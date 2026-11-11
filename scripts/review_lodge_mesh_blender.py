"""Blender5.3: measured-image camera review and provisional reference export."""
import bpy,bmesh,json,math
from collections import Counter
from pathlib import Path
from mathutils import Matrix,Vector
BASE=Path('/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/november-capture-reconstruction-v001')
OUT=BASE/'lodge-reference-review-v002'
OUT.mkdir(exist_ok=False)
(OUT/'execution-storage').mkdir()
assert bpy.app.version[:2]==(5,3),bpy.app.version_string
j=json.loads((BASE/'lodge-reference-review-v001/orientation.json').read_text());
(OUT/'orientation.json').write_text(json.dumps(j,indent=2));T=Matrix(j['native_to_blender'])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.temporary_directory=str(OUT/'execution-storage')
bpy.ops.wm.obj_import(filepath=str(BASE/'openmvs-lodge-v002/textured-v002.obj'),forward_axis='Y',up_axis='Z')
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert meshes
removed=[]
for o in meshes:
 parent=list(range(len(o.data.vertices)))
 def find(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 for e in o.data.edges:
  a,b=map(find,e.vertices)
  if a!=b:parent[b]=a
 counts=Counter(find(p.vertices[0]) for p in o.data.polygons)
 ids=[v.index for v in o.data.vertices if counts[find(v.index)]<1000]
 bm=bmesh.new();bm.from_mesh(o.data);bm.verts.ensure_lookup_table();bmesh.ops.delete(bm,geom=[bm.verts[i] for i in ids],context='VERTS');bm.to_mesh(o.data);bm.free();removed.append({'object':o.name,'removed_vertices':len(ids),'criterion':'Disconnected components fewer than1000faces; originalunfilteredmesh retained'})
 o.matrix_world=T@o.matrix_world;o['source']='Verified2026-11-10 clip035 t140–162s';o['status']='Partial photogrammetric reference; physical scale unverified'
 # Diagnostic unlit captured-color material. No invented lighting or textures.
 for m in o.data.materials:
  if not m or not m.use_nodes:continue
  nodes=m.node_tree.nodes;tex=next((n for n in nodes if n.type=='TEX_IMAGE'),None);output=next((n for n in nodes if n.type=='OUTPUT_MATERIAL'),None)
  if tex and output:
   e=nodes.new('ShaderNodeEmission');m.node_tree.links.new(tex.outputs['Color'],e.inputs['Color']);m.node_tree.links.new(e.outputs[0],output.inputs['Surface'])
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16;scene.render.resolution_x=960;scene.render.resolution_y=960;scene.render.resolution_percentage=100;scene.world=bpy.data.worlds.new('Diagnostic background');scene.world.color=(.025,.025,.025);scene.view_settings.view_transform='Standard'
camdata=bpy.data.cameras.new('Capture-matched review');camera=bpy.data.objects.new('Capture-matched review',camdata);scene.collection.objects.link(camera);scene.camera=camera
R=Matrix(j['camera_native_R']);t=Vector(j['camera_native_t']);pose=R.transposed().to_4x4();pose.translation=-(R.transposed()@t);camera.matrix_world=T@pose@Matrix.Diagonal((1,-1,-1,1));camdata.type='PERSP';camdata.angle=math.radians(80);camdata.clip_end=10000
scene.render.filepath=str(OUT/'capture-matched.png');bpy.ops.render.render(write_still=True)
# A second camera keeps the same origin/viewdirection with an upright roll.
look=camera.matrix_world.to_3x3()@Vector((0,0,-1));camera.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(OUT/'upright-capture-view.png');bpy.ops.render.render(write_still=True)
coords=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box];lo=Vector([min(v[i] for v in coords) for i in range(3)]);hi=Vector([max(v[i] for v in coords) for i in range(3)]);center=(lo+hi)/2;extent=(hi-lo).length
camera.location=center+Vector((.8,-1,.7))*extent;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();camdata.type='ORTHO';camdata.ortho_scale=max(hi-lo)*1.35
scene.render.filepath=str(OUT/'overview.png');bpy.ops.render.render(write_still=True)
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'Cliff-House-Nov10-partial-reference.glb'),export_format='GLB',use_selection=True,export_yup=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Cliff-House-Nov10-partial-reference.blend'))
report={'blender':bpy.app.version_string,'filtered_components':removed,'mesh_objects':len(meshes),'vertices':sum(len(o.data.vertices) for o in meshes),'polygons':sum(len(o.data.polygons) for o in meshes),'bounds_blender':[list(lo),list(hi)],'scale':'unverified arbitrary SfM units','coverage':'clip035 t140–162; not complete building','material':'unlit captured photographic texture for diagnostic reference','export':str(OUT/'Cliff-House-Nov10-partial-reference.glb')}
(OUT/'mesh-review.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
