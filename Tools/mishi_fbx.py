"""What a binary FBX says about its meshes' UV scale - pure Python (struct + zlib): the system's and Unreal's alike.

    python Tools/mishi_fbx.py Import/eros15_07/female.fbx [...]

uv_scale(path) -> {material name: centimetres of surface one unit of UV covers}: for each triangle the square root of
(its area on the body / its area in UV space), the median over a material's triangles weighted by area.  A tiled detail map
(the skin's pores) gets its tiling from it, so that a pore is as large on a face - a quarter of a metre spread over the UV
square - as on a body.
"""
import json
import math
import struct
import sys
import zlib


class Node:
    __slots__ = ("name", "props", "children")

    def __init__(self, name, props, children):
        self.name, self.props, self.children = name, props, children

    def find(self, name):
        return next((c for c in self.children if c.name == name), None)

    def all(self, name):
        return [c for c in self.children if c.name == name]


ARRAYS = {b"f": "f", b"d": "d", b"l": "q", b"i": "i", b"b": "b", b"c": "b"}
SCALARS = {b"Y": "<h", b"C": "<b", b"I": "<i", b"F": "<f", b"D": "<d", b"L": "<q"}


def _props(data, pos, count):
    out = []
    for _ in range(count):
        t = data[pos:pos + 1]
        pos += 1
        if t in SCALARS:
            fmt = SCALARS[t]
            out.append(struct.unpack_from(fmt, data, pos)[0])
            pos += struct.calcsize(fmt)
        elif t in ARRAYS:
            n, enc, size = struct.unpack_from("<III", data, pos)
            pos += 12
            raw = data[pos:pos + size]
            pos += size
            if enc == 1:
                raw = zlib.decompress(raw)
            out.append(struct.unpack("<%d%s" % (n, ARRAYS[t]), raw[:n * struct.calcsize(ARRAYS[t])]))
        elif t in (b"S", b"R"):
            n = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            out.append(data[pos:pos + n].decode("utf-8", "replace") if t == b"S" else data[pos:pos + n])
            pos += n
        else:
            raise ValueError("FBX property type %r at %d" % (t, pos - 1))
    return out, pos


def _node(data, pos, wide):
    if wide:
        end, count, _size = struct.unpack_from("<QQQ", data, pos)
        pos += 24
    else:
        end, count, _size = struct.unpack_from("<III", data, pos)
        pos += 12
    n = data[pos]
    pos += 1
    if end == 0:
        return None, pos + n
    name = data[pos:pos + n].decode("ascii", "replace")
    pos += n
    props, pos = _props(data, pos, count)
    children = []
    while pos < end:
        child, pos = _node(data, pos, wide)
        if child is None:
            break
        children.append(child)
    return Node(name, props, children), end


def read(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:20] != b"Kaydara FBX Binary  ":
        raise ValueError("%s is not a binary FBX" % path)
    version = struct.unpack_from("<I", data, 23)[0]
    pos, top = 27, []
    while pos < len(data) - 32:
        node, pos = _node(data, pos, version >= 7500)
        if node is None:
            break
        top.append(node)
    return Node("", [], top)


def _name(prop):
    # "body\x00\x01Geometry" -> "body"
    return prop.split("\x00")[0] if isinstance(prop, str) else str(prop)


