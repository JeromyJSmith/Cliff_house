"""Solve crop-constrained rigid poses and validate reserved spatial cells."""
import json
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw
from register_ten_scans import moved,load
from register_shared_crops import D
from verify_cloudcompare_pilot import stats

def main():
 if (D/'SOURCE_IDENTITY_REJECTED.md').exists():raise RuntimeError("Source identity rejected: these October scans are 401 Pearl, not Cliff House. Supply verified November 9–10 captures in a new run.")
 j=json.loads((D/'crops.json').read_text());ids=[i for i in range(1,11) if i!=6];seed={int(i):np.array(m) for i,m in j['seed_transforms'].items()};edges=[]
 for pair in j['pairs']:
  i,k=pair['pair'];folder=D/f'{i}-{k}'
  for fit in pair['fits']:
   a,b=fit['data'],fit['reference'];x=load(folder/f'scan-{a}-crop.ply')['xyz'][::30].astype(float);edges.append((a,b,x,np.array(fit['delta_common_frame'])))
 def unpack(v):
  p={6:np.eye(4)}
  for n,i in enumerate(ids):
   m=np.eye(4);m[:3,:3]=Rotation.from_rotvec(v[n*6:n*6+3]).as_matrix();m[:3,3]=v[n*6+3:n*6+6];p[i]=m
  return p
 def fun(v):
  p=unpack(v);return np.concatenate([(moved(x,p[i])-moved(moved(x,m),p[k])).ravel()/np.sqrt(len(x)) for i,k,x,m in edges])
 sol=least_squares(fun,np.zeros(54),loss='soft_l1',f_scale=.01,max_nfev=150);p=unpack(sol.x);trans={i:p[i]@seed[i] for i in seed};checks=[];constraints=[]
 for a,b,x,m in edges:constraints.append({'pair':[a,b],'displacement':stats(np.linalg.norm(moved(x,p[a])-moved(moved(x,m),p[b]),axis=1))})
 for pair in j['pairs']:
  i,k=pair['pair'];folder=D/f'{i}-{k}';x=load(folder/f'scan-{i}-validation.ply')['xyz'].astype(float);y=load(folder/f'scan-{k}-validation.ply')['xyz'].astype(float);xx=moved(x,p[i]);yy=moved(y,p[k]);before=np.r_[cKDTree(y).query(x)[0],cKDTree(x).query(y)[0]];after=np.r_[cKDTree(yy).query(xx)[0],cKDTree(xx).query(yy)[0]];checks.append({'pair':[i,k],'points':[len(x),len(y)],'before':stats(before),'after':stats(after),'cycle':pair['cycle']})
 result={'transforms':{str(i):m.tolist() for i,m in trans.items()},'delta':{str(i):m.tolist() for i,m in p.items()},'constraints':constraints,'validation':checks,'optimizer_success':bool(sol.success),'scale_adjusted':False,'physical_units':'captured scale, independently unverified','accepted':False};(D/'solution.json').write_text(json.dumps(result,indent=2));print(json.dumps({'constraints':constraints,'validation':checks},indent=2))
 # Detail comparison for each common crop, same source axes and bounds.
 colors=[(30,210,230),(245,90,170)];sheet=Image.new('RGB',(1200,300*len(j['pairs'])),(15,18,23));draw=ImageDraw.Draw(sheet)
 for row,pair in enumerate(j['pairs']):
  i,k=pair['pair'];folder=D/f'{i}-{k}';x=load(folder/f'scan-{i}-crop.ply')['xyz'];y=load(folder/f'scan-{k}-crop.ply')['xyz'];lo,hi=np.quantile(np.r_[x,y],[.005,.995],axis=0);ax=sorted(range(3),key=lambda a:hi[a]-lo[a],reverse=True)[:2];u,v=ax;scale=min(550/(hi[u]-lo[u]),240/(hi[v]-lo[v]))
  for col,pts in enumerate(((x,y),(moved(x,p[i]),moved(y,p[k])))):
   canvas=np.full((300,600,3),[15,18,23],np.uint8)
   for cloud,color in zip(pts,colors):
    a=((cloud[:,u]-lo[u])*scale+20).astype(int);b=(280-(cloud[:,v]-lo[v])*scale).astype(int);ok=(a>=0)&(a<600)&(b>=40)&(b<300);canvas[b[ok],a[ok]]=color
   sheet.paste(Image.fromarray(canvas),(col*600,row*300));draw.text((col*600+10,row*300+10),f'{i}-{k} '+('SEED' if col==0 else 'CROP GRAPH')+f' axes {u},{v}',fill='white')
 sheet.save(D/'crop-comparison.jpg',quality=93)
if __name__=='__main__':main()
