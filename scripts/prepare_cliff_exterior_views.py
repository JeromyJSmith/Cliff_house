"""Traceable pinhole views from verified November10 dual-fisheye captures.
Uses existing estimated lens calibration; does not stitch frames or infer geometry.
"""
import pathlib,json,subprocess,concurrent.futures
import numpy as np
import cv2
from audit_november_video import OUT

def main():
 dest=OUT/'exterior-perspective-v001';dest.mkdir(exist_ok=False);raw=dest/'source-frames';raw.mkdir();images=dest/'images';images.mkdir();records=json.loads((OUT/'capture-provenance.json').read_text());cameras={};lines=(OUT/'calibration-041/cameras.txt').read_text().splitlines()
 for line in lines:
  if not line or line.startswith('#'):continue
  f=line.split();cameras[int(f[0])-1]=np.array([float(x) for x in f[4:]])
 # Fixed ranges selected from inspected coverage; exclude interiors and the operator-facing azimuth.
 selections={'035':[(90,226,4)],'038':[(0,100,4)],'037':[(0,13,3),(50,75,4)],'040':[(0,22,3)]};jobs=[]
 for rec in records:
  clip=pathlib.Path(rec['source']).stem[-3:]
  for start,end,step in selections.get(clip,[]):
   for t in range(start,end,step):
    for lens in (0,1):jobs.append((rec,clip,t,lens))
 size=1280;focal=size/(2*np.tan(np.deg2rad(40)));yy,xx=np.mgrid[:size,:size];rays=np.stack([(xx-(size-1)/2)/focal,(yy-(size-1)/2)/focal,np.ones_like(xx)],axis=-1);theta=np.deg2rad(60);ry=np.array([[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta),0,np.cos(theta)]]);maps={}
 for lens,params in cameras.items():
  fx,fy,cx,cy,*ks=params
  for az in (0,90,180):
   phi=np.deg2rad(az);rz=np.array([[np.cos(phi),-np.sin(phi),0],[np.sin(phi),np.cos(phi),0],[0,0,1]]);r=rz@ry;v=rays@r.T;rho=np.linalg.norm(v[...,:2],axis=-1);a=np.arctan2(rho,v[...,2]);ad=a*(1+sum(k*a**(2*(n+1)) for n,k in enumerate(ks)));mx=(fx*v[...,0]/np.maximum(rho,1e-12)*ad+cx).astype('float32');my=(fy*v[...,1]/np.maximum(rho,1e-12)*ad+cy).astype('float32');maps[lens,az]=(mx,my,r)
 def extract(job):
  rec,clip,t,lens=job;file=raw/f'clip{clip}-t{t:04d}-lens{lens}.jpg';cmd=['ffmpeg','-nostdin','-v','error','-ss',str(t),'-i',rec['source'],'-map',f'0:v:{lens}','-frames:v','1','-q:v','2','-n',str(file)];subprocess.run(cmd,check=True,capture_output=True);im=cv2.imread(str(file));views=[]
  for az in (0,90,180):
   mx,my,r=maps[lens,az];view=cv2.remap(im,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT);path=images/f'clip{clip}-t{t:04d}-lens{lens}-az{az:03d}.jpg';assert cv2.imwrite(str(path),view,[cv2.IMWRITE_JPEG_QUALITY,95]);views.append({'file':str(path),'virtual_rotation_to_lens':r.tolist(),'lens_azimuth_degrees':az})
  print(clip,t,lens,flush=True);return {'source_video':rec['source'],'embedded_capture_date':rec['capture_time_denver'],'timestamp_seconds':t,'video_stream':lens,'source_frame':str(file),'views':views,'extraction_command':cmd}
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:frames=list(pool.map(extract,jobs))
 manifest={'status':'verified Nov10 video, calibrated perspective derivatives; calibration transferred from existing clip041 estimate and not independently calibrated','image_count':len(frames)*3,'camera_model':'PINHOLE','image_size':[size,size],'intrinsics':[float(focal),float(focal),(size-1)/2,(size-1)/2],'source_lens_calibration':{str(k):v.tolist() for k,v in cameras.items()},'operator_avoidance':'omit azimuth270 view; not a full person segmentation','frames':frames};(dest/'manifest.json').write_text(json.dumps(manifest,indent=2));print('COMPLETE',len(frames)*3,flush=True)
if __name__=='__main__':main()
