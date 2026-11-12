#!/usr/bin/env bash
# Build Spirula Studio's headless CUDA binary at a pinned commit.
# Usage (inside the pixi `spirula-build` environment):
#   tools/build_spirula_cuda.sh <commit> <cuda-arch> <out-dir>     e.g. 667e353… 120 /path/out
# Writes <out-dir>/spirula and <out-dir>/BUILD_INFO. The GUI is off, so the binary needs no display, GL or Vulkan.
set -euo pipefail
commit=$1 arch=$2 out=$3
src=$(mktemp -d)
trap 'rm -rf "$src"' EXIT
git -C "$src" init -q
git -C "$src" remote add origin https://github.com/harry7557558/spirula-studio.git
git -C "$src" fetch -q --depth 1 origin "$commit"
git -C "$src" checkout -q FETCH_HEAD
cd "$src"
bash build_develop.bash -DSS_BACKEND=cuda -DSS_BUILD_GUI=OFF \
  -DCMAKE_CUDA_ARCHITECTURES="$arch" -DTORCH_CUDA_ARCH_LIST="${arch:0:-1}.${arch: -1}" \
  -DCMAKE_BUILD_TYPE=Release
mkdir -p "$out"
install -m 755 build_cuda/spirula "$out/spirula"
printf 'spirula_commit=%s\ncuda_arch=%s\nnvcc=%s\ncxx=%s\n' "$commit" "$arch" \
  "$(nvcc --version | tail -1)" "$(${CXX:-c++} --version | head -1)" > "$out/BUILD_INFO"
