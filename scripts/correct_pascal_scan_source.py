"""Remove only our misidentified 401 scan reference from the Cliff House project."""
import subprocess,json,pathlib
O=pathlib.Path('/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/shared-crop-registration-v002')
if (O/'pascal-removal-verified.json').exists():raise RuntimeError('Correction already completed; do not repeat deletion.')
p=subprocess.Popen(['/Users/jero/.local/bin/pascal','mcp','connect'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
def rpc(i,method,params):
 p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n');p.stdin.flush()
 while True:
  line=p.stdout.readline()
  if not line:raise RuntimeError('MCP closed')
  try:r=json.loads(line)
  except ValueError:continue
  if r.get('id')==i:return r
n=1
rpc(n,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'cliff-source-correction','version':'1'}});p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
def tool(name,args):
 global n
 n+=1;r=rpc(n,'tools/call',{'name':name,'arguments':args});(O/f'pascal-correction-{n}-{name}.json').write_text(json.dumps(r,indent=2));v=r.get('result',{});assert not v.get('isError'),v
 return v.get('structuredContent') or json.loads(v['content'][0]['text'])
try:
 print('loaded',tool('load_scene',{'id':'e23412a87765'}));scene=tool('get_scene',{});nodes=[v for v in scene['nodes'].values() if v.get('type')=='scan' and v.get('name')=='Cliff-House-provisional-point-reference'];assert len(nodes)==1,nodes;print('target',nodes[0]);print('deleted',tool('delete_node',{'id':nodes[0]['id']}));print('saved',tool('save_scene',{'name':'Cliff House — present-day scan reference','saveMode':'checkpoint'}));print('status',tool('get_project_status',{'id':'e23412a87765'}));after=tool('get_scene',{});assert not any(v.get('type')=='scan' for v in after['nodes'].values())
finally:p.stdin.close();p.terminate()
