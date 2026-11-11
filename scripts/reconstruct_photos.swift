// Apple RealityKit photogrammetry runner. No Spirula, inferred scale or destructive cleanup.
// API source: installed RealityFoundation macOS 27.2 SDK and
// https://developer.apple.com/documentation/realitykit/photogrammetrysession/request/modelfile(url:detail:geometry:)
import Foundation
import RealityKit
import Darwin

struct RunnerError: Error, CustomStringConvertible {
    let description: String
    init(_ message: String) { description = message }
}

@main
struct ReconstructPhotos {
    static let usage = """
    reconstruct_photos --capability
    reconstruct_photos --help
    reconstruct_photos --input ABS_IMAGE_DIRECTORY --output ABS_NEW_OBJ_DIRECTORY \
      --checkpoint ABS_NEW_CHECKPOINT_DIRECTORY --log ABS_NEW_JSONL_LOG

    Runs one medium-detail OBJ request, unordered samples, high feature sensitivity,
    object masking disabled. All destinations must be new, distinct persistent paths.
    Input images are read only; no automatic cleanup or replacement occurs.
    A request error, incomplete stitching, cancellation or missing OBJ exits nonzero.
    """

    static func emit(_ event: String, _ fields: [String: Any] = [:], log: FileHandle? = nil) {
        var value = fields
        value["event"] = event
        value["time_utc"] = ISO8601DateFormatter().string(from: Date())
        let data = (try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])) ?? Data("{}".utf8)
        var line = data; line.append(10)
        FileHandle.standardOutput.write(line)
        log?.write(line)
    }

    static func durableURL(_ path: String, directory: Bool) throws -> URL {
        guard path.hasPrefix("/") else { throw RunnerError("An absolute path is required: \(path)") }
        let url = URL(fileURLWithPath: path, isDirectory: directory).standardizedFileURL.resolvingSymlinksInPath()
        let components = url.pathComponents.map { $0.lowercased() }
        guard !components.contains(where: { ["tmp", "temp", ".trash"].contains($0) }),
              !url.path.hasPrefix("/private/var/folders/"), !url.path.hasPrefix("/var/folders/")
        else { throw RunnerError("Refusing temporary, auto-cleaned or Trash storage: \(url.path)") }
        return url
    }

    static func run() async throws {
        let args = Array(CommandLine.arguments.dropFirst())
        if args == ["--help"] || args.isEmpty { print(usage); return }
        if args == ["--capability"] {
            emit("capability", ["is_supported": PhotogrammetrySession.isSupported,
                "maximum_input_images": PhotogrammetrySession.limits.maximumNumberOfInputImages,
                "maximum_input_dimension": PhotogrammetrySession.limits.maximumInputImageDimension,
                "os_version": ProcessInfo.processInfo.operatingSystemVersionString])
            guard PhotogrammetrySession.isSupported else { throw RunnerError("PhotogrammetrySession is unsupported") }
            return
        }
        let keys = Set(["--input", "--output", "--checkpoint", "--log"])
        guard args.count == 8 else { throw RunnerError(usage) }
        var values: [String: String] = [:]
        for index in stride(from: 0, to: args.count, by: 2) {
            guard keys.contains(args[index]), values[args[index]] == nil else { throw RunnerError("Unknown or duplicate argument: \(args[index])") }
            values[args[index]] = args[index + 1]
        }
        guard values.count == 4 else { throw RunnerError(usage) }
        guard PhotogrammetrySession.isSupported else { throw RunnerError("PhotogrammetrySession is unsupported") }
        let input = try durableURL(values["--input"]!, directory: true)
        let output = try durableURL(values["--output"]!, directory: true)
        let checkpoint = try durableURL(values["--checkpoint"]!, directory: true)
        let logURL = try durableURL(values["--log"]!, directory: false)
        let fm = FileManager.default
        var isDirectory: ObjCBool = false
        guard fm.fileExists(atPath: input.path, isDirectory: &isDirectory), isDirectory.boolValue else { throw RunnerError("Input directory does not exist") }
        let destinations = [output, checkpoint, logURL]
        guard Set(destinations.map(\.path)).count == destinations.count else { throw RunnerError("Destinations must be distinct") }
        for url in destinations {
            guard !fm.fileExists(atPath: url.path) else { throw RunnerError("Refusing to replace existing output: \(url.path)") }
            guard !url.path.hasPrefix(input.path + "/"), !input.path.hasPrefix(url.path + "/") else { throw RunnerError("Input and destinations must not contain one another") }
            for other in destinations where other != url {
                guard !url.path.hasPrefix(other.path + "/") else { throw RunnerError("Destinations must not contain one another") }
            }
        }
        let imageExtensions: Set<String> = ["jpg", "jpeg", "png", "heic", "heif", "tif", "tiff", "exr"]
        let images = try fm.contentsOfDirectory(at: input, includingPropertiesForKeys: nil).filter { imageExtensions.contains($0.pathExtension.lowercased()) }
        guard images.count >= 3 else { throw RunnerError("At least three input images are required") }
        guard images.count <= PhotogrammetrySession.limits.maximumNumberOfInputImages else { throw RunnerError("Input image count exceeds this device's supported limit") }
        try fm.createDirectory(at: output, withIntermediateDirectories: true)
        try fm.createDirectory(at: checkpoint, withIntermediateDirectories: true)
        try fm.createDirectory(at: logURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let descriptor = open(logURL.path, O_WRONLY | O_CREAT | O_EXCL, 0o600)
        guard descriptor >= 0 else { throw RunnerError("Cannot create exclusive log: \(logURL.path)") }
        let log = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? log.synchronize(); try? log.close() }
        var configuration = PhotogrammetrySession.Configuration()
        configuration.sampleOrdering = .unordered
        configuration.featureSensitivity = .high
        configuration.isObjectMaskingEnabled = false
        configuration.checkpointDirectory = checkpoint
        emit("start", ["input": input.path, "input_image_count": images.count, "output": output.path,
            "checkpoint": checkpoint.path, "log": logURL.path, "detail": "medium", "sample_ordering": "unordered",
            "feature_sensitivity": "high", "object_masking": false, "physical_scale": "unverified"], log: log)
        do {
            let session = try PhotogrammetrySession(input: input, configuration: configuration)
            let request = PhotogrammetrySession.Request.modelFile(url: output, detail: .medium)
            try session.process(requests: [request])
            var requestCompleted = false
            var processingCompleted = false
            for try await event in session.outputs {
                switch event {
                case .inputComplete: emit("input_complete", log: log)
                case .requestProgress(_, let fraction): emit("progress", ["fraction_complete": fraction], log: log)
                case .requestProgressInfo(_, let info):
                    var fields: [String: Any] = [:]
                    if let stage = info.processingStage { fields["stage"] = String(describing: stage) }
                    if let remaining = info.estimatedRemainingTime { fields["estimated_seconds_remaining"] = remaining }
                    emit("progress_info", fields, log: log)
                case .requestComplete(_, let result):
                    guard case .modelFile(let url) = result else { throw RunnerError("Unexpected request result") }
                    requestCompleted = true; emit("request_complete", ["path": url.path], log: log)
                case .requestError(_, let error): session.cancel(); throw RunnerError("Request failed: \(error)")
                case .processingComplete: processingCompleted = true; emit("processing_complete", log: log)
                case .processingCancelled: throw RunnerError("Processing cancelled")
                case .invalidSample(let id, let reason): emit("invalid_sample", ["id": id, "reason": reason], log: log)
                case .skippedSample(let id): emit("skipped_sample", ["id": id], log: log)
                case .automaticDownsampling: emit("automatic_downsampling", log: log)
                case .stitchingIncomplete: session.cancel(); throw RunnerError("Stitching incomplete; any outputs remain provisional")
                @unknown default: emit("other_output", ["description": String(describing: event)], log: log)
                }
                if processingCompleted { break }
            }
            guard requestCompleted && processingCompleted else { throw RunnerError("Output sequence ended before complete success") }
            let files = try fm.contentsOfDirectory(at: output, includingPropertiesForKeys: [.fileSizeKey])
            guard files.contains(where: { $0.pathExtension.lowercased() == "obj" && ((try? $0.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) > 0 }) else { throw RunnerError("Completion returned without a nonempty OBJ") }
            emit("success", ["files": files.map(\.path), "quality_review_required": true], log: log)
        } catch {
            emit("failure", ["error": String(describing: error), "outputs_preserved": true], log: log)
            throw error
        }
    }

    static func main() async {
        do { try await run() }
        catch { emit("fatal", ["error": String(describing: error)]); exit(EXIT_FAILURE) }
    }
}
