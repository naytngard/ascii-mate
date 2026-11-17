"""Blender (arka plan) ile model hazırlar: seçili nesneleri birleştirir, Decimate ile üçgen sayısını düşürür,
malzeme rengini köşe rengine yazar ve Y-yukarı, merkezlenmiş, köşe renkli bir OBJ üretir (tools/hd_convert.parse_obj okur).
Kullanım:
  blender -b --python tools/blender_prep.py -- <girdi> <cikti.obj> [--drop a,b] [--keep a,b] [--tris 12000]
      [--color "#rrggbb"] [--mat Ad=#rrggbb,...] [--rot-z 0]
girdi: .blend / .fbx / .obj.   --color: tüm malzemeleri bu renge çevirir.   --mat: malzeme adına göre renk.
"""
import sys

import bmesh
import bpy
from mathutils import Matrix


def arg(name, default=None):
    a = sys.argv[sys.argv.index("--") + 1:]
    return a[a.index(name) + 1] if name in a else default


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


inp, out = sys.argv[sys.argv.index("--") + 1], sys.argv[sys.argv.index("--") + 2]
drop = set(filter(None, (arg("--drop", "") or "").split(",")))
keep = set(filter(None, (arg("--keep", "") or "").split(",")))
tris_target = int(arg("--tris", "12000"))
color_all = hex_rgb(arg("--color")) if arg("--color") else None
mat_over = {}
for kv in filter(None, (arg("--mat", "") or "").split(",")):
    k, v = kv.split("=")
    mat_over[k] = hex_rgb(v)
rot_z = float(arg("--rot-z", "0"))

low = inp.lower()
if low.endswith(".blend"):
    bpy.ops.wm.open_mainfile(filepath=inp)
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if low.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=inp)
    else:
        bpy.ops.wm.obj_import(filepath=inp)

dg = bpy.context.evaluated_depsgraph_get()
bm = bmesh.new()
mat_colors = {}  # birleşik malzeme dizisi
mats = []
for o in list(bpy.data.objects):
    if o.type != "MESH" or o.name in drop or (keep and o.name not in keep):
        continue
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    me.transform(ev.matrix_world)
    base = len(mats)
    for s in me.materials:
        nm = s.name if s else "none"
        c = tuple(s.diffuse_color[:3]) if s else (0.7, 0.7, 0.7)
        mats.append((nm, c))
    if not me.materials:
        mats.append(("none", (0.7, 0.7, 0.7)))
    bm_o = bmesh.new()
    bm_o.from_mesh(me)
    for f in bm_o.faces:
        f.material_index += base
    tmp = bpy.data.meshes.new("tmp")
    bm_o.to_mesh(tmp)
    bm_o.free()
    bm.from_mesh(tmp)
    ev.to_mesh_clear()

bmesh.ops.triangulate(bm, faces=bm.faces)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
mesh = bpy.data.meshes.new("joined")
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("joined", mesh)
bpy.context.scene.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
n0 = len(mesh.polygons)
if n0 > tris_target:
    md = obj.modifiers.new("dec", "DECIMATE")
    md.ratio = tris_target / n0
    md.use_collapse_triangulate = True
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = bpy.data.meshes.new_from_object(ev)
print("TRIS", n0, "->", len(mesh.polygons))

# köşe renkleri: köşeyi kullanan ilk yüzün malzemesi
vcol = {}
for p in mesh.polygons:
    nm, c = mats[p.material_index] if p.material_index < len(mats) else ("none", (0.7, 0.7, 0.7))
    c = color_all or mat_over.get(nm) or c
    for vi in p.vertices:
        vcol.setdefault(vi, c)

# Blender Z-yukarı (ön = -Y) → Y-yukarı (ön = +Z); sonra bbox merkezle
R = Matrix.Rotation(rot_z * 3.14159265 / 180.0, 3, "Z")
pts = []
for v in mesh.vertices:
    x, y, z = R @ v.co
    pts.append((x, z, -y))
lo = [min(p[i] for p in pts) for i in range(3)]
hi = [max(p[i] for p in pts) for i in range(3)]
ctr = [(lo[i] + hi[i]) / 2 for i in range(3)]
with open(out, "w") as fh:
    for i, p in enumerate(pts):
        c = vcol.get(i, (0.7, 0.7, 0.7))
        fh.write("v %.5f %.5f %.5f %.4f %.4f %.4f\n" % (p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2], c[0], c[1], c[2]))
    for p in mesh.polygons:
        a, b, c = p.vertices
        # Y-yukarı dönüşümü (x,z,-y) el yönünü korur (determinant +1)
        fh.write("f %d %d %d\n" % (a + 1, b + 1, c + 1))
print("OBJ", out, "verts", len(pts), "size", [round(hi[i] - lo[i], 3) for i in range(3)])
