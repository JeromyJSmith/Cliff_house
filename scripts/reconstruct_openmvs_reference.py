"""Persistently reconstruct a provisional surface from qualified registered views."""
import argparse,json,pathlib,subprocess,time,os
BIN=pathlib.Path('/Users/jero/Developer/tools/openmvs/v2.4.0')
def main():
 p=argparse.ArgumentParser();p.add_argument('--views',required=True);p.add_argument('--output',required=True);a=p.parse_args();views=pathlib.Path(a.views);out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();(out/'execution-storage').mkdir();env=os.environ.copy();env['TMPDIR']=str(out/'execution-storage');commands=[]
 def run(name,args):
  cmd=[str(BIN/name),*map(str,args),'--max-threads','8'];start=time.time();log=out/'logs'/(name+'.log')
  with log.open('x') as f:r=subprocess.run(cmd,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT)
  commands.append({'command':cmd,'returncode':r.returncode,'seconds':time.time()-start,'log':str(log)});(out/'commands.json').write_text(json.dumps(commands,indent=2));print(name,r.returncode,flush=True)
  if r.returncode:raise RuntimeError(f'{name} failed; preserved {log}')
 run('InterfaceCOLMAP',['-i',views,'--image-folder',views/'images','-o',out/'scene.mvs'])
 run('DensifyPointCloud',['-i',out/'scene.mvs','-o',out/'dense.mvs','--resolution-level','1','--max-resolution','1280','--min-resolution','640','--number-views','5','--number-views-fuse','3','--ignore-mask-label','0','--tower-mode','0','--remove-dmaps','0','--estimate-roi','0','--crop-to-roi','0'])
 run('ReconstructMesh',['-i',out/'dense.mvs','-o',out/'mesh.mvs','--close-holes','0','--smooth','0','--crop-to-roi','0','--target-face-num','300000'])
 run('TextureMesh',['-i',out/'mesh.mvs','-o',out/'textured.mvs','--export-type','obj','--close-holes','0','--ignore-mask-label','0','--max-texture-size','4096'])
 (out/'result.json').write_text(json.dumps({'status':'completed; visual and geometric review required before import','views':str(views),'physical_scale':'unverified','automatic_hole_filling':False,'outputs':[str(x) for x in out.iterdir() if x.is_file()]},indent=2))
if __name__=='__main__':main()
