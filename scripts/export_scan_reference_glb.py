"""GLB point primitives: reference samples only; no inferred mesh or Gaussian splats."""
import json,struct,numpy as np
from register_shared_crops import D
from register_ten_scans import load,moved
from pathlib import Path

def main():
 if (D/'SOURCE_IDENTITY_REJECTED.md').exists():raise RuntimeError("Source identity rejected: these October scans are 401 Pearl, not Cliff House. Supply verified November 9–10 captures in a new run.")
 j=json.loads((D/'crops.json').read_text());sol=json.loads((D/'solution.json').read_text());doc={'asset':{'version':'2.0','generator':'Cliff House recorded rigid scan-reference export'},'scene':0,'scenes':[{'nodes':list(range(10))}],'nodes':[],'meshes':[],'buffers':[],'bufferViews':[],'accessors':[],'materials':[{'name':'Captured RGB','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1},'extensions':{'KHR_materials_unlit':{}}}],'extensionsUsed':['KHR_materials_unlit'],'extras':{'status':'PROVISIONAL registered reference; residual misalignment remains','scale':'captured source scale; independently unverified','coordinates':'unchanged registered scan 6 XYZ; Y appears vertical','evidence':str(D)}};binary=bytearray();bounds=[]
 def accessor(a,kind,component,normalized=False):
  while len(binary)%4:binary.append(0)
  off=len(binary);binary.extend(a.tobytes());vi=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':off,'byteLength':a.nbytes,'target':34962});ai=len(doc['accessors']);entry={'bufferView':vi,'componentType':component,'count':len(a),'type':kind}
  if normalized:entry['normalized']=True
  if component==5126:entry.update({'min':a.min(axis=0).tolist(),'max':a.max(axis=0).tolist()})
  doc['accessors'].append(entry);return ai
 for i,c in enumerate(j['sources'],1):
  a=load(Path(c['sample']));x=moved(a['xyz'],np.array(sol['transforms'][str(i)])).astype('<f4');rgb=np.column_stack([a['rgb'],np.full(len(a),255,dtype=np.uint8)]);pi=accessor(x,'VEC3',5126);ci=accessor(rgb,'VEC4',5121,True);name=f'Scan {i:02d} — provisional registered points';doc['meshes'].append({'name':name,'primitives':[{'attributes':{'POSITION':pi,'COLOR_0':ci},'mode':0,'material':0}]});doc['nodes'].append({'name':name,'mesh':i-1,'extras':{'scan_id':i,'source_sha256':c['source_sha256'],'sample_records':len(a)}});bounds.append([x.min(axis=0).tolist(),x.max(axis=0).tolist()])
 while len(binary)%4:binary.append(0)
 doc['buffers']=[{'byteLength':len(binary)}];js=json.dumps(doc,separators=(',',':')).encode();js+=b' '*((-len(js))%4);blob=struct.pack('<4sII',b'glTF',2,12+8+len(js)+8+len(binary))+struct.pack('<I4s',len(js),b'JSON')+js+struct.pack('<I4s',len(binary),b'BIN\0')+binary
 p=D/'Cliff-House-provisional-point-reference.glb';p.open('xb').write(blob);(D/'glb-reference.json').write_text(json.dumps({'path':str(p),'bytes':len(blob),'points':2000000,'scan_nodes':10,'primitive':'POINTS','bounds_by_scan':bounds,'no_solid_surfaces_created':True},indent=2));print(p,len(blob))
if __name__=='__main__':main()
