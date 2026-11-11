"""Overlap-aware CloudCompare edge fits, reciprocal checks and rigid pose graph."""
import concurrent.futures,json,pathlib,subprocess,time
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
from register_ten_scans import OUT,load,save,moved
from verify_cloudcompare_pilot import stats
DEST=OUT/'overlap-graph-refinement'
def main():
 DEST.mkdir(exist_ok=False);samples=[load(OUT/f'scan-{i}-train.ply')[::3] for i in range(1,11)];pts=[s['xyz'].astype(float) for s in samples]
 edges=[(1,2),(2,3),(3,4),(4,9),(9,10),(8,9),(7,8),(5,6),(6,8),(1,6),(3,7),(2,5),(4,10)]
 def fit(pair):
  i,k=pair;folder=DEST/f'{i}-to-{k}';folder.mkdir();save(folder/'data.ply',samples[i-1]);save(folder/'reference.ply',samples[k-1]);cmd=['/Users/jero/.local/bin/CloudCompare','-SILENT','-AUTO_SAVE','OFF','-O',str(folder/'data.ply'),'-O',str(folder/'reference.ply'),'-ICP','-ITER','60','-OVERLAP','50','-RANDOM_SAMPLING_LIMIT','50000'];r=subprocess.run(cmd,cwd=folder,capture_output=True,text=True,timeout=180);(folder/'log.txt').write_text(r.stdout+'\n'+r.stderr);assert r.returncode==0;m=np.loadtxt(next(folder.glob('*REGISTRATION_MATRIX*.txt')));assert abs(np.linalg.det(m[:3,:3])-1)<1e-5;receipt={'data':i,'reference':k,'matrix':m.tolist(),'command':cmd};(folder/'result.json').write_text(json.dumps(receipt,indent=2));print('fit',i,k,flush=True);return receipt
 pairs=edges+[(k,i) for i,k in edges]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:runs=list(pool.map(fit,pairs))
 by={(r['data'],r['reference']):np.array(r['matrix']) for r in runs};accepted=[];checks=[]
 for i,k in edges:
  m=by[i,k];back=by[k,i];cycle=moved(moved(pts[i-1],m),back);d=np.linalg.norm(cycle-pts[i-1],axis=1);err=float(np.median(d));checks.append({'pair':[i,k],'cycle':stats(d)});accepted.append((i,k,m,1/max(.03,err)))
 # Optimize rigid poses using edge predictions at three noncollinear source points.
 init=json.loads((OUT/'registration.json').read_text())['transforms'];ids=[i for i in range(1,11) if i!=6]
 def pack(m):return np.r_[Rotation.from_matrix(m[:3,:3]).as_rotvec(),m[:3,3]]
 def unpack(x):
  result={6:np.eye(4)}
  for n,i in enumerate(ids):
   m=np.eye(4);m[:3,:3]=Rotation.from_rotvec(x[n*6:n*6+3]).as_matrix();m[:3,3]=x[n*6+3:n*6+6];result[i]=m
  return result
 anchors={i:np.array([np.mean(p,axis=0),np.mean(p,axis=0)+[2,0,0],np.mean(p,axis=0)+[0,2,0],np.mean(p,axis=0)+[0,0,2]]) for i,p in enumerate(pts,1)}
 def residual(x):
  poses=unpack(x);return np.concatenate([(moved(anchors[i],poses[i])-moved(moved(anchors[i],m),poses[k])).ravel()*np.sqrt(w) for i,k,m,w in accepted])
 sol=least_squares(residual,np.concatenate([pack(np.array(init[str(i)])) for i in ids]),loss='soft_l1',f_scale=.1,max_nfev=200);poses=unpack(sol.x)
 result={'runs':runs,'reciprocal_checks':checks,'transforms':{str(i):m.tolist() for i,m in poses.items()},'optimizer_success':bool(sol.success),'cost':sol.cost,'scale_adjusted':False,'units':'unverified source units'};(DEST/'graph.json').write_text(json.dumps(result,indent=2));print('COMPLETE',flush=True)
if __name__=='__main__':main()
