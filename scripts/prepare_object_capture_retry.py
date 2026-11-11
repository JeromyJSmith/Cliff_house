"""Preserve originals; qualify a continuous clip and annotate virtual camera EXIF."""
from pathlib import Path
import json, math, subprocess, os
from PIL import Image, TiffImagePlugin
from audit_november_video import OUT

root=OUT/'object-capture-clip035-v002'
root.mkdir(exist_ok=False)
inputs=root/'images';inputs.mkdir()
manifest=json.loads((OUT/'exterior-perspective-v001/manifest.json').read_text())
f=manifest['intrinsics'][0]
# A square virtual sensor with the same diagonal as 35mm film records the
# generated camera's known field of view, not physical capture focal length.
sensor_width=math.hypot(36,24)/math.sqrt(2)
focal_mm=f*sensor_width/1280
records=[]
for frame in manifest['frames']:
 if 'clip035-' not in Path(frame['source_frame']).name:continue
 for view in frame['views']:
  source=Path(view['file']);dest=inputs/source.name
  with Image.open(source) as im:
   exif=im.getexif();exif[271]='Derived perspective camera';exif[272]='Cliff House 80 degree virtual view'
   exif[34665]={37386:TiffImagePlugin.IFDRational(focal_mm),41989:round(focal_mm),41486:TiffImagePlugin.IFDRational(1280/sensor_width),41487:TiffImagePlugin.IFDRational(1280/sensor_width),41488:4,40962:1280,40963:1280}
   im.save(dest,quality=98,exif=exif)
  records.append({'source':str(source),'output':str(dest),'source_video':frame['source_video'],'timestamp_seconds':frame['timestamp_seconds'],'virtual_rotation_to_lens':view['virtual_rotation_to_lens']})
(root/'input-provenance.json').write_text(json.dumps({'reason':'First mixed-clip Apple run failed processError (-15) during alignment; retry one continuous exterior clip with explicit derived-camera focal metadata. Original videos and derivatives unchanged.','physical_scale':'unverified','focal_pixels':f,'virtual_focal_mm':focal_mm,'virtual_sensor_width_mm':sensor_width,'image_count':len(records),'images':records},indent=2))
storage=root/'execution-storage';storage.mkdir()
cmd=[str(OUT/'toolchain/reconstruct_photos'),'--input',str(inputs),'--output',str(root/'model'),'--checkpoint',str(root/'checkpoints'),'--log',str(root/'progress.jsonl')]
(root/'launch.json').write_text(json.dumps({'command':cmd,'TMPDIR':str(storage)},indent=2))
env=os.environ.copy();env['TMPDIR']=str(storage)
with (root/'console.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
(root/'exit.json').write_text(json.dumps({'returncode':r.returncode}))
print('RETURN',r.returncode,flush=True)
