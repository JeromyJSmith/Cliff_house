"""Verify embedded capture dates and create traceable video contact sheets."""
import json,pathlib,subprocess,datetime,zoneinfo,concurrent.futures
from PIL import Image,ImageDraw
ROOT=pathlib.Path('/Users/jero/Desktop/frasier/Cliff House')
OUT=ROOT/'Mapping Evidence/2026-11-11/november-capture-reconstruction-v001'
def main():
 OUT.mkdir(exist_ok=False);(OUT/'contact-frames').mkdir();sources=sorted(ROOT.glob('*.insv'))+sorted((ROOT/'Cliff_house repository/input').glob('*.insv'));records=[]
 for p in sources:
  r=subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(p)],capture_output=True,text=True,check=True);meta=json.loads(r.stdout);stamp=meta['format']['tags']['creation_time'];dt=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00')).astimezone(zoneinfo.ZoneInfo('America/Denver'));assert dt.date().isoformat() in {'2026-11-09','2026-11-10'},(p,dt);records.append({'source':str(p),'bytes':p.stat().st_size,'capture_time_embedded':stamp,'capture_time_denver':dt.isoformat(),'duration':float(meta['format']['duration']),'video_streams':[{'index':x['index'],'width':x.get('width'),'height':x.get('height')} for x in meta['streams'] if x['codec_type']=='video'],'probe':meta})
 (OUT/'capture-provenance.json').write_text(json.dumps(records,indent=2));jobs=[]
 for rec in records:
  for lens in (0,1):
   for frac in (.12,.48,.82):jobs.append((rec,lens,frac))
 def frame(job):
  rec,lens,frac=job;t=rec['duration']*frac;p=pathlib.Path(rec['source']);out=OUT/'contact-frames'/f'{p.stem}-lens{lens}-{frac}.jpg';cmd=['ffmpeg','-nostdin','-v','error','-ss',str(t),'-i',str(p),'-map',f'0:v:{lens}','-frames:v','1','-vf','scale=400:400','-q:v','3','-n',str(out)];subprocess.run(cmd,check=True,capture_output=True);return {'source':rec['source'],'lens':lens,'seconds':t,'image':str(out),'command':cmd}
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:frames=list(pool.map(frame,jobs))
 (OUT/'contact-frame-provenance.json').write_text(json.dumps(frames,indent=2))
 for page in range(3):
  subset=records[page*3:(page+1)*3];sheet=Image.new('RGB',(1200,860*len(subset)),(18,20,25));draw=ImageDraw.Draw(sheet)
  for row,rec in enumerate(subset):
   fr=[f for f in frames if f['source']==rec['source']]
   for n,f in enumerate(fr):
    x=n%3*400;y=row*860+(n//3)*430;sheet.paste(Image.open(f['image']),(x,y+30));draw.text((x+5,y+5),f"{pathlib.Path(rec['source']).stem[-3:]} lens{f['lens']} {f['seconds']:.1f}s",fill='white')
  sheet.save(OUT/f'coverage-{page+1}.jpg',quality=92)
 print(json.dumps([{k:v for k,v in r.items() if k!='probe'} for r in records],indent=2))
if __name__=='__main__':main()
