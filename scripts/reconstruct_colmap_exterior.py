"""Native COLMAP sparse reconstruction of verified November10 dual-fisheye frames.
Persistent new run only; original sources and prior reconstruction products are read-only.
"""
import collections,hashlib,json,os,pathlib,subprocess,time
import cv2
import numpy as np
BASE=pathlib.Path('/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/november-capture-reconstruction-v001')
OUT=BASE/'colmap-exterior-v001'
COLMAP='/Users/jero/.pixi/bin/colmap'
MANIFEST=BASE/'exterior-perspective-v001/manifest.json'
NEIGHBORS=6
CROSS_CLIP_CANDIDATES=12

def main():
 OUT.mkdir(exist_ok=False);images=OUT/'images';images.mkdir();logs=OUT/'logs';logs.mkdir();storage=OUT/'execution-storage';storage.mkdir();sparse=OUT/'sparse';sparse.mkdir();commands=[]
 manifest=json.loads(MANIFEST.read_text());frames=manifest['frames'];calibration=manifest['source_lens_calibration'];names={};group=collections.defaultdict(list);desc={};sources=[]
 for lens in (0,1):(images/f'cam{lens}').mkdir()
 for f in frames:
  source=pathlib.Path(f['source_frame']);lens=f['video_stream'];name=f'cam{lens}/{source.name}';(images/name).symlink_to(source);names[source.name]=name;clip=source.stem.split('-')[0];group[clip,lens].append((f['timestamp_seconds'],name));sources.append({'image':name,'source_frame':str(source),'source_video':f['source_video'],'capture_date':f['embedded_capture_date'],'timestamp_seconds':f['timestamp_seconds'],'lens':lens,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
  im=cv2.imread(str(source));small=cv2.resize(im,(96,96));hsv=cv2.cvtColor(small,cv2.COLOR_BGR2HSV);hist=cv2.calcHist([hsv],[0,1],None,[24,8],[0,180,0,256]).ravel();hist/=max(np.linalg.norm(hist),1e-9);desc[name]=hist
 pairs=set()
 def add(a,b):
  if a!=b:pairs.add(tuple(sorted((a,b))))
 for key,items in group.items():
  items.sort()
  for i,(_,a) in enumerate(items):
   for _,b in items[i+1:i+1+NEIGHBORS]:add(a,b)
 for f in frames:
  source=pathlib.Path(f['source_frame']);a=names[source.name];lens=f['video_stream'];clip=source.stem.split('-')[0]
  other=sorted(group[clip,1-lens],key=lambda t:abs(t[0]-f['timestamp_seconds']))[:3]
  for _,b in other:add(a,b)
  candidates=[name for name in desc if name.split('/')[1].split('-')[0]!=clip]
  for b in sorted(candidates,key=lambda b:float(np.linalg.norm(desc[a]-desc[b])))[:CROSS_CLIP_CANDIDATES]:add(a,b)
 (OUT/'pairs.txt').write_text(''.join(f'{a} {b}\n' for a,b in sorted(pairs)))
 receipt={'source_manifest':str(MANIFEST),'sources':sources,'source_image_count':len(sources),'pairs':len(pairs),'pair_policy':f'same clip/lens next{NEIGHBORS} chronological; crosslens sameclip nearest3 time; eachimage{CROSS_CLIP_CANDIDATES} nearest HSV histogram candidates from otherclips. Histograms propose pairs only; native geometric verification decides matches.','calibration':calibration,'camera_model':'OPENCV_FISHEYE','cpu_threads':4,'no_measured_rig_baseline':True,'physical_scale':'unverified','commands':commands}
 (OUT/'provenance.json').write_text(json.dumps(receipt,indent=2))
 env=os.environ.copy();env['TMPDIR']=str(storage);env['OMP_NUM_THREADS']='4';env['OPENBLAS_NUM_THREADS']='4';env['VECLIB_MAXIMUM_THREADS']='4'
 def run(stage,args):
  cmd=[COLMAP,*args,'--log_target','stderr','--log_color','0'];start=time.time();path=logs/(stage+'.log')
  with path.open('x') as f:p=subprocess.run(cmd,cwd=OUT,env=env,stdout=f,stderr=subprocess.STDOUT)
  entry={'stage':stage,'command':cmd,'log':str(path),'seconds':time.time()-start,'returncode':p.returncode};commands.append(entry);(OUT/'commands.json').write_text(json.dumps(commands,indent=2));print(stage,p.returncode,round(entry['seconds'],1),flush=True);assert p.returncode==0,(stage,path)
 db=OUT/'database.db'
 for lens in (0,1):
  listing=OUT/f'cam{lens}-images.txt';listing.write_text(''.join(s['image']+'\n' for s in sources if s['lens']==lens))
  run(f'extract-cam{lens}',['feature_extractor','--database_path',str(db),'--image_path',str(images),'--image_list_path',str(listing),'--ImageReader.camera_model','OPENCV_FISHEYE','--ImageReader.single_camera_per_folder','1','--ImageReader.camera_params',','.join(map(str,calibration[str(lens)])),'--FeatureExtraction.num_threads','4','--FeatureExtraction.use_gpu','0','--FeatureExtraction.max_image_size','2400','--SiftExtraction.max_num_features','4096'])
 run('matching',['matches_importer','--database_path',str(db),'--match_list_path',str(OUT/'pairs.txt'),'--match_type','pairs','--FeatureMatching.num_threads','4','--FeatureMatching.use_gpu','0','--TwoViewGeometry.filter_stationary_matches','1'])
 run('mapping',['mapper','--database_path',str(db),'--image_path',str(images),'--output_path',str(sparse),'--Mapper.num_threads','4','--Mapper.ba_use_gpu','0','--Mapper.init_min_tri_angle','8','--Mapper.random_seed','0'])
 models=[]
 for model in sorted(sparse.iterdir()):
  if not model.is_dir():continue
  run('analyze-'+model.name,['model_analyzer','--path',str(model)]);txt=OUT/('model-'+model.name+'-text');txt.mkdir();run('text-'+model.name,['model_converter','--input_path',str(model),'--output_path',str(txt),'--output_type','TXT']);ply=OUT/('model-'+model.name+'.ply');run('ply-'+model.name,['model_converter','--input_path',str(model),'--output_path',str(ply),'--output_type','PLY']);models.append({'native':str(model),'text':str(txt),'ply':str(ply),'analysis':str(logs/('analyze-'+model.name+'.log'))})
 result={'models':models,'completed':bool(models),'physical_scale':'unverified','provenance':str(OUT/'provenance.json'),'commands':str(OUT/'commands.json')};(OUT/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 if not models:raise RuntimeError('No sparse model reconstructed; retained database and logs')
if __name__=='__main__':main()
