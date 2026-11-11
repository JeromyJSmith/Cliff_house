"""Dense temporal sampling of verified clip035 lodge coverage; native COLMAP only."""
import pathlib,json,subprocess,concurrent.futures,hashlib
import reconstruct_colmap_exterior as pipeline
BASE=pipeline.BASE
CAPTURES=BASE/'clip035-first-minute-frames-v001'

def main():
 CAPTURES.mkdir(exist_ok=False);raw=CAPTURES/'source-frames';raw.mkdir();r=next(r for r in json.loads((BASE/'capture-provenance.json').read_text()) if r['source'].endswith('_035.insv'));assert r['capture_time_denver'].startswith('2026-11-10')
 jobs=[(tick/2,lens) for tick in range(0,120,2) for lens in (0,1)]
 def extract(job):
  t,lens=job;file=raw/f'clip035-t{t:07.2f}-lens{lens}.jpg';cmd=['ffmpeg','-nostdin','-v','error','-threads','2','-ss',str(t),'-i',r['source'],'-map',f'0:v:{lens}','-frames:v','1','-q:v','2','-threads','2','-n',str(file)];p=subprocess.run(cmd,capture_output=True,text=True);assert p.returncode==0,p.stderr
  return {'source_video':r['source'],'embedded_capture_date':r['capture_time_denver'],'timestamp_seconds':t,'video_stream':lens,'source_frame':str(file),'extraction_command':cmd,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:frames=list(pool.map(extract,jobs))
 cal=json.loads((BASE/'exterior-perspective-v001/manifest.json').read_text())['source_lens_calibration'];manifest={'frames':frames,'source_lens_calibration':cal,'selection':'First minute of earliest November10 360 capture, one capture per second, both fisheye streams.','camera_model':'OPENCV_FISHEYE','calibration_status':'Transferred existing clip041 estimate; not survey calibrated.'};(CAPTURES/'manifest.json').write_text(json.dumps(manifest,indent=2));print('EXTRACTED',len(frames),flush=True)
 pipeline.OUT=BASE/'colmap-first-minute-v001';pipeline.MANIFEST=CAPTURES/'manifest.json';pipeline.NEIGHBORS=12;pipeline.CROSS_CLIP_CANDIDATES=0;pipeline.main()
if __name__=='__main__':main()
