"""Non-destructive deterministic point-cloud overlap diagnostic, not registration.
Samples source-order records, preserves RGB, computes source-frame distances, hashes originals.
Distances are in unverified source coordinate units; no physical-accuracy claims.
"""
import argparse,hashlib,json,pathlib,time
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw
DTYPE=np.dtype([('xyz','<f4',(3,)),('rgb','u1',(3,))])
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def main(root,out):
 out.mkdir(parents=True,exist_ok=False);clouds=[];points=[];colors=[]
 for p in sorted(root.glob('*.ply'),key=lambda p:int(p.stem.split('_')[-1])):
  before=p.stat()
  with p.open('rb') as f:
   header=b''
   while not header.endswith(b'end_header\n'):
    line=f.readline()
    if not line:raise ValueError('Missing header terminator')
    header+=line
  text=header.decode();expected=['property float x','property float y','property float z','property uchar red','property uchar green','property uchar blue']
  assert [x for x in text.splitlines() if x.startswith('property ')]==expected
  assert 'format binary_little_endian 1.0' in text
  n=int(next(x for x in text.splitlines() if x.startswith('element vertex ')).split()[-1]);assert before.st_size==len(header)+n*15
  mm=np.memmap(p,dtype=DTYPE,mode='r',offset=len(header),shape=(n,));idx=np.linspace(0,n-1,min(200000,n),dtype=np.int64);sample=np.array(mm[idx]);del mm
  assert np.isfinite(sample['xyz']).all()
  target=out/(p.stem.replace(' ','_')+'-sample.ply');blob=(f'ply\nformat binary_little_endian 1.0\ncomment deterministic source-order sample for diagnostics; units unverified\nelement vertex {len(sample)}\n'+'\n'.join(expected)+'\nend_header\n').encode()+sample.tobytes();target.write_bytes(blob)
  sha=digest(p);after=p.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
  points.append(sample['xyz'].astype(np.float64));colors.append(sample['rgb']);clouds.append({'source':str(p),'source_sha256':sha,'bytes':before.st_size,'source_mtime_ns':before.st_mtime_ns,'source_vertices':n,'sample':str(target),'sample_sha256':hashlib.sha256(blob).hexdigest(),'sample_vertices':len(sample),'sampling':'200000 equally spaced source record indices including endpoints','units':'unverified source coordinate units'})
  print('Sampled and hashed',p.name,flush=True)
 thresholds=[0.02,0.05,0.1,0.25];trees=[cKDTree(x) for x in points];pairs=[]
 for i,pts in enumerate(points):
  check=pts[::4]
  for j,tree in enumerate(trees):
   if i==j:continue
   d,_=tree.query(check,workers=2)
   pairs.append({'data':i+1,'reference':j+1,'query_points':len(check),'median_nn':float(np.median(d)),'p90_nn':float(np.quantile(d,.9)),'p95_nn':float(np.quantile(d,.95)),'fraction_within':{str(t):float(np.mean(d<=t)) for t in thresholds}})
 result={'source_root':str(root),'clouds':clouds,'pairs':pairs,'registration_performed':False,'scale_verified':False,'warning':'Distances are sampled original-frame nearest-neighbor distances in unverified source units. Shared coordinates, overlap and nearest points do not establish independent measured accuracy or scan uniqueness.'}
 (out/'overlap.json').write_text(json.dumps(result,indent=2)+'\n')
 # Three projections keep source axes unchanged; common framing across all clouds.
 size=(460,240);margin=15;sheet=Image.new('RGB',(size[0]*3,size[1]*len(points)),(20,23,28));draw=ImageDraw.Draw(sheet)
 allpts=np.concatenate(points);lims=np.quantile(allpts,[.002,.998],axis=0)
 for row,(pts,rgb) in enumerate(zip(points,colors)):
  for col,(a,b,label) in enumerate([(0,2,'XZ'),(0,1,'XY'),(2,1,'ZY')]):
   xy=pts[::3][:,[a,b]];lo=lims[0,[a,b]];hi=lims[1,[a,b]];scale=min((size[0]-2*margin)/(hi[0]-lo[0]),(size[1]-35)/(hi[1]-lo[1]));x=((xy[:,0]-lo[0])*scale+margin).astype(int);y=(size[1]-15-(xy[:,1]-lo[1])*scale).astype(int)
   good=(x>=0)&(x<size[0])&(y>=25)&(y<size[1]);canvas=np.full((size[1],size[0],3),[20,23,28],np.uint8);canvas[y[good],x[good]]=rgb[::3][good];sheet.paste(Image.fromarray(canvas),(col*size[0],row*size[1]));draw.text((col*size[0]+10,row*size[1]+5),f'Scan {row+1}: source {label}, common framing',fill='white')
 sheet.save(out/'source-projections.jpg',quality=90)
 print(json.dumps({'overlap_report':str(out/'overlap.json'),'preview':str(out/'source-projections.jpg'),'pair_1_to_2':pairs[0]},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-root',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();main(a.source_root.resolve(),a.output.resolve())
