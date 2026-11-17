"""Blender (arka plan) ile bir model dosyasını inceler: nesneler, üçgen sayısı, boyut, malzeme renkleri.
Kullanım: blender -b --python tools/blender_inspect.py -- <dosya.blend|.fbx|.obj>
"""
import sys

import bpy

path = sys.argv[sys.argv.index("--") + 1]
low = path.lower()
if low.endswith(".blend"):
    bpy.ops.wm.open_mainfile(filepath=path)
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if low.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    elif low.endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=path)
print("=== INSPECT", path)
dg = bpy.context.evaluated_depsgraph_get()
for o in bpy.data.objects:
    info = [o.name, o.type]
    if o.type == "MESH":
        me = o.data
        me.calc_loop_triangles()
        ev = o.evaluated_get(dg)
        wv = [ev.matrix_world @ v.co for v in ev.to_mesh().vertices]
        lo = [min(p[i] for p in wv) for i in range(3)]
        hi = [max(p[i] for p in wv) for i in range(3)]
        info += ["tris=%d" % len(me.loop_triangles), "mats=%s" % [m.name if m else None for m in me.materials],
                 "mods=%s" % [m.type for m in o.modifiers], "bbox_min=(%.2f,%.2f,%.2f)" % tuple(lo),
                 "bbox_max=(%.2f,%.2f,%.2f)" % tuple(hi), "hide=%s/%s" % (o.hide_viewport, o.hide_render)]
    print(" ", *info)
for m in bpy.data.materials:
    c = tuple(round(x, 2) for x in m.diffuse_color)
    print("  MAT", m.name, c)