def uv_scale(path):
    root = read(path)
    objects, links = root.find("Objects"), root.find("Connections")
    if objects is None or links is None:
        return {}
    scale = 1.0                                      # the file's unit in centimetres
    settings = root.find("GlobalSettings")
    if settings is not None and settings.find("Properties70") is not None:
        for p in settings.find("Properties70").all("P"):
            if p.props and p.props[0] == "UnitScaleFactor":
                scale = float(p.props[-1])
    geometry = {g.props[0]: g for g in objects.all("Geometry")}
    materials = {m.props[0]: _name(m.props[1]) for m in objects.all("Material")}
    models = {m.props[0]: m for m in objects.all("Model")}
    of_model, mats_of = {}, {}
    for c in links.all("C"):
        if c.props[0] != "OO":
            continue
        child, parent = c.props[1], c.props[2]
        if child in geometry and parent in models:
            of_model[child] = parent
        elif child in materials and parent in models:
            mats_of.setdefault(parent, []).append(materials[child])
    spans = {}                                        # material -> [(cm per UV unit, area)]
    for gid, g in geometry.items():
        v, pvi = g.find("Vertices"), g.find("PolygonVertexIndex")
        layer = g.find("LayerElementUV")
        if v is None or pvi is None or layer is None or layer.find("UV") is None:
            continue
        v, pvi, uv = v.props[0], pvi.props[0], layer.find("UV").props[0]
        uvi = layer.find("UVIndex").props[0] if layer.find("UVIndex") is not None else None
        by_vertex = (layer.find("MappingInformationType").props[0] == "ByVertice") if layer.find("MappingInformationType") is not None else False
        names = mats_of.get(of_model.get(gid), [])
        ml = g.find("LayerElementMaterial")
        per_polygon = None
        if ml is not None and ml.find("Materials") is not None and ml.find("MappingInformationType").props[0] == "ByPolygon":
            per_polygon = ml.find("Materials").props[0]
        poly, corner, polygon = [], 0, 0
        for index in pvi:
            last = index < 0
            vertex = -index - 1 if last else index
            k = vertex if by_vertex else corner
            k = uvi[k] if uvi is not None else k
            poly.append((vertex, k))
            corner += 1
            if not last:
                continue
            m = per_polygon[polygon] if per_polygon is not None and polygon < len(per_polygon) else 0
            name = names[m] if m < len(names) else (names[0] if names else "?")
            polygon += 1
            for t in range(1, len(poly) - 1):
                (a, ua), (b, ub), (c, uc) = poly[0], poly[t], poly[t + 1]
                ax, ay, az = v[a * 3], v[a * 3 + 1], v[a * 3 + 2]
                e1 = (v[b * 3] - ax, v[b * 3 + 1] - ay, v[b * 3 + 2] - az)
                e2 = (v[c * 3] - ax, v[c * 3 + 1] - ay, v[c * 3 + 2] - az)
                cx, cy, cz = e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]
                area = 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz) * scale * scale
                u1, v1 = uv[ub * 2] - uv[ua * 2], uv[ub * 2 + 1] - uv[ua * 2 + 1]
                u2, v2 = uv[uc * 2] - uv[ua * 2], uv[uc * 2 + 1] - uv[ua * 2 + 1]
                flat = 0.5 * abs(u1 * v2 - u2 * v1)
                if area > 1e-9 and flat > 1e-12:
                    spans.setdefault(name, []).append((math.sqrt(area / flat), area))
            poly = []
    out = {}
    for name, items in spans.items():
        items.sort()
        half, run = sum(a for _, a in items) * 0.5, 0.0
        for span, area in items:
            run += area
            if run >= half:
                out[name] = round(span, 2)
                break
    return out


def _through(m, x, y, z):
    """A point through an FBX matrix: 16 numbers, row after row, the translation in the last row."""
    return (x * m[0] + y * m[4] + z * m[8] + m[12], x * m[1] + y * m[5] + z * m[9] + m[13], x * m[2] + y * m[6] + z * m[10] + m[14])


