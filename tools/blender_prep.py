"""Blender (arka plan) ile model hazırlar: seçili nesneleri birleştirir, Decimate ile üçgen sayısını düşürür,
malzeme rengini köşe rengine yazar ve Y-yukarı, merkezlenmiş, köşe renkli bir OBJ üretir (tools/hd_convert.parse_obj okur).
Kullanım:
  blender -b --python tools/blender_prep.py -- <girdi> <cikti.obj> [--drop a,b] [--keep a,b] [--tris 12000]
      [--color "#rrggbb"] [--mat Ad=#rrggbb,...] [--rot-z 0] [--texture [N]] [--srgb]
--texture: dokulu malzemelerde UV'den doku örnekler (köşe rengine yazar); N = önce kenar bölme sayısı (varsayılan 1, düşük poli modelde
  daha çok köşe → daha çok renk ayrıntısı). --srgb: örneklenen renkleri doğrusaldan sRGB'ye çevirir.
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
tex_cuts = 0
if "--texture" in sys.argv:
    nxt = sys.argv[sys.argv.index("--texture") + 1] if sys.argv.index("--texture") + 1 < len(sys.argv) else ""
    tex_cuts = int(nxt) if nxt.isdigit() else 1
to_srgb = "--srgb" in sys.argv

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
    if tex_cuts and bm_o.loops.layers.uv.active is not None:
        import numpy as np

        bmesh.ops.subdivide_edges(bm_o, edges=bm_o.edges[:], cuts=tex_cuts, use_grid_fill=True)
        uvl = bm_o.loops.layers.uv.active
        coll = bm_o.loops.layers.float_color.get("Col") or bm_o.loops.layers.float_color.new("Col")
        imgs = {}
        for mt in me.materials:
            node = next((n for n in mt.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None) if mt and mt.use_nodes else None
            if node is not None and node.image.name not in imgs:
                im = node.image
                px = np.empty(im.size[0] * im.size[1] * 4, np.float32)
                im.pixels.foreach_get(px)
                imgs[im.name] = (px.reshape(im.size[1], im.size[0], 4), im.size[0], im.size[1])
        for fc in bm_o.faces:
            mt = me.materials[fc.material_index] if me.materials else None
            node = next((n for n in mt.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None) if mt and mt.use_nodes else None
            for lp in fc.loops:
                if node is None:
                    lp[coll] = (*(mt.diffuse_color[:3] if mt else (0.7, 0.7, 0.7)), 1.0)
                    continue
                arr, w_, h_ = imgs[node.image.name]
                u, v = lp[uvl].uv
                c = arr[min(h_ - 1, max(0, int(v % 1.0 * h_))), min(w_ - 1, max(0, int(u % 1.0 * w_)))]
                rgb = np.clip(c[:3], 0, 1)
                if to_srgb:
                    rgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
                lp[coll] = (float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
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

# köşe renkleri: köşeyi kullanan ilk yüzün malzemesi (doku örneklendiyse köşe başına ortalama)
vcol = {}
for p in mesh.polygons:
    nm, c = mats[p.material_index] if p.material_index < len(mats) else ("none", (0.7, 0.7, 0.7))
    c = color_all or mat_over.get(nm) or c
    for vi in p.vertices:
        vcol.setdefault(vi, c)
ca = mesh.color_attributes.get("Col") if tex_cuts else None
if ca is not None and not color_all:
    acc, cnt = {}, {}
    for li, lp in enumerate(mesh.loops):
        col_ = ca.data[li].color
        a_ = acc.setdefault(lp.vertex_index, [0.0, 0.0, 0.0])
        for k in range(3):
            a_[k] += col_[k]
        cnt[lp.vertex_index] = cnt.get(lp.vertex_index, 0) + 1
    for vi, a_ in acc.items():
        vcol[vi] = tuple(x / cnt[vi] for x in a_)

# Blender Z-yukarı (ön = -Y) → Y-yukarı (ön = +Z); sonra bbox merkezle
R = Matrix.Rotation(rot_z * 3.14159265 / 180.0, 3, "Z")
pts = []
for v in mesh.vertices:
    x, y, z = R @ v.co
    pts.append((x, z, -y))
lo = [min(p[i] for p in pts) for i in range(3)]
hi = [max(p[i] for p in pts) for i in range(3)]
ctr = [(lo[i] + hi[i]) / 2 for i in range(3)]
arms = arg("--arms")  # "pivot_x,pivot_z,aci_derece,esik0,esik1": T-pozu kollarını omuz noktasında aşağı (+z) döndür
if arms:
    import math

    px, pz, ang, e0, e1 = (float(t) for t in arms.split(","))
    th = math.radians(ang)
    moved = []
    for p in pts:
        x, y, z = p[0] - ctr[0], p[1] - ctr[1], p[2] - ctr[2]
        s = 1.0 if x >= 0 else -1.0
        t = min(1.0, max(0.0, (abs(x) - e0) / max(e1 - e0, 1e-6)))
        w = t * t * (3 - 2 * t)  # yumuşak geçiş: gövde-omuz kopmasın
        a = th * w
        dx, dz = x - s * px, z - pz
        ca, sa = math.cos(a), math.sin(a)
        if s > 0:
            ndx, ndz = dx * ca - dz * sa, dx * sa + dz * ca
        else:
            ndx, ndz = dx * ca + dz * sa, -dx * sa + dz * ca
        moved.append((ndx + s * px + ctr[0], y + ctr[1], ndz + pz + ctr[2]))
    pts = moved
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
