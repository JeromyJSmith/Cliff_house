"""Project registered fisheye cameras into calibrated pinhole views for OpenMVS.
No new camera solve, point triangulation, physical scale or geometry is invented.
"""
import argparse,json,os,pathlib
import cv2,numpy as np,pycolmap
from scipy.spatial.transform import Rotation

def main():
 a=argparse.ArgumentParser();a.add_argument('--model',required=True);a.add_argument('--images',required=True);a.add_argument('--output',required=True);a=a.parse_args()
 out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=False);dst=out/'images';dst.mkdir();sparse=out/'sparse';sparse.mkdir()
 recon=pycolmap.Reconstruction(a.model);size=1280;focal=size/(2*np.tan(np.deg2rad(40)));c=(size-1)/2
 yy,xx=np.mgrid[:size,:size];rays=np.stack([(xx-c)/focal,(yy-c)/focal,np.ones_like(xx)],axis=-1)
 views=[];tracks={};maps={};image_id=0;calibration_limits={}
 for native_id,im in sorted(recon.images.items()):
  cam=recon.cameras[im.camera_id];pose=im.cam_from_world();R=pose.rotation.matrix();t=pose.translation
  source=pathlib.Path(a.images)/im.name;pixels=cv2.imread(str(source));assert pixels is not None
  for az in (0,90,180):
   V=Rotation.from_euler('z',az,degrees=True).as_matrix()@Rotation.from_euler('y',80,degrees=True).as_matrix()
   key=(im.camera_id,az)
   if key not in maps:
    assert cam.model_name=='OPENCV_FISHEYE',cam.model_name
    # COLMAP img_from_cam rejects rays behind the native lens plane. These
    # >180deg captures still record those rays: use the calibrated equidistant
    # polynomial with atan2 so the lower facade is not replaced by black.
    native_rays=rays@V.T;rho=np.linalg.norm(native_rays[...,:2],axis=-1);theta=np.arctan2(rho,native_rays[...,2])
    fx,fy,cx,cy,*ks=cam.params;td=theta*(1+sum(k*theta**(2*(n+1)) for n,k in enumerate(ks)))
    samples=np.linspace(0,1.9,2000);derivative=1+sum((2*n+3)*k*samples**(2*(n+1)) for n,k in enumerate(ks))
    invalid=np.where(derivative<=0)[0];limit=float(samples[invalid[0]]) if len(invalid) else 1.9
    # Never extrapolate a nonmonotonic fitted model beyond its front hemisphere.
    if len(invalid):limit=min(limit,np.pi/2)
    calibration_limits[str(im.camera_id)]={'max_projection_angle_radians':limit,'monotonic_to_1_9_rad':not bool(len(invalid)),'params':cam.params.tolist()}
    uv=np.stack([fx*native_rays[...,0]/np.maximum(rho,1e-12)*td+cx,fy*native_rays[...,1]/np.maximum(rho,1e-12)*td+cy],axis=-1).astype('float32')
    valid=(theta<limit)&(uv[...,0]>=0)&(uv[...,0]<cam.width-1)&(uv[...,1]>=0)&(uv[...,1]<cam.height-1)
    uv[~valid]=-1;maps[key]=(uv,valid)
   uv,valid_pixels=maps[key];view=cv2.remap(pixels,uv[:,:,0],uv[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
   rv=V.T@R;tv=V.T@t;observations=[]
   for p2 in im.points2D:
    if not p2.has_point3D():continue
    pid=p2.point3D_id;X=rv@recon.points3D[pid].xyz+tv
    if X[2]<=0:continue
    u,v=focal*X[:2]/X[2]+c
    if 0<=u<size and 0<=v<size and valid_pixels[int(v),int(u)]:observations.append((float(u),float(v),int(pid)))
   if len(observations)<8:continue
   image_id+=1;name=f'{native_id:05d}-az{az:03d}.jpg';assert cv2.imwrite(str(dst/name),view,[cv2.IMWRITE_JPEG_QUALITY,95])
   cv2.imwrite(str(dst/(pathlib.Path(name).stem+'.mask.png')),valid_pixels.astype('uint8')*255)
   quat=Rotation.from_matrix(rv).as_quat();q=[quat[3],*quat[:3]]
   for idx,(_,_,pid) in enumerate(observations):tracks.setdefault(pid,[]).append((image_id,idx,native_id))
   views.append({'id':image_id,'name':name,'q':q,'t':tv.tolist(),'observations':observations,'native_image':im.name,'native_id':native_id,'virtual_to_native':V.tolist()})
 # Require two original capture images, not merely virtual rotations at one center.
 valid={pid for pid,track in tracks.items() if len({v[2] for v in track})>=2}
 with (sparse/'cameras.txt').open('x') as h:h.write(f'1 PINHOLE {size} {size} {focal} {focal} {c} {c}\n')
 with (sparse/'images.txt').open('x') as h:
  for v in views:
   h.write(' '.join(map(str,[v['id'],*v['q'],*v['t'],1,v['name']]))+'\n')
   h.write(' '.join(f'{x} {y} {pid if pid in valid else -1}' for x,y,pid in v['observations'])+'\n')
 with (sparse/'points3D.txt').open('x') as h:
  for pid in sorted(valid):
   p=recon.points3D[pid];track=tracks[pid]
   h.write(' '.join(map(str,[pid,*p.xyz,*p.color,p.error]))+' '+' '.join(f'{i} {j}' for i,j,_ in track)+'\n')
 (out/'provenance.json').write_text(json.dumps({'source_model':a.model,'source_images':a.images,'projection':'PINHOLE 1280 square 80deg FOV, virtual rotation80deg tilt, az0/90/180','scale':'unchanged arbitrary SfM units, physical scale unverified','calibration_projection_limits':calibration_limits,'visibility_observations':'projected existing3Dpoints into virtual views; not new measured feature residuals','points':len(valid),'virtual_images':len(views),'views':[{k:v for k,v in x.items() if k!='observations'} for x in views]},indent=2))
 # Read back using COLMAP library to verify the camera/track text is valid.
 check=pycolmap.Reconstruction(str(sparse));assert check.num_reg_images()==len(views);assert check.num_points3D()==len(valid)
 print(json.dumps({'images':len(views),'points':len(valid),'output':str(out)}))
if __name__=='__main__':main()
