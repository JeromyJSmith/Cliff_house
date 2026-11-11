"""Rigid CloudCompare fits on shared, nonplanar spatial crops.
Crops are geometric edge/corner candidates, not semantically identified doorways.
Original source coordinates and scale are retained through explicit transforms.
"""
import json,pathlib,concurrent.futures,subprocess
import numpy as np
from scipy.spatial import cKDTree
from register_ten_scans import OUT,load,save,moved
from verify_cloudcompare_pilot import stats
D=OUT.parent/'shared-crop-registration-v002'
EDGES=[(1,2),(2,3),(3,4),(4,9),(9,10),(8,9),(7,8),(5,6),(6,8),(1,6),(3,7),(2,5),(4,10),(5,8),(2,6)]
def tiles(points,step=.4):
 keys=np.floor(points/step).astype(int);u,inv,counts=np.unique(keys,axis=0,return_inverse=True,return_counts=True);chosen={}
 for n in np.flatnonzero(counts>=20):
  x=points[inv==n];ev=np.linalg.eigvalsh(np.cov(x.T));
  if ev[0]/max(ev.sum(),1e-12)>.015:chosen[tuple(u[n])]=n
 return keys,chosen

def main():
 if (D/'SOURCE_IDENTITY_REJECTED.md').exists():raise RuntimeError("Source identity rejected: these October scans are 401 Pearl, not Cliff House. Supply verified November 9–10 captures in a new run.")
 D.mkdir(exist_ok=False);j=json.loads((OUT/'registration.json').read_text());poses={int(k):np.array(v) for k,v in j['transforms'].items()};samples={i:load(OUT/f'scan-{i}-train.ply') for i in range(1,11)};points={i:moved(s['xyz'],poses[i]) for i,s in samples.items()};tiledata={i:tiles(x) for i,x in points.items()}
 def pair(edge):
  i,k=edge;folder=D/f'{i}-{k}';folder.mkdir();ki,ci=tiledata[i];kk,ck=tiledata[k];common=set(ci)&set(ck)
  # Keep corresponding 0.4-unit cells containing nonplanar geometry in BOTH scans.
  validation={c for c in common if (c[0]+2*c[1]+3*c[2])%5==0}; fitting=common-validation
  masks=[np.array([tuple(key) in fitting for key in keys]) for keys in (ki,kk)]
  for n,keys in ((i,ki),(k,kk)):
   vm=np.array([tuple(key) in validation for key in keys]);s=samples[n][vm].copy();s['xyz']=points[n][vm];save(folder/f'scan-{n}-validation.ply',s);counts=[int(x.sum()) for x in masks]
  assert min(counts)>300,(edge,counts)
  crops=[]
  for n,mask in zip((i,k),masks):
   s=samples[n][mask].copy();s['xyz']=points[n][mask];crops.append(s);save(folder/f'scan-{n}-crop.ply',s)
  fits=[]
  for reverse in (False,True):
   data,ref=(k,i) if reverse else (i,k);run=folder/('reverse' if reverse else 'forward');run.mkdir();save(run/'data.ply',crops[1 if reverse else 0]);save(run/'reference.ply',crops[0 if reverse else 1]);cmd=['/Users/jero/.local/bin/CloudCompare','-SILENT','-AUTO_SAVE','OFF','-O',str(run/'data.ply'),'-O',str(run/'reference.ply'),'-ICP','-ITER','60','-OVERLAP','90','-RANDOM_SAMPLING_LIMIT','100000'];r=subprocess.run(cmd,cwd=run,capture_output=True,text=True,timeout=180);(run/'log.txt').write_text(r.stdout+'\n'+r.stderr);assert r.returncode==0;m=np.loadtxt(next(run.glob('*REGISTRATION_MATRIX*.txt')));assert np.allclose(m[:3,:3].T@m[:3,:3],np.eye(3),atol=1e-5) and np.linalg.det(m[:3,:3])>0
   local=np.linalg.inv(poses[ref])@m@poses[data];fits.append({'data':data,'reference':ref,'matrix':local.tolist(),'delta_common_frame':m.tolist(),'command':cmd})
  cycle=np.array(fits[1]['delta_common_frame'])@np.array(fits[0]['delta_common_frame']);x=crops[0]['xyz'];err=np.linalg.norm(moved(x,cycle)-x,axis=1);result={'pair':[i,k],'crop_counts':counts,'shared_corner_cells':[[int(v) for v in c] for c in sorted(common)],'validation_cells':[[int(v) for v in c] for c in sorted(validation)],'cell_size':.4,'seed':'direct scan-6 poses from previous run','cycle':stats(err),'fits':fits};(folder/'result.json').write_text(json.dumps(result,indent=2));print(edge,counts,'cycle',result['cycle']['median'],flush=True);return result
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(pair,EDGES))
 (D/'crops.json').write_text(json.dumps({'sources':j['sources'],'seed_transforms':j['transforms'],'pairs':results,'units':'captured source units; unchanged scale','semantic_doorway_labels_verified':False},indent=2));print('COMPLETE',flush=True)
if __name__=='__main__':main()
