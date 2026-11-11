"""Verify saved rigid registration matrix on held-out sampled records and plot overlays."""
import argparse,hashlib,json,pathlib
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw
from run_cloudcompare_pilot import load,save

def stats(d):return {'median':float(np.median(d)),'p90':float(np.quantile(d,.9)),'p95':float(np.quantile(d,.95)),'rms':float(np.sqrt(np.mean(d*d)))}
def main(root):
 matrices=list(root.glob('*REGISTRATION_MATRIX*.txt'));assert len(matrices)==1
 matrix=np.loadtxt(matrices[0]);assert matrix.shape==(4,4) and np.isfinite(matrix).all();r=matrix[:3,:3];det=float(np.linalg.det(r));ortho=float(np.max(np.abs(r.T@r-np.eye(3))))
 assert abs(det-1)<1e-4 and ortho<1e-4 and np.allclose(matrix[3],[0,0,0,1])
 a=load(root/'data-holdout.ply');b=load(root/'reference-holdout.ply');x=a['xyz'].astype(float);y=b['xyz'].astype(float);moved=x@r.T+matrix[:3,3];tree=cKDTree(y);before,_=tree.query(x,workers=2);after,_=tree.query(moved,workers=2);common=before<=.25
 allref=load(root/'reference-train.ply');revbefore,_=cKDTree(x).query(y,workers=2);revafter,_=cKDTree(moved).query(y,workers=2)
 result={'matrix_path':str(matrices[0]),'matrix_sha256':hashlib.sha256(matrices[0].read_bytes()).hexdigest(),'matrix_data_to_reference':matrix.tolist(),'rotation_determinant':det,'rotation_orthogonality_max_error':ortho,'translation_source_units':matrix[:3,3].tolist(),'rotation_degrees':float(np.degrees(np.arccos(np.clip((np.trace(r)-1)/2,-1,1)))),'held_out_data_points':len(x),'held_out_reference_points':len(y),'before':stats(before),'after':stats(after),'reverse_before':stats(revbefore),'reverse_after':stats(revafter),'fixed_before_overlap_mask':{'definition':'before distance <=0.25 unverified source units','points':int(common.sum()),'before':stats(before[common]),'after':stats(after[common])},'measured_physical_accuracy':'unverified','note':'Held-out source-order samples test the local fit, not independent survey control. Dense neighboring samples and shared sensor drift can remain correlated. Scale is unchanged. No full-resolution merge or scene registration to images was performed.'}
 assert result['after']['median']<result['before']['median'],'Pilot did not improve held-out median'
 out=root/'verification.json';assert not out.exists();out.write_text(json.dumps(result,indent=2)+'\n');new=a.copy();new['xyz']=moved.astype('<f4');save(root/'data-holdout-aligned.ply',new)
 # Cyan reference / magenta moving cloud, before and after, source axes unchanged.
 sheet=Image.new('RGB',(1400,700),(20,23,28));draw=ImageDraw.Draw(sheet)
 for row,(u,v,name) in enumerate([(0,1,'source XY'),(2,1,'source ZY')]):
  lo=np.quantile(np.concatenate([x,y]),.002,axis=0)[[u,v]];hi=np.quantile(np.concatenate([x,y]),.998,axis=0)[[u,v]];scale=min(660/(hi[0]-lo[0]),300/(hi[1]-lo[1]))
  for col,(pts,title) in enumerate([(x,'BEFORE'),(moved,'AFTER')]):
   canvas=np.full((350,700,3),[20,23,28],np.uint8)
   for xyz,color in [(y,(35,200,220)),(pts,(235,65,160))]:
    xx=((xyz[:,u]-lo[0])*scale+20).astype(int);yy=(335-(xyz[:,v]-lo[1])*scale).astype(int);ok=(xx>=0)&(xx<700)&(yy>=30)&(yy<350);canvas[yy[ok],xx[ok]]=color
   sheet.paste(Image.fromarray(canvas),(col*700,row*350));draw.text((col*700+15,row*350+10),f'{title}: {name}. Cyan scan 6; magenta scan 7',fill='white')
 sheet.save(root/'registration-holdout-overlay.jpg',quality=93)
 print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('pilot',type=pathlib.Path);main(p.parse_args().pilot.resolve())
