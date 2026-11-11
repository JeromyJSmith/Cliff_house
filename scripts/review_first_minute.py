import bpy
from pathlib import Path
from mathutils import Vector
p=Path('/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/november-capture-reconstruction-v001/first-minute-surface-v001')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=str(p/'textured.obj'),forward_axis='Y',up_axis='Z')
objs=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert objs
for o in objs:
 for m in o.data.materials:
  if m and m.use_nodes:
   n=m.node_tree.nodes;tex=next((x for x in n if x.type=='TEX_IMAGE'),None);out=next((x for x in n if x.type=='OUTPUT_MATERIAL'),None)
   if tex and out:
    e=n.new('ShaderNodeEmission');m.node_tree.links.new(tex.outputs['Color'],e.inputs['Color']);m.node_tree.links.new(e.outputs[0],out.inputs['Surface'])
coords=[o.matrix_world@Vector(c) for o in objs for c in o.bound_box];lo=Vector([min(v[i] for v in coords) for i in range(3)]);hi=Vector([max(v[i] for v in coords) for i in range(3)]);center=(lo+hi)/2;extent=(hi-lo).length
c=bpy.data.cameras.new('Review');o=bpy.data.objects.new('Review',c);bpy.context.scene.collection.objects.link(o);o.location=center+Vector((1,-1,1))*extent;o.rotation_euler=(center-o.location).to_track_quat('-Z','Y').to_euler();c.type='ORTHO';c.ortho_scale=max(hi-lo)*1.5
s=bpy.context.scene;s.camera=o;s.render.engine='CYCLES';s.cycles.samples=8;s.render.resolution_x=800;s.render.resolution_y=800;s.render.resolution_percentage=100;s.render.filepath=str(p/'review.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(p/'first-minute.blend'))
