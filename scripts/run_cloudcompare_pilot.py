"""Run a rigid two-scan CloudCompare CLI pilot on persistent derived samples.
Hold out every fourth sample record; no scale adjustment, raw writes, or merging.
"""
import argparse,json,pathlib,subprocess,time
import numpy as np
DTYPE=np.dtype([('xyz','<f4',(3,)),('rgb','u1',(3,))])
def load(p):
 with p.open('rb') as f:
  header=b''
  while not header.endswith(b'end_header\n'):
   line=f.readline()
   if not line:raise ValueError('Missing header end')
   header+=line
 return np.fromfile(p,dtype=DTYPE,offset=len(header))
def save(p,a):
 with p.open('xb') as f:
  f.write((f'ply\nformat binary_little_endian 1.0\nelement vertex {len(a)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n').encode());f.write(a.tobytes())
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);j=json.loads(a.overlap.read_text());clouds=j['clouds'];data=load(pathlib.Path(clouds[a.data-1]['sample']));ref=load(pathlib.Path(clouds[a.reference-1]['sample']));mask=np.arange(len(data))%4!=0;rmask=np.arange(len(ref))%4!=0
 for name,pts in [('data-train',data[mask]),('reference-train',ref[rmask]),('data-holdout',data[~mask]),('reference-holdout',ref[~rmask])]:save(out/(name+'.ply'),pts)
 cmd=['/Users/jero/.local/bin/CloudCompare','-SILENT','-AUTO_SAVE','OFF','-O',str(out/'data-train.ply'),'-O',str(out/'reference-train.ply'),'-ICP','-ITER','40','-OVERLAP','80','-RANDOM_SAMPLING_LIMIT','200000'];start=time.time();r=subprocess.run(cmd,cwd=out,capture_output=True,text=True,timeout=180)
 (out/'cloudcompare.log').write_text(r.stdout+'\nSTDERR\n'+r.stderr)
 receipt={'data_scan':a.data,'reference_scan':a.reference,'command':cmd,'returncode':r.returncode,'seconds':time.time()-start,'training_records_each':int(mask.sum()),'holdout_records_each':int((~mask).sum()),'rigid_only':True,'adjust_scale':False,'overlap_parameter_percent':80,'overlap_parameter_is_estimate':True,'source_report':str(a.overlap.resolve()),'raw_sources_modified':False,'new_files':[str(x) for x in out.iterdir()]}
 (out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2));print(r.stdout[-4000:]);print(r.stderr[-500:])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--overlap',type=pathlib.Path,required=True);p.add_argument('--data',type=int,default=7);p.add_argument('--reference',type=int,default=6);p.add_argument('--output',type=pathlib.Path,required=True);main(p.parse_args())
