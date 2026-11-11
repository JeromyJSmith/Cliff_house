"""Stream all original points through recorded rigid poses; native CloudCompare merge.
Only creates new files. Retains RGB, scan ID and individual registered derivatives.
"""
import hashlib,json,pathlib,subprocess,time
import numpy as np
from register_shared_crops import D
from register_ten_scans import moved
from run_cloudcompare_pilot import DTYPE
from assess_cloud_overlap import digest
O=D/'registered-reference'
OUTTYPE=np.dtype([('xyz','<f4',(3,)),('rgb','u1',(3,)),('scan_id','<f4')])
def main():
 if (D/'SOURCE_IDENTITY_REJECTED.md').exists():raise RuntimeError("Source identity rejected: these October scans are 401 Pearl, not Cliff House. Supply verified November 9–10 captures in a new run.")
 O.mkdir(exist_ok=False);j=json.loads((D/'crops.json').read_text());sol=json.loads((D/'solution.json').read_text());receipts=[];paths=[]
 for i,c in enumerate(j['sources'],1):
  source=pathlib.Path(c['source']);m=np.array(sol['transforms'][str(i)]);assert np.allclose(m[:3,:3].T@m[:3,:3],np.eye(3),atol=1e-5) and abs(np.linalg.det(m[:3,:3])-1)<1e-5
  out=O/f'scan-{i:02d}-registered.ply';paths.append(out);h=hashlib.sha256();before=source.stat();n=c['source_vertices'];header=(f'ply\nformat binary_little_endian 1.0\ncomment provisional rigid registration; captured scale; scan 6 reference\nelement vertex {n}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nproperty float scan_id\nend_header\n').encode();written=0;lo=np.full(3,np.inf);hi=-lo
  with source.open('rb') as f,out.open('xb') as target:
   original=b''
   while not original.endswith(b'end_header\n'):original+=f.readline()
   h.update(original);target.write(header)
   while blob:=f.read(15*1000000):
    h.update(blob);a=np.frombuffer(blob,dtype=DTYPE);b=np.empty(len(a),dtype=OUTTYPE);b['xyz']=moved(a['xyz'].astype(float),m);b['rgb']=a['rgb'];b['scan_id']=i;assert np.isfinite(b['xyz']).all();lo=np.minimum(lo,b['xyz'].min(axis=0));hi=np.maximum(hi,b['xyz'].max(axis=0));target.write(b.tobytes());written+=len(a)
  assert written==n and h.hexdigest()==c['source_sha256'];after=source.stat();assert before.st_size==after.st_size and before.st_mtime_ns==after.st_mtime_ns
  receipt={'scan':i,'source':str(source),'source_sha256':h.hexdigest(),'source_unchanged':True,'output':str(out),'output_sha256':digest(out),'vertices':written,'matrix':m.tolist(),'bbox':[lo.tolist(),hi.tolist()]};receipts.append(receipt);(O/f'scan-{i:02d}-receipt.json').write_text(json.dumps(receipt,indent=2));print('registered',i,written,flush=True)
 merged=O/'Cliff-House-provisional-registered-all-10.ply';assert not merged.exists();cmd=['/Users/jero/.local/bin/CloudCompare','-SILENT','-AUTO_SAVE','OFF','-C_EXPORT_FMT','PLY','-PLY_EXPORT_FMT','BINARY_LE']
 for p in paths:cmd+=['-O',str(p)]
 cmd+=['-MERGE_CLOUDS','-SAVE_CLOUDS','FILE',merged.name];start=time.time();r=subprocess.run(cmd,cwd=O,capture_output=True,text=True,timeout=1200);(O/'merge.log').write_text(r.stdout+'\n'+r.stderr);receipt={'status':'provisional registered reference; not survey-qualified','sources':receipts,'command':cmd,'returncode':r.returncode,'seconds':time.time()-start,'expected_vertices':sum(x['vertices'] for x in receipts),'merged':str(merged),'no_smoothing_deduplication_or_meshing':True};(O/'manifest.json').write_text(json.dumps(receipt,indent=2));assert r.returncode==0 and merged.exists();print('MERGED',merged,flush=True)
if __name__=='__main__':main()
