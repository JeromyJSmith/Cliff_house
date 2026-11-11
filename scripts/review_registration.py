"""Compare source, direct ICP and overlap graph on reserved points and sections."""
import json
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw
from register_ten_scans import OUT,load,moved
from verify_cloudcompare_pilot import stats
from refine_registration_graph import DEST

def main():
 audit=json.loads((OUT/'registration.json').read_text());graph=json.loads((DEST/'graph.json').read_text());original=[load(__import__('pathlib').Path(c['sample']))[::4]['xyz'].astype(float) for c in audit['sources']]
 variants={'source':original,'direct':[moved(x,np.array(audit['transforms'][str(i)])) for i,x in enumerate(original,1)],'graph':[moved(x,np.array(graph['transforms'][str(i)])) for i,x in enumerate(original,1)]};results={}
 for name,pts in variants.items():
  trees=[cKDTree(x) for x in pts];pairs=[]
  for i in range(10):
   for k in range(i+1,10):
    d=np.r_[trees[k].query(pts[i],workers=2)[0],trees[i].query(pts[k],workers=2)[0]];trim=d[d<.25];pairs.append({'pair':[i+1,k+1],'all':stats(d),'overlap':float(np.mean(d<.25)),'overlap_stats':stats(trim)})
  results[name]=pairs
 (DEST/'comparison.json').write_text(json.dumps(results,indent=2))
 colors=[(255,80,80),(255,160,40),(250,230,70),(120,220,70),(40,210,160),(30,190,250),(100,120,255),(210,100,250),(250,100,180),(240,240,240)]
 sheet=Image.new('RGB',(1800,1200),(15,18,23));draw=ImageDraw.Draw(sheet);allpts=np.concatenate(original);lo,hi=np.quantile(allpts,[.005,.995],axis=0)
 for col,(name,pts) in enumerate(variants.items()):
  for row,(u,v,title) in enumerate([(0,2,'XZ'),(0,1,'XY'),(2,1,'ZY')]):
   canvas=np.full((400,600,3),[15,18,23],np.uint8);scale=min(560/(hi[u]-lo[u]),350/(hi[v]-lo[v]))
   for i,p in enumerate(pts):
    x=((p[:,u]-lo[u])*scale+20).astype(int);y=(380-(p[:,v]-lo[v])*scale).astype(int);ok=(x>=0)&(x<600)&(y>30)&(y<400);canvas[y[ok],x[ok]]=colors[i]
   sheet.paste(Image.fromarray(canvas),(col*600,row*400));draw.text((col*600+12,row*400+10),f'{name.upper()} source {title}; colors identify scans',fill='white')
 sheet.save(DEST/'comparison.jpg',quality=95)
 print('cycle',[(x['pair'],round(x['cycle']['median'],4)) for x in graph.get('reciprocal_checks',[])]);print('mean pair overlap',[(n,round(np.mean([p['overlap'] for p in v]),3)) for n,v in results.items()])
if __name__=='__main__':main()
