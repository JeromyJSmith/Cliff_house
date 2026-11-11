"""Reject inconsistent edges; solve reciprocal rigid constraints, retaining all evidence."""
import json
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from register_ten_scans import OUT,load,moved
from refine_registration_graph import DEST
from verify_cloudcompare_pilot import stats
D=OUT/'qualified-graph-v002'
def main():
 D.mkdir(exist_ok=False);g=json.loads((DEST/'graph.json').read_text());initial=json.loads((OUT/'registration.json').read_text());by={(r['data'],r['reference']):np.array(r['matrix']) for r in g['runs']};edges=[];excluded=[]
 for c in g['reciprocal_checks']:
  i,k=c['pair'];err=c['cycle']['median']
  if err>.2:excluded.append(c);continue
  edges.extend([(i,k,by[i,k],err),(k,i,by[k,i],err)])
 # Reuse the independently checked 80% 1<->6 fit, which is better constrained than its 50% retry.
 for r in initial['runs']:
  if {r['data'],r['reference']}=={1,6}:edges.append((r['data'],r['reference'],np.array(r['matrix']),.028135))
 ids=[i for i in range(1,11) if i!=6];pts={i:load(OUT/f'scan-{i}-train.ply')['xyz'][::150].astype(float) for i in range(1,11)}
 def pack(m):return np.r_[Rotation.from_matrix(m[:3,:3]).as_rotvec(),m[:3,3]]
 def unpack(x):
  poses={6:np.eye(4)}
  for n,i in enumerate(ids):
   m=np.eye(4);m[:3,:3]=Rotation.from_rotvec(x[n*6:n*6+3]).as_matrix();m[:3,3]=x[n*6+3:n*6+6];poses[i]=m
  return poses
 def fun(x):
  p=unpack(x);return np.concatenate([(moved(pts[i],p[i])-moved(moved(pts[i],m),p[k])).ravel()/np.sqrt(max(.025,e)) for i,k,m,e in edges])
 sol=least_squares(fun,np.concatenate([pack(np.array(initial['transforms'][str(i)])) for i in ids]),loss='soft_l1',f_scale=.1,max_nfev=150);p=unpack(sol.x);res=[]
 for i,k,m,e in edges:res.append({'pair':[i,k],'constraint_displacement':stats(np.linalg.norm(moved(pts[i],p[i])-moved(moved(pts[i],m),p[k]),axis=1))})
 result={'transforms':{str(i):m.tolist() for i,m in p.items()},'excluded_edges':excluded,'constraints':res,'optimizer_success':bool(sol.success),'scale_adjusted':False,'acceptance':'Pending visual and held-out review; units unverified'};(D/'graph.json').write_text(json.dumps(result,indent=2));print([(r['pair'],round(r['constraint_displacement']['median'],3)) for r in res])
if __name__=='__main__':main()