def meshes(path):
    """The skinned meshes of a file as they stand in their bind pose, in centimetres, and where the bones stood then:

        {"meshes": [{"name": the mesh node's name,
                     "vertices": [(x, y, z)], "polygons": [[vertex index]], "uvs": [[(u, v)] for each polygon's corners],
                     "materials": [material name for each polygon], "weights": {bone name: ([vertex index], [weight])}}],
         "bones": {bone name: (x, y, z)},
         "bone_matrices": {bone name: the bone's bind matrix, 16 numbers row by row, its axes in rows 0-2 and its place in row 3
                           (centimetres; a point of the bone's own space times it = the point in the file's space)}}

    (Blender 3.6's importer gives up on what Unity's exporter writes - a root that is skinned to and parents the meshes -
    with a KeyError in link_hierarchy; this reads what a body-to-body fit needs and nothing else.)"""
    root = read(path)
    objects, links = root.find("Objects"), root.find("Connections")
    scale = 1.0
    settings = root.find("GlobalSettings")
    if settings is not None and settings.find("Properties70") is not None:
        for p in settings.find("Properties70").all("P"):
            if p.props and p.props[0] == "UnitScaleFactor":
                scale = float(p.props[-1])
    geometry = {g.props[0]: g for g in objects.all("Geometry")}
    materials = {m.props[0]: _name(m.props[1]) for m in objects.all("Material")}
    models = {m.props[0]: m for m in objects.all("Model")}
    deformers = {d.props[0]: d for d in objects.all("Deformer")}
    of_model, mats_of, skin_of, clusters_of, bone_of = {}, {}, {}, {}, {}
    for c in links.all("C"):
        if c.props[0] != "OO":
            continue
        child, parent = c.props[1], c.props[2]
        if child in geometry and parent in models:
            of_model[child] = parent
        elif child in materials and parent in models:
            mats_of.setdefault(parent, []).append(materials[child])
        elif child in deformers and parent in geometry:
            skin_of[parent] = child
        elif child in deformers and parent in deformers:
            clusters_of.setdefault(parent, []).append(child)
        elif child in models and parent in deformers:
            bone_of[parent] = child
    out = {"meshes": [], "bones": {}, "bone_matrices": {}}
    for gid, g in geometry.items():
        v, pvi = g.find("Vertices"), g.find("PolygonVertexIndex")
        if v is None or pvi is None:
            continue
        v, pvi = v.props[0], pvi.props[0]
        layer = g.find("LayerElementUV")
        uv = layer.find("UV").props[0] if layer is not None and layer.find("UV") is not None else None
        uvi = layer.find("UVIndex").props[0] if uv is not None and layer.find("UVIndex") is not None else None
        by_vertex = uv is not None and layer.find("MappingInformationType") is not None and layer.find("MappingInformationType").props[0] == "ByVertice"
        names = mats_of.get(of_model.get(gid), [])
        ml = g.find("LayerElementMaterial")
        per_polygon = None
        if ml is not None and ml.find("Materials") is not None and ml.find("MappingInformationType").props[0] == "ByPolygon":
            per_polygon = ml.find("Materials").props[0]
        weights, bind = {}, None
        for cid in clusters_of.get(skin_of.get(gid), []):
            cl = deformers[cid]
            bone = _name(models[bone_of[cid]].props[1]) if cid in bone_of else _name(cl.props[1])
            link, tr = cl.find("TransformLink"), cl.find("Transform")
            if link is not None:
                out["bones"].setdefault(bone, tuple(x * scale for x in link.props[0][12:15]))
                out["bone_matrices"].setdefault(bone, tuple(link.props[0][:12]) + tuple(x * scale for x in link.props[0][12:15]) + (1.0,))
            if tr is not None and link is not None and bind is None:
                # Transform takes the mesh's own space into the bone's (Unity's bind pose), TransformLink the bone's into the
                # world: one after the other is where the mesh stood when it was bound - the same for every bone of it
                a, b = tr.props[0], link.props[0]
                bind = [sum(a[i * 4 + k] * b[k * 4 + j] for k in range(4)) for i in range(4) for j in range(4)]
            idx, w = cl.find("Indexes"), cl.find("Weights")
            if idx is not None and w is not None:
                weights[bone] = (list(idx.props[0]), list(w.props[0]))
        vertices = []
        for i in range(0, len(v), 3):
            p = (v[i], v[i + 1], v[i + 2])
            if bind is not None:
                p = _through(bind, *p)
            vertices.append((p[0] * scale, p[1] * scale, p[2] * scale))
        polygons, uvs, mats = [], [], []
        poly, corners, corner = [], [], 0
        for index in pvi:
            last = index < 0
            vertex = -index - 1 if last else index
            poly.append(vertex)
            if uv is not None:
                k = vertex if by_vertex else corner
                k = uvi[k] if uvi is not None else k
                corners.append((uv[k * 2], uv[k * 2 + 1]))
            corner += 1
            if last:
                m = per_polygon[len(polygons)] if per_polygon is not None and len(polygons) < len(per_polygon) else 0
                mats.append(names[m] if m < len(names) else (names[0] if names else "?"))
                polygons.append(poly)
                uvs.append(corners)
                poly, corners = [], []
        model = models.get(of_model.get(gid))
        out["meshes"].append({"name": _name(model.props[1]) if model is not None else _name(g.props[1]), "vertices": vertices,
                              "polygons": polygons, "uvs": uvs, "materials": mats, "weights": weights})
    # the bones no vertex hangs on (finger tips, the root): from the bind poses the file keeps
    for pose in objects.all("Pose"):
        for node in pose.all("PoseNode"):
            n, m = node.find("Node"), node.find("Matrix")
            if n is None or m is None or n.props[0] not in models:
                continue
            name = _name(models[n.props[0]].props[1])
            out["bones"].setdefault(name, tuple(x * scale for x in m.props[0][12:15]))
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p)
        print(json.dumps(uv_scale(p), indent=1, ensure_ascii=False))
