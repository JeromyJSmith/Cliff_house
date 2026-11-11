"""Persistent CloudCompare rigid registrations and independent overlap checks.
No original writes. All transforms map data into unchanged scan 6 coordinates.
"""
import json,pathlib,subprocess,time,sys
import numpy as np
from scipy.spatial import cKDTree
from run_cloudcompare_pilot import load,save
from verify_cloudcompare_pilot import stats
ROOT=pathlib.Path('/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11')
AUDIT=ROOT/'cloudcompare-assessment-v001/point-cloud-audit/overlap.json'
OUT=ROOT/'ten-scan-registration-v001'
def moved(x,m):return x@m[:3,:3].T+m[:3,3]
def main():
 OUT.mkdir(exist_ok=False);j=json.loads(AUDIT.read_text());clouds=j['clouds'];samples=[load(pathlib.Path(c['sample'])) for c in clouds];train=[];hold=[]
 for i,a in enumerate(samples,1):
  mask=np.arange(len(a))%4!=0;train.append(a[mask]);hold.append(a[~mask]['xyz'].astype(float));save(OUT/f'scan-{i}-train.ply',a[mask])
 transforms={6:np.eye(4)};runs=[]
 pairs=[(i,6) for i in range(1,11) if i!=6]+[(6,i) for i in range(1,11) if i!=6]
 for data,ref in pairs:
  run=OUT/f'fit-{data}-to-{ref}';run.mkdir();save(run/'data.ply',train[data-1]);save(run/'reference.ply',train[ref-1])
  cmd=['/Users/jero/.local/bin/CloudCompare','-SILENT','-AUTO_SAVE','OFF','-O',str(run/'data.ply'),'-O',str(run/'reference.ply'),'-ICP','-ITER','60','-OVERLAP','80','-RANDOM_SAMPLING_LIMIT','200000'];start=time.time();p=subprocess.run(cmd,cwd=run,capture_output=True,text=True,timeout=180);(run/'cloudcompare.log').write_text(p.stdout+'\n'+p.stderr);assert p.returncode==0
  files=list(run.glob('*REGISTRATION_MATRIX*.txt'));assert len(files)==1;m=np.loadtxt(files[0]);assert np.isfinite(m).all() and np.allclose(m[:3,:3].T@m[:3,:3],np.eye(3),atol=1e-5) and abs(np.linalg.det(m[:3,:3])-1)<1e-5
  tree=cKDTree(hold[ref-1]);before=tree.query(hold[data-1],workers=2)[0];after=tree.query(moved(hold[data-1],m),workers=2)[0];mask=before<.25
  r={'data':data,'reference':ref,'matrix':m.tolist(),'command':cmd,'seconds':time.time()-start,'before':stats(before),'after':stats(after),'fixed_overlap_count':int(mask.sum()),'fixed_overlap_before':stats(before[mask]),'fixed_overlap_after':stats(after[mask])};runs.append(r)
  if ref==6:transforms[data]=m
  (run/'result.json').write_text(json.dumps(r,indent=2));print(data,ref,'median',r['before']['median'],r['after']['median'],flush=True)
 transformed=[moved(x,transforms[i+1]) for i,x in enumerate(hold)];trees=[cKDTree(x) for x in hold];newtrees=[cKDTree(x) for x in transformed];checks=[]
 for i in range(10):
  for k in range(i+1,10):
   b=np.concatenate([trees[k].query(hold[i],workers=2)[0],trees[i].query(hold[k],workers=2)[0]]);a=np.concatenate([newtrees[k].query(transformed[i],workers=2)[0],newtrees[i].query(transformed[k],workers=2)[0]]);mask=b<.25
   checks.append({'pair':[i+1,k+1],'before':stats(b),'after':stats(a),'fixed_overlap_before':stats(b[mask]),'fixed_overlap_after':stats(a[mask]),'overlap_before_at_025':float(np.mean(b<.25)),'overlap_after_at_025':float(np.mean(a<.25))})
 reciprocal=[]
 for r in runs[9:]:
  i=r['reference'];cycle=transforms[i]@np.array(r['matrix']);d=np.linalg.norm(moved(hold[5],cycle)-hold[5],axis=1);reciprocal.append({'scan':i,'cycle_displacement':stats(d)})
 report={'reference_scan':6,'source_audit':str(AUDIT),'sources':clouds,'transforms':{str(k):v.tolist() for k,v in transforms.items()},'runs':runs,'pair_checks':checks,'reciprocal_checks':reciprocal,'units':'unverified source units','scale_adjusted':False,'merged':False};(OUT/'registration.json').write_text(json.dumps(report,indent=2))
 for i,a in enumerate(samples,1):
  a=a.copy();a['xyz']=moved(a['xyz'],transforms[i]);save(OUT/f'scan-{i}-aligned-sample.ply',a)
 print('COMPLETE',OUT,flush=True)
if __name__=='__main__':main()
