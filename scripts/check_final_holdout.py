"""Directional checks on records excluded from both seed and crop fitting; vertical views."""
import json,pathlib
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw
from register_shared_crops import D
from register_ten_scans import moved,load
from verify_cloudcompare_pilot import stats

def main():
 j=json.loads((D/'crops.json').read_text());s=json.loads((D/'solution.json').read_text());seed={int(k):np.array(v) for k,v in j['seed_transforms'].items()};delta={int(k):np.array(v) for k,v in s['delta'].items()};pts={i:moved(load(pathlib.Path(c['sample']))[::4]['xyz'],seed[i]) for i,c in enumerate(j['sources'],1)};out=[]
 for pair in j['pairs']:
  i,k=pair['pair'];cells={tuple(c) for c in pair['shared_corner_cells']};clouds=[]
  for n in (i,k):
   keys=np.floor(pts[n]/.4).astype(int);mask=np.array([tuple(c) in cells for c in keys]);clouds.append(pts[n][mask])
  x,y=clouds;xx,yy=moved(x,delta[i]),moved(y,delta[k]);directions=[]
  for a,b,aa,bb,label in [(x,y,xx,yy,[i,k]),(y,x,yy,xx,[k,i])]:directions.append({'direction':label,'points':len(a),'before':stats(cKDTree(b).query(a)[0]),'after':stats(cKDTree(bb).query(aa)[0])})
  out.append({'pair':[i,k],'directions':directions})
 (D/'final-holdout.json').write_text(json.dumps({'records':'every fourth 200k sample record; excluded from all seed and cropped fits','limitation':'spatially correlated sensor measurements, no independent survey control','checks':out},indent=2))
 # Vertical XY and ZY views of the weakest shared groups, plus the strongest control.
 pairs=[(1,2),(2,5),(5,6),(5,8),(1,6)];im=Image.new('RGB',(1400,350*len(pairs)),(15,18,23));draw=ImageDraw.Draw(im)
 for row,(i,k) in enumerate(pairs):
  x=moved(load(D/f'{i}-{k}'/f'scan-{i}-crop.ply')['xyz'],delta[i]);y=moved(load(D/f'{i}-{k}'/f'scan-{k}-crop.ply')['xyz'],delta[k]);lo,hi=np.quantile(np.r_[x,y],[.005,.995],axis=0)
  for col,(u,v) in enumerate(((0,1),(2,1))):
   scale=min(650/(hi[u]-lo[u]),290/(hi[v]-lo[v]));canvas=np.full((350,700,3),[15,18,23],np.uint8)
   for cloud,color in ((x,(30,210,230)),(y,(245,90,170))):
    a=((cloud[:,u]-lo[u])*scale+20).astype(int);b=(330-(cloud[:,v]-lo[v])*scale).astype(int);ok=(a>=0)&(a<700)&(b>35)&(b<350);canvas[b[ok],a[ok]]=color
   im.paste(Image.fromarray(canvas),(col*700,row*350));draw.text((col*700+10,row*350+10),f'{i}-{k} registered source '+('XY' if col==0 else 'ZY'),fill='white')
 im.save(D/'vertical-review.png');print([(r['pair'],[round(v['after']['median'],4) for v in r['directions']]) for r in out])
if __name__=='__main__':main()
