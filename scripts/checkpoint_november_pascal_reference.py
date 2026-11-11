"""Verify and checkpoint only the importedNovember reference in Cliff House."""
import subprocess,json,pathlib
O=pathlib.Path('/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/november-capture-reconstruction-v001/lodge-reference-review-v002')
assert not(O/'pascal-checkpoint-verified.json').exists(),'Alreadycheckpointed'
p=subprocess.Popen(['/Users/jero/.local/bin/pascal','mcp','connect'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
def rpc(i,method,params):
 p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n');p.stdin.flush()
 while True:
  line=p.stdout.readline()
  if not line:raise RuntimeError('MCPclosed')
  try:r=json.loads(line)
  except ValueError:continue
  if r.get('id')==i:return r
n=1
rpc(n,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'cliff-november-reference','version':'1'}});p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
def tool(name,args):
 global n
 n+=1;r=rpc(n,'tools/call',{'name':name,'arguments':args});(O/f'pascal-{n}-{name}.json').write_text(json.dumps(r,indent=2));v=r.get('result',{});assert not v.get('isError'),v
 return v.get('structuredContent') or json.loads(v['content'][0]['text'])
try:
 loaded=tool('load_scene',{'id':'e23412a87765'});scene=tool('get_scene',{});scans=[v for v in scene['nodes'].values() if v.get('type')=='scan'];assert len(scans)==1,scans;assert scans[0]['name']=='Cliff-House-Nov10-partial-reference',scans
 verify=tool('verify_scene',{});print('verify',verify)
 saved=tool('save_scene',{'name':'Cliff House — present-day scan reference','saveMode':'checkpoint','expectedVersion':loaded['version']});status=tool('get_project_status',{'id':'e23412a87765'});after=tool('get_scene',{});assert scans[0]['id'] in after['nodes']
 receipt={'saved':saved,'status':status,'scan':scans[0],'verification':verify,'source':'VerifiedNov10clip035t140–162, partialreference, physicalscaleunverified','other_projects_modified':False};(O/'pascal-checkpoint-verified.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
finally:p.stdin.close();p.terminate()
