"""Denser source-file spot checks on the spatially withheld feature cells."""
import json,pathlib
import numpy as np
from scipy.spatial import cKDTree
from register_shared_crops import D
from register_ten_scans import moved
from run_cloudcompare_pilot import DTYPE
from verify_cloudcompare_pilot import stats

def main():
 j=json.loads((D/'crops.json').read_text());sol=json.loads((D/'solution.json').read_text());seed={int(k):np.array(v) for k,v in j['seed_transforms'].items()};delta={int(k):np.array(v) for k,v in sol['delta'].items()};pts={}
 for i,c in enumerate(j['sources'],1):
  p=pathlib.Path(c['source']);f=p.open('rb');header=b''
  while not header.endswith(b'end_header\n'):header+=f.readline()
  f.close();a=np.memmap(p,dtype=DTYPE,mode='r',offset=len(header),shape=(c['source_vertices'],));idx=np.linspace(1,len(a)-2,1000000,dtype=np.int64);pts[i]=moved(a[idx]['xyz'].astype(float),seed[i]);del a
 keys={i:np.floor(x/.4).astype(int) for i,x in pts.items()};checks=[]
 for pair in j['pairs']:
  i,k=pair['pair'];cells={tuple(c) for c in pair['validation_cells']};clouds=[];cellkeys=[]
  for n in (i,k):
   mask=np.array([tuple(key) in cells for key in keys[n]]);clouds.append(pts[n][mask]);cellkeys.append(keys[n][mask])
  x,y=clouds;xx,yy=moved(x,delta[i]),moved(y,delta[k]);b1=cKDTree(y).query(x,workers=2)[0];b2=cKDTree(x).query(y,workers=2)[0];a1=cKDTree(yy).query(xx,workers=2)[0];a2=cKDTree(xx).query(yy,workers=2)[0];local=[]
  for cell in sorted(cells):
   m1=np.all(cellkeys[0]==cell,axis=1);m2=np.all(cellkeys[1]==cell,axis=1)
   if m1.sum()<20 or m2.sum()<20:continue
   local.append({'cell':list(cell),'points':[int(m1.sum()),int(m2.sum())],'before':stats(np.r_[b1[m1],b2[m2]]),'after':stats(np.r_[a1[m1],a2[m2]])})
  r={'pair':[i,k],'points':[len(x),len(y)],'before':stats(np.r_[b1,b2]),'after':stats(np.r_[a1,a2]),'cells':local};checks.append(r);print([i,k],r['after']['median'],r['after']['p95'],flush=True)
 (D/'dense-validation.json').write_text(json.dumps({'sampling':'1,000,000 deterministic source records per cloud, excluding endpoints; denser spot check, not all records or independent survey control','checks':checks},indent=2))
if __name__=='__main__':main()
