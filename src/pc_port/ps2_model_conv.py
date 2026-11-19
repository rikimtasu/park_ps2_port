"""
Convert Ruah's official PS2 3D battle model from PA_BTL.DAT[67] (00_LUAH_ph2chr09.def FLK)
and her 611-entry PS2 motion bank PA_BTL.DAT[108..719] into PC Prism Ark formats:
  - data/char/character/ruah/ph2chr09.dmo       (DirectX .X skinned mesh + 49 bones + 59 animations)
  - data/char/character/ruah/ph2chr09.def       (parts table + all battle/damage/skill motion scripts)
  - data/char/character/ruah/ph2chr09.cmn       (common effect material definitions)
  - data/char/character/ruah/ph2chr09_face.tga  (PA_BTL[67] sub[1] 128x128 32-bit TGA)
  - data/char/character/ruah/ph2chr09.tga       (PA_BTL[67] sub[2] 256x256 32-bit TGA)
  - data/char/character/ruah/ph2chr09_hair.tga  (PA_BTL[67] sub[3] 128x128 32-bit TGA)
"""
import math
import os
import re
import struct
import numpy as np
from PIL import Image

import common

RUAH_BTL_FLK_IDX = 67
RUAH_MOT_BANK_START = 108
RUAH_MOT_BANK_LIST = 719
RUAH_SE_BASE = 2100


def unpack_inner_flk(data: bytes) -> list[bytes]:
    assert data[:4] == b"FLK\x00", f"Expected inner FLK magic, got {data[:4]!r}"
    cnt, = struct.unpack_from("<I", data, 0x18)
    out = []
    for i in range(cnt):
        off, sz = struct.unpack_from("<II", data, 0x20 + i * 8)
        out.append(data[off : off + sz])
    return out


def _quat_slerp(q0: tuple[float, float, float, float], q1: tuple[float, float, float, float], t: float):
    if t <= 0.0:
        return q0
    if t >= 1.0:
        return q1
    x0, y0, z0, w0 = q0
    x1, y1, z1, w1 = q1
    dot = x0 * x1 + y0 * y1 + z0 * z1 + w0 * w1
    if dot < 0.0:
        dot = -dot
        x1, y1, z1, w1 = -x1, -y1, -z1, -w1
    if dot > 0.9995:
        rx = x0 + t * (x1 - x0)
        ry = y0 + t * (y1 - y0)
        rz = z0 + t * (z1 - z0)
        rw = w0 + t * (w1 - w0)
        inv = 1.0 / max(1e-12, math.sqrt(rx * rx + ry * ry + rz * rz + rw * rw))
        return (rx * inv, ry * inv, rz * inv, rw * inv)
    theta_0 = math.acos(min(1.0, max(-1.0, dot)))
    sin_0 = math.sin(theta_0)
    theta = theta_0 * t
    s0 = math.cos(theta) - dot * math.sin(theta) / sin_0
    s1 = math.sin(theta) / sin_0
    return (
        s0 * x0 + s1 * x1,
        s0 * y0 + s1 * y1,
        s0 * z0 + s1 * z1,
        s0 * w0 + s1 * w1,
    )


def _ps2_quat_pos_to_dmo_euler(
    qx: float, qy: float, qz: float, qw: float,
    px: float, py: float, pz: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """
    Convert PS2 column-vector bone local transform M_col = T(px, py, pz) @ R(qx, qy, qz, qw)
    conjugated by Cz = diag(1, 1, -1, 1) and transposed to DirectX row-vector convention
    into P_ARK201.exe's exact Euler angles (rx, ry, rz) for Rz(rz) @ Rx(rx) @ Ry(ry) @ T(tx, ty, tz).
    """
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz

    # R_col = quat_to_mat(qx, qy, qz, qw)
    # R_row = (Cz @ R_col @ Cz).T:
    #   m00 = R_col[0,0],  m01 = R_col[1,0],  m02 = -R_col[2,0]
    #   m10 = R_col[0,1],  m11 = R_col[1,1],  m12 = -R_col[2,1]
    #   m20 = -R_col[0,2], m21 = -R_col[1,2], m22 = R_col[2,2]
    m00 = 1.0 - 2.0 * (yy + zz)
    m01 = 2.0 * (xy + wz)
    m02 = -2.0 * (xz - wy)

    m11 = 1.0 - 2.0 * (xx + zz)

    m20 = -2.0 * (xz + wy)
    m21 = -2.0 * (yz - wx)
    m22 = 1.0 - 2.0 * (xx + yy)

    # In P_ARK201.exe (0x004A1790):
    #   M[2,1] = -sin(rx)
    #   M[0,1] = sin(rz)*cos(rx), M[1,1] = cos(rz)*cos(rx)
    #   M[2,0] = cos(rx)*sin(ry), M[2,2] = cos(rx)*cos(ry)
    s_rx = -max(-1.0, min(1.0, m21))
    rx = math.asin(s_rx)
    cx = math.cos(rx)
    if abs(cx) > 1e-5:
        ry = math.atan2(m20, m22)
        rz = math.atan2(m01, m11)
    else:
        rz = 0.0
        ry = math.atan2(-m02, m00)

    pos = (px / 100.0, py / 100.0, -pz / 100.0)
    rot = (rx, ry, rz)
    return pos, rot


def parse_ps2_mdp(mdp: bytes):
    """Parse PS2 MDP skeletal hierarchy and skinned triangle strips."""
    assert mdp[:4] == b"MDP\x00", f"Bad MDP magic: {mdp[:4]!r}"
    n_nodes, = struct.unpack_from("<I", mdp, 0x04)
    n_bones, = struct.unpack_from("<I", mdp, 0x1C)
    assert n_nodes == n_bones + 1 == 50, f"Unexpected Ruah MDP counts: {n_nodes}, {n_bones}"

    bones = []
    for b in range(n_bones):
        o = 0x40 + b * 0xF0
        raw_name = mdp[o : o + 32].split(b"\x00", 1)[0].decode("ascii", "replace")
        sib, bidx, par, chd = struct.unpack_from("<4i", mdp, o + 0x20)
        bx, by, bz = struct.unpack_from("<3f", mdp, o + 0x40)
        bones.append({
            "idx": b,
            "ps2_name": raw_name,
            "name": f"b{b:02d}",
            "parent": -1 if b == 0 else par,
            "bind": (bx, by, bz),
        })

    o_skin = 0x40 + n_bones * 0xF0
    cmd_o, cmd_sz = struct.unpack_from("<II", mdp, o_skin + 0xA0)
    t2_off, t2_cnt = struct.unpack_from("<II", mdp, o_skin + 0xA8)
    cmds = struct.unpack_from(f"<{cmd_sz // 4}I", mdp, cmd_o)

    tags = [None] * len(cmds)
    pos = 2
    n_groups = cmds[1]
    for _ in range(n_groups):
        tex_id, n_strips = cmds[pos], cmds[pos + 1]
        for s in range(n_strips):
            tags[pos + 2 + s] = (tex_id, cmds[pos + 2 + s])
        pos += 2 + n_strips
    assert pos == len(cmds), f"cmd_all parse mismatch: {pos} != {len(cmds)}"

    strips = []
    for ci in range(t2_cnt):
        vif_o, vif_sz, c_o, c_sz, p1, p2, p3, p4, u8, cnt2, u10, u11 = struct.unpack_from(
            "<12I", mdp, t2_off + ci * 0x30
        )
        c_start = (c_o - cmd_o) // 4
        c_end = c_start + c_sz // 4
        cur = 0x44 if ci == 0 else 0x1C
        first = True
        prev_tex = None
        for k in range(c_start, c_end):
            t = tags[k]
            if t is None:
                continue
            tex_id, slen = t
            if not first:
                cur += 72 if (prev_tex is not None and tex_id != prev_tex) else 24
            first = False
            prev_tex = tex_id
            vs = []
            for vi in range(slen):
                vo = vif_o + cur + vi * 0x40
                vidx, = struct.unpack_from("<I", mdp, vo)
                u, v, _, _ = struct.unpack_from("<4f", mdp, vo + 0x10)
                nx, ny, nz, _ = struct.unpack_from("<4f", mdp, vo + 0x20)
                r, g, b_c, a_c = struct.unpack_from("<4f", mdp, vo + 0x30)
                assert (r, g, b_c, a_c) == (128.0, 128.0, 128.0, 128.0), (
                    f"Unexpected vertex RGBA at chunk {ci} off 0x{vo:x}: {(r, g, b_c, a_c)}"
                )
                if vidx < u8:
                    px, py, pz, _ = struct.unpack_from("<4f", mdp, p1 + vidx * 16)
                    wf, is_b, b0x5, b1x5 = struct.unpack_from("<f3I", mdp, p3 + vidx * 16)
                else:
                    j = vidx - u8
                    px, py, pz, _ = struct.unpack_from("<4f", mdp, p2 + j * 16)
                    wf, is_b, b0x5, b1x5 = struct.unpack_from("<f3I", mdp, p4 + j * 16)
                b0, b1 = b0x5 // 5, b1x5 // 5
                # DirectX LH bind-pose position & outward normal
                v_lh = (-px / 100.0, pz / 100.0, -py / 100.0)
                nl = math.sqrt(nx * nx + ny * ny + nz * nz)
                if nl > 1e-6:
                    n_lh = (nz / nl, nx / nl, -ny / nl)
                else:
                    n_lh = (0.0, 1.0, 0.0)
                if is_b == 0 or abs(1.0 - wf) < 1e-5 or b0 == b1:
                    weights = ((b0, 1.0),)
                else:
                    w0 = round(float(wf), 4)
                    w1 = round(1.0 - w0, 4)
                    weights = ((b0, w0), (b1, w1))
                vs.append((v_lh, n_lh, (u, v), weights))
            strips.append((tex_id, vs))
            cur += slen * 0x40

    return bones, strips


def build_directx_x_file(bones: list[dict], strips: list[tuple[int, list]]) -> bytes:
    """Build standard ASCII DirectX .X skin mesh (xof 0303txt 0032) with double-sided faces."""
    verts = []
    norms = []
    uvs = []
    v_weights = []
    v_map = {}

    faces = []
    face_mats = []

    def get_vid(pos, norm, uv, weights):
        key = (
            round(pos[0], 5), round(pos[1], 5), round(pos[2], 5),
            round(norm[0], 4), round(norm[1], 4), round(norm[2], 4),
            round(uv[0], 5), round(uv[1], 5),
            weights,
        )
        idx = v_map.get(key)
        if idx is None:
            idx = len(verts)
            v_map[key] = idx
            verts.append(pos)
            norms.append(norm)
            uvs.append(uv)
            v_weights.append(weights)
        return idx

    for tex_id, vs in strips:
        for i in range(len(vs) - 2):
            v0, v1, v2 = (vs[i], vs[i + 1], vs[i + 2]) if (i % 2 == 0) else (vs[i], vs[i + 2], vs[i + 1])
            p0, p1, p2 = v0[0], v1[0], v2[0]
            # Skip degenerate triangles
            if (
                (abs(p0[0] - p1[0]) + abs(p0[1] - p1[1]) + abs(p0[2] - p1[2]) < 1e-6)
                or (abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2]) < 1e-6)
                or (abs(p0[0] - p2[0]) + abs(p0[1] - p2[1]) + abs(p0[2] - p2[2]) < 1e-6)
            ):
                continue

            # Front face
            i0 = get_vid(v0[0], v0[1], v0[2], v0[3])
            i1 = get_vid(v1[0], v1[1], v1[2], v1[3])
            i2 = get_vid(v2[0], v2[1], v2[2], v2[3])
            faces.append((i0, i1, i2))
            face_mats.append(tex_id)

            # Back-face twin (with negated normal, matching PC double-sided cloth/hair/ribbon convention)
            n0_b = (-v0[1][0], -v0[1][1], -v0[1][2])
            n1_b = (-v1[1][0], -v1[1][1], -v1[1][2])
            n2_b = (-v2[1][0], -v2[1][1], -v2[1][2])
            bi0 = get_vid(v0[0], n0_b, v0[2], v0[3])
            bi2 = get_vid(v2[0], n2_b, v2[2], v2[3])
            bi1 = get_vid(v1[0], n1_b, v1[2], v1[3])
            faces.append((bi0, bi2, bi1))
            face_mats.append(tex_id)

    n_v = len(verts)
    n_f = len(faces)

    # Group vertex weights per bone
    bone_vidxs = {b["idx"]: [] for b in bones}
    bone_vwts = {b["idx"]: [] for b in bones}
    for vi, wlist in enumerate(v_weights):
        for b_idx, w_val in wlist:
            bone_vidxs[b_idx].append(vi)
            bone_vwts[b_idx].append(w_val)

    lines = [
        "xof 0303txt 0032",
        "",
        "template XSkinMeshHeader {",
        " <3cf169ce-ff7c-44ab-93c0-f78f62d172e2>",
        " WORD nMaxSkinWeightsPerVertex;",
        " WORD nMaxSkinWeightsPerFace;",
        " WORD nBones;",
        "}",
        "",
        "template VertexDuplicationIndices {",
        " <b8d65549-d7c9-4995-89cf-53a9a8b031e3>",
        " DWORD nIndices;",
        " DWORD nOriginalVertices;",
        " array DWORD indices[nIndices];",
        "}",
        "",
        "template SkinWeights {",
        " <6f0d123b-bad2-4167-a0d0-80224f25fabb>",
        " STRING transformNodeName;",
        " DWORD nWeights;",
        " array DWORD vertexIndices[nWeights];",
        " array FLOAT weights[nWeights];",
        " Matrix4x4 matrixOffset;",
        "}",
        "",
        "Mesh ph2chr09_Layer1 {",
        f" {n_v};",
    ]

    for k, (x, y, z) in enumerate(verts):
        sep = ";" if k == n_v - 1 else ","
        lines.append(f" {x:.6f};{y:.6f};{z:.6f};{sep}")

    lines.append(f" {n_f};")
    for k, (i0, i1, i2) in enumerate(faces):
        sep = ";" if k == n_f - 1 else ","
        lines.append(f" 3;{i0},{i1},{i2};{sep}")

    lines.append("")
    lines.append(" MeshMaterialList {")
    lines.append("  3;")
    lines.append(f"  {n_f};")
    for k, m in enumerate(face_mats):
        sep = ";" if k == n_f - 1 else ","
        lines.append(f"  {m}{sep}")

    for tname in ("ph2chr09_face.tga", "ph2chr09.tga", "ph2chr09_hair.tga"):
        lines.extend([
            "  Material {",
            "   1.000000;1.000000;1.000000;1.000000;;",
            "   0.000000;",
            "   0.000000;0.000000;0.000000;;",
            "   0.000000;0.000000;0.000000;;",
            "   TextureFilename {",
            f'    "{tname}";',
            "   }",
            "  }",
        ])
    lines.append(" }")

    lines.append("")
    lines.append(" MeshNormals {")
    lines.append(f"  {n_v};")
    for k, (nx, ny, nz) in enumerate(norms):
        sep = ";" if k == n_v - 1 else ","
        lines.append(f"  {nx:.6f};{ny:.6f};{nz:.6f};{sep}")
    lines.append(f"  {n_f};")
    for k, (i0, i1, i2) in enumerate(faces):
        sep = ";" if k == n_f - 1 else ","
        lines.append(f"  3;{i0},{i1},{i2};{sep}")
    lines.append(" }")

    lines.append("")
    lines.append(" MeshTextureCoords {")
    lines.append(f"  {n_v};")
    for k, (u, v) in enumerate(uvs):
        sep = ";" if k == n_v - 1 else ","
        lines.append(f"  {u:.6f};{v:.6f};{sep}")
    lines.append(" }")

    lines.extend([
        "",
        " XSkinMeshHeader {",
        "  2;",
        f"  {len(bones)};",
        f"  {len(bones)};",
        " }",
    ])

    for b in bones:
        b_idx = b["idx"]
        b_name = b["name"]
        bx, by, bz = b["bind"]
        vidxs = bone_vidxs[b_idx]
        vwts = bone_vwts[b_idx]
        nw = len(vidxs)
        lines.append("")
        lines.append(" SkinWeights {")
        lines.append(f'  "{b_name}";')
        lines.append(f"  {nw};")
        for k, vi in enumerate(vidxs):
            sep = ";" if k == nw - 1 else ","
            lines.append(f"  {vi}{sep}")
        for k, wt in enumerate(vwts):
            sep = ";" if k == nw - 1 else ","
            lines.append(f"  {wt:.6f}{sep}")
        ox, oy, oz = -bx / 100.0, -by / 100.0, bz / 100.0
        lines.append(
            f"  1.000000,0.000000,0.000000,0.000000,"
            f"0.000000,1.000000,0.000000,0.000000,"
            f"0.000000,0.000000,1.000000,0.000000,"
            f"{ox:.6f},{oy:.6f},{oz:.6f},1.000000;;"
        )
        lines.append(" }")

    lines.append("}")
    lines.append("")
    return "\r\n".join(lines).encode("ascii")


def sample_mot_clip(mot: bytes, n_bones: int, min_frames: int = 2) -> tuple[int, list[list[tuple[tuple[float, float, float], tuple[float, float, float]]]]]:
    """
    Sample a PS2 MOT clip into dense 60fps per-bone (pos, rot) frames [b][f].
    """
    assert mot[:4] == b"MOT\x00", f"Bad MOT magic: {mot[:4]!r}"
    _, max_frame, mot_bones, off_data = struct.unpack_from("<4s3I", mot, 0)
    assert mot_bones == n_bones, f"MOT bone count {mot_bones} != {n_bones}"
    n_frames = max(max_frame + 1, min_frames)

    bones_frames = []
    for b in range(n_bones):
        ro, rf, po, pf = struct.unpack_from("<4I", mot, 0x10 + b * 16)
        next_ro = (
            struct.unpack_from("<I", mot, 0x10 + (b + 1) * 16)[0]
            if b + 1 < n_bones
            else (len(mot) - off_data)
        )
        nr = (po - ro) // 20
        np_k = (next_ro - po) // 16
        r_keys = [struct.unpack_from("<I4f", mot, off_data + ro + k * 20) for k in range(nr)]
        p_keys = [struct.unpack_from("<I3f", mot, off_data + po + k * 16) for k in range(np_k)]

        # Precompute unique keyframe answers when nr == 1 and np_k == 1
        if nr == 1 and np_k == 1:
            rk = r_keys[0]
            pk = p_keys[0]
            const_pr = _ps2_quat_pos_to_dmo_euler(rk[1], rk[2], rk[3], rk[4], pk[1], pk[2], pk[3])
            bones_frames.append([const_pr] * n_frames)
            continue

        b_track = []
        ri = 0
        pi = 0
        for f in range(n_frames):
            f_clamped = min(f, max_frame)
            while ri + 1 < nr and r_keys[ri + 1][0] <= f_clamped:
                ri += 1
            if ri + 1 < nr and r_keys[ri][0] < f_clamped < r_keys[ri + 1][0]:
                f0, x0, y0, z0, w0 = r_keys[ri]
                f1, x1, y1, z1, w1 = r_keys[ri + 1]
                t = (f_clamped - f0) / float(f1 - f0)
                qx, qy, qz, qw = _quat_slerp((x0, y0, z0, w0), (x1, y1, z1, w1), t)
            else:
                _, qx, qy, qz, qw = r_keys[ri]

            while pi + 1 < np_k and p_keys[pi + 1][0] <= f_clamped:
                pi += 1
            if pi + 1 < np_k and p_keys[pi][0] < f_clamped < p_keys[pi + 1][0]:
                f0, px0, py0, pz0 = p_keys[pi]
                f1, px1, py1, pz1 = p_keys[pi + 1]
                t = (f_clamped - f0) / float(f1 - f0)
                px = px0 + t * (px1 - px0)
                py = py0 + t * (py1 - py0)
                pz = pz0 + t * (pz1 - pz0)
            else:
                _, px, py, pz = p_keys[pi]

            b_track.append(_ps2_quat_pos_to_dmo_euler(qx, qy, qz, qw, px, py, pz))
        bones_frames.append(b_track)

    return n_frames, bones_frames


def _pack_dmo_node(
    name: str,
    parent: int,
    pos: tuple[float, float, float],
    rot: tuple[float, float, float],
    scl: tuple[float, float, float],
    piv: tuple[float, float, float],
    off2: tuple[float, float, float],
    x_data: bytes,
    ntype: int,
    motions: list[tuple[str, int, int, bytes]],
) -> bytes:
    hdr = bytearray(0x14C)
    nb = name.encode("cp932")[:255]
    hdr[: len(nb)] = nb
    struct.pack_into("<i", hdr, 0x100, parent)
    struct.pack_into("<3f", hdr, 0x104, *pos)
    struct.pack_into("<3f", hdr, 0x110, *rot)
    struct.pack_into("<3f", hdr, 0x11C, *scl)
    struct.pack_into("<3f", hdr, 0x128, *piv)
    struct.pack_into("<3f", hdr, 0x134, *off2)
    struct.pack_into("<iii", hdr, 0x140, len(x_data), len(motions), ntype)

    chunks = [bytes(hdr)]
    if ntype == 0 and len(x_data) > 0:
        chunks.append(x_data)

    for mname, n_frames, flags, fbytes in motions:
        mhdr = bytearray(0x12C)
        mb = mname.encode("cp932")[:255]
        mhdr[: len(mb)] = mb
        struct.pack_into("<iI", mhdr, 0x100, n_frames, flags)
        chunks.append(bytes(mhdr))
        if fbytes:
            chunks.append(fbytes)

    return b"".join(chunks)


def build_ruah_dmo(bones: list[dict], x_bytes: bytes, clips: list[tuple[str, int, list]]) -> bytes:
    """
    Assemble complete PC DMO binary for Ruah (6 mesh/null nodes + 49 bone nodes).
    """
    n_mesh = 6
    n_xfiles = 1
    n_bone = len(bones)
    assert n_bone == 49

    # Base clip is clips[0] ('BASE')
    assert clips[0][0] == "BASE"
    base_tracks = clips[0][2]

    # Mesh node 0 gets n_mot = len(clips) with flags = 0 (0 frame bytes) so node 0 has full motion table
    mesh0_motions = [(cname, nf, 0, b"") for cname, nf, _ in clips]

    node_blobs = []
    # [0] ph2chr09_Layer1 (skinned .X mesh)
    node_blobs.append(
        _pack_dmo_node(
            name="ph2chr09_Layer1",
            parent=-1,
            pos=(0.0, 0.0, 0.0),
            rot=(0.0, 0.0, 0.0),
            scl=(1.0, 1.0, 1.0),
            piv=(0.0, 0.0, 0.0),
            off2=(0.0, 0.0, 0.0),
            x_data=x_bytes,
            ntype=0,
            motions=mesh0_motions,
        )
    )

    # [1..5] Attachment null nodes parented to their exact corresponding bone nodes (6 + bone_idx):
    #   b01 = masternull, b20 = weapon_top, b21 = weapon_end, b12 = itemNull01, b30 = ST_NULL
    null_attachments = [
        ("masternull", 6 + 1),
        ("weapon_top", 6 + 20),
        ("weapon_end", 6 + 21),
        ("itemNull01", 6 + 12),
        ("ST_NULL", 6 + 30),
    ]
    for null_name, par_node_idx in null_attachments:
        node_blobs.append(
            _pack_dmo_node(
                name=null_name,
                parent=par_node_idx,
                pos=(0.0, 0.0, 0.0),
                rot=(0.0, 0.0, 0.0),
                scl=(1.0, 1.0, 1.0),
                piv=(0.0, 0.0, 0.0),
                off2=(0.0, 0.0, 0.0),
                x_data=b"",
                ntype=0,
                motions=[],
            )
        )

    # [6..54] 49 Bone nodes ("b00" .. "b48")
    for b in range(n_bone):
        b_info = bones[b]
        par_node = -1 if b_info["parent"] < 0 else (6 + b_info["parent"])
        rest_p, rest_r = base_tracks[b][0]

        b_motions = []
        for cname, nf, b_tracks in clips:
            track = b_tracks[b]
            pos_changes = any(
                abs(p[0] - rest_p[0]) > 1e-5 or abs(p[1] - rest_p[1]) > 1e-5 or abs(p[2] - rest_p[2]) > 1e-5
                for p, _ in track
            )
            rot_changes = any(
                abs(r[0] - rest_r[0]) > 1e-5 or abs(r[1] - rest_r[1]) > 1e-5 or abs(r[2] - rest_r[2]) > 1e-5
                for _, r in track
            )
            if not pos_changes and not rot_changes:
                b_motions.append((cname, nf, 0, b""))
            elif not pos_changes:
                buf = bytearray(nf * 12)
                for fi, (_, r) in enumerate(track):
                    struct.pack_into("<3f", buf, fi * 12, *r)
                b_motions.append((cname, nf, 2, bytes(buf)))
            else:
                buf = bytearray(nf * 24)
                for fi, (p, r) in enumerate(track):
                    struct.pack_into("<6f", buf, fi * 24, p[0], p[1], p[2], r[0], r[1], r[2])
                b_motions.append((cname, nf, 3, bytes(buf)))

        node_blobs.append(
            _pack_dmo_node(
                name=b_info["name"],
                parent=par_node,
                pos=rest_p,
                rot=rest_r,
                scl=(1.0, 1.0, 1.0),
                piv=(0.0, 0.0, 0.0),
                off2=(0.0, 0.0, 0.0),
                x_data=b"",
                ntype=1,
                motions=b_motions,
            )
        )

    dmo_hdr = struct.pack("<4sfIfIII", b"DMO ", 1.01, 1, 60.0, n_mesh, n_xfiles, n_bone)
    return dmo_hdr + b"".join(node_blobs)


def build_ruah_def(
    bones: list[dict],
    ps2_def_bytes: bytes,
    mot_list_lines: list[str],
    clip_frames_map: dict[str, int],
    fel_def_text: str,
) -> bytes:
    """
    Build data/char/character/ruah/ph2chr09.def with:
      1. Exact `parts` declarations for Ruah's 49 bones + 5 attachment nulls + ph2chr09_Layer1.
      2. Ruah's signature PS2 attack/skill/defense blocks (LUAH_AK_01, LUAH_SP_01, LUAH_SP_02,
         LUAH_TA_01..04, BOUGYO, JOUKYU_BOUGYO, plus FEL_MAGICAL_HAMMER aliased to Ruah's spear attack).
      3. All 243 vanilla PC motion blocks & PS2 Ruah damage blocks mapped to Ruah's 59 real DMO clips
         and Ruah's battle voice IDs (02100..02203, 00090, 00091, 01009).
    """
    assert ps2_def_bytes[:4] == b"DEF\x00"
    _, cnt, off_hdr, _ = struct.unpack_from("<4s3I", ps2_def_bytes, 0)

    ps2_motion_to_clip = {}
    for i in range(cnt):
        o = off_hdr + i * 0x30
        mname = ps2_def_bytes[o : o + 32].split(b"\x00", 1)[0].decode("cp932", "replace")
        _, tot_f = struct.unpack_from("<HH", ps2_def_bytes, o + 0x20)
        _, mtn_idx, _ = struct.unpack_from("<3I", ps2_def_bytes, o + 0x24)
        c_name = mot_list_lines[mtn_idx].strip().replace(".mtn", "").upper()
        if not c_name or c_name.startswith("#"):
            c_name = "BASE"
        ps2_motion_to_clip[mname] = (c_name, tot_f)

    parts_lines = []
    for b in bones:
        parts_lines.append(f"parts {b['name']} 0 off")
    parts_lines.append("parts ph2chr09_Layer1 0 alpha")
    parts_lines.append("parts masternull 0 off")
    parts_lines.append("parts weapon_top 0 off")
    parts_lines.append("parts weapon_end 0 off")
    parts_lines.append("parts itemNull01 0 off")
    parts_lines.append("parts ST_NULL 0 off")

    # Ruah's signature attack, special skill, team attack, and defense blocks from PA_BTL[67] sub[9]
    luah_ak_01_body = """    DMO_motion ATTACK1
    category 1

    // ホワイトアウト
    event VOID 5 5 FILTER2:500:0:0:0:150:0:0:0:150:1
    event VOID 40 40 FILTER2:20:0:0:0:150:0:0:0:0:1

    // キャラの声 (B_RUA_0013.ogg)
    event VOID 1 1 EVENT_SOUND:1:02113:127

    // カメラ
    event VOID 5 5 EVENT_CAMERAWORK_ON:friend_attack_Default_camera
    event VOID 60 60 EVENT_CAMERAWORK_OFF

    // カメラシェイク
    event VOID 33 33 EVENT_CAMERASHAKE:0.01:0.35:0.5:1

    // 槍の軌跡
    event VOID 8 8 EVENT_TRACK_COMMAND:CREATE:SwordTracks_White:weapon_top:weapon_end:40:6:1:8
    event VOID 8 8 EVENT_TRACK_COMMAND:CKEY:0:255:255:255:180
    event VOID 8 8 EVENT_TRACK_COMMAND:END

    // SE
    event VOID 1 1 EVENT_SOUND:17:10016:127
    event VOID 1 1 EVENT_SOUND:22:10000:127
    event VOID 1 1 EVENT_SOUND:22:10000:127

    // ポップアップ
    event VOID 1 1 EVENT_POPUP:33

    event VOID 1 1 EVENT_MOVE_ENEMY
    event VOID 22 22 EVENT_TGTMOTION:10001
    event VOID 100 100 EVENT_MOVE_DEF
    event VOID 120 120 EVENT_END
    jump  VOID 120 0 motion(BASE)"""

    luah_sp_01_body = """    DMO_motion SA_ATTACK
    category 1

    // ホワイトアウト
    event VOID 5 5 FILTER2:500:0:0:0:150:0:0:0:150:1
    event VOID 240 240 FILTER2:20:0:0:0:150:0:0:0:0:1

    // キャラの声 (B_RUA_0014.ogg: リリトー・イフターハ)
    event VOID 1 1 EVENT_SOUND:1:02114:127

    // カメラ
    event VOID 4 4 EVENT_CAMERAWORK_ON:friend_attack_Default_camera
    event VOID 240 240 EVENT_CAMERAWORK_OFF

    // カメラシェイク
    event VOID 160 160 EVENT_CAMERASHAKE:0.02:0.4:0.5:1
    event VOID 200 200 EVENT_CAMERASHAKE:0.03:0.5:0.5:1

    // 槍の軌跡
    event VOID 10 10 EVENT_TRACK_COMMAND:CREATE:SwordTracks_White:weapon_top:weapon_end:220:6:1:8
    event VOID 10 10 EVENT_TRACK_COMMAND:CKEY:0:255:255:255:200
    event VOID 10 10 EVENT_TRACK_COMMAND:END

    // SE
    event VOID 1 1 EVENT_SOUND:17:10016:127
    event VOID 1 1 EVENT_SOUND:22:10000:127
    event VOID 1 1 EVENT_SOUND:160:10025:127
    event VOID 1 1 EVENT_SOUND:200:10000:127

    // パーティクル
    particle VOID 10 220 mahoujin_hatudou01_white_orlaA masternull
    particle VOID 10 220 mahoujin_hatudou01_white_orlaB masternull

    // ポップアップ
    event VOID 1 1 EVENT_POPUP:200

    event VOID 1 1 EVENT_MOVE_ENEMY
    event VOID 160 160 EVENT_TGTMOTION:10035
    event VOID 280 280 EVENT_MOVE_DEF
    event VOID 300 300 EVENT_END
    jump  VOID 300 0 motion(BASE)"""

    luah_sp_02_body = """    DMO_motion SA_ATTACK02
    category 1

    // ホワイトアウト
    event VOID 5 5 FILTER2:500:0:0:0:150:0:0:0:150:1
    event VOID 260 260 FILTER2:20:0:0:0:150:0:0:0:0:1

    // キャラの声 (B_RUA_0015.ogg: ウーリー・ゼカルヤー)
    event VOID 1 1 EVENT_SOUND:1:02115:127

    // カメラ
    event VOID 4 4 EVENT_CAMERAWORK_ON:friend_attack_Default_camera
    event VOID 260 260 EVENT_CAMERAWORK_OFF

    // カメラシェイク
    event VOID 200 200 EVENT_CAMERASHAKE:0.03:0.5:0.5:1
    event VOID 210 210 EVENT_CAMERASHAKE:0.03:0.5:0.5:1

    // 槍の軌跡
    event VOID 10 10 EVENT_TRACK_COMMAND:CREATE:SwordTracks_White:weapon_top:weapon_end:230:6:1:8
    event VOID 10 10 EVENT_TRACK_COMMAND:CKEY:0:255:255:255:220
    event VOID 10 10 EVENT_TRACK_COMMAND:END

    // SE
    event VOID 1 1 EVENT_SOUND:17:10016:127
    event VOID 1 1 EVENT_SOUND:22:10000:127
    event VOID 1 1 EVENT_SOUND:160:10070:127
    event VOID 1 1 EVENT_SOUND:200:10056:127
    event VOID 1 1 EVENT_SOUND:200:10000:127

    // パーティクル
    particle VOID 10 240 mahoujin_hatudou01_white_orlaA masternull
    particle VOID 10 240 mahoujin_hatudou01_white_orlaB masternull
    particle VOID 20 240 mahoujin_hatudou01_white_orlaC masternull

    // ポップアップ
    event VOID 1 1 EVENT_POPUP:200

    event VOID 1 1 EVENT_MOVE_CENTER:0:0
    event VOID 200 200 EVENT_TGTMOTION:10001
    event VOID 280 280 EVENT_MOVE_DEF
    event VOID 300 300 EVENT_END
    jump  VOID 300 0 motion(BASE)"""

    bougyo_body = """    DMO_motion DEFENCE
    category 1

    // ホワイトアウト
    event VOID 1 1 FILTER2:500:0:0:0:150:0:0:0:150:1
    event VOID 40 40 FILTER2:20:0:0:0:150:0:0:0:0:1

    // カメラ
    event VOID 1 1 EVENT_CAMERAWORK_ON:Defence_Default_camera
    event VOID 60 60 EVENT_CAMERAWORK_OFF

    // キャラの声 (B_RUA_0008.ogg)
    event VOID 1 1 EVENT_SOUND:1:02108:127

    // SE
    event VOID 1 1 EVENT_SOUND:10:10007:127

    // ポップアップ
    event VOID 1 1 EVENT_POPUP:10

    // オブジェクトを出現
    material active 10 BOUGYO masternull

    event VOID 60 60 EVENT_END
    jump VOID 60 0 motion(BASE)"""

    joukyu_bougyo_body = bougyo_body.replace("02108", "02109").replace("BOUGYO", "JOUKYU_BOUGYO")

    custom_blocks = {
        "LUAH_AK_01": luah_ak_01_body,
        "FEL_MAGICAL_HAMMER": luah_ak_01_body,
        "LUAH_SP_01": luah_sp_01_body,
        "LUAH_SP_02": luah_sp_02_body,
        "BOUGYO": bougyo_body,
        "FEL_GUARD": bougyo_body,
        "JOUKYU_BOUGYO": joukyu_bougyo_body,
        "FEL_JOUKYU_GUARD": joukyu_bougyo_body,
    }

    # Voice remapper from Fel -> Ruah
    def _remap_voices(text: str) -> str:
        text = re.sub(r"(EVENT_RANDOM_SOUND:\d+:)0*31(:)", r"\g<1>00090\2", text)
        text = re.sub(r"(EVENT_RANDOM_SOUND:\d+:)0*32(:)", r"\g<1>00091\2", text)
        text = re.sub(r"(EVENT_RANDOM_SOUND:\d+:)0*1003(:)", r"\g<1>01009\2", text)

        def _repl_se(m):
            sid = int(m.group(2))
            if 600 <= sid <= 799:
                new_id = RUAH_SE_BASE + (sid % 16)
                return f"{m.group(1)}{new_id:05d}{m.group(3)}"
            return m.group(0)

        return re.sub(r"(EVENT_SOUND:\d+:)(\d+)(:)", _repl_se, text)

    def _resolve_clip(mname: str, fel_clip: str) -> str:
        if mname in ps2_motion_to_clip:
            c = ps2_motion_to_clip[mname][0]
            if c in clip_frames_map:
                return c
        if fel_clip in clip_frames_map:
            return fel_clip
        if fel_clip.startswith("MG_") or fel_clip in ("POKAPOKA", "CYCLONE", "METEOSTRIKE", "OIROKE01"):
            return "HOJYO_USE"
        if fel_clip.startswith("DAMAGE"):
            return "DAMAGE"
        return "BASE"

    emitted_motions = set()
    motion_Texts = []

    for m in re.finditer(r"motion\s+(\S+)\s*\{(.*?)\n\}", fel_def_text, re.S):
        mname = m.group(1)
        body = m.group(2)
        emitted_motions.add(mname)
        if mname in custom_blocks:
            motion_Texts.append(f"motion {mname} {{\r\n{custom_blocks[mname]}\r\n}}")
            continue

        body = _remap_voices(body)
        # Replace DMO_motion <fel_clip> with valid Ruah DMO clip
        def _repl_dmo_mot(mm):
            old_c = mm.group(1)
            new_c = _resolve_clip(mname, old_c)
            return f"DMO_motion {new_c}"

        body = re.sub(r"DMO_motion\s+(\S+)", _repl_dmo_mot, body, count=1)
        motion_Texts.append(f"motion {mname} {{{body}\n}}")

    # Append any custom_blocks or PS2 Ruah motion blocks not present in Fel's .def
    for mname, cbody in custom_blocks.items():
        if mname not in emitted_motions:
            emitted_motions.add(mname)
            motion_Texts.append(f"motion {mname} {{\r\n{cbody}\r\n}}")

    # Template damage block from Fel's DAMAGE_POWER_BLADE or DAMAGE_SWINGING_CROSS or DAMAGE_CRITICAL_BREAK
    dmg_template_m = re.search(r"motion\s+DAMAGE_FALCON_ATTACK1\s*\{(.*?)\n\}", fel_def_text, re.S)
    dmg_template = _remap_voices(dmg_template_m.group(1)) if dmg_template_m else """
    DMO_motion DAMAGE
    category 1
    event VOID 1 1 EVENT_RANDOM_SOUND:1:01009:127
    event VOID 60 60 EVENT_END
    jump VOID 60 0 motion(BASE)"""

    for mname, (c_name, tot_f) in ps2_motion_to_clip.items():
        if mname in emitted_motions:
            continue
        emitted_motions.add(mname)
        use_clip = c_name if c_name in clip_frames_map else "DAMAGE"
        end_f = max(30, min(tot_f, clip_frames_map.get(use_clip, 60)))
        if mname.startswith("LUAH_TA_"):
            body = f"""    DMO_motion {use_clip}
    category 1
    event VOID 1 1 EVENT_RANDOM_SOUND:10:00090:127
    event VOID 60 60 EVENT_END
    jump VOID 60 0 motion(BASE)"""
        elif mname.startswith("UKE_") or mname in ("MENTAL_POTION2", "MG_HEAL", "MG_INJA_SHIYUKUFUKU"):
            body = f"""    DMO_motion {use_clip}
    category 1
    event VOID {end_f} {end_f} EVENT_END
    jump VOID {end_f} 0 motion(BASE)"""
        else:
            body = re.sub(r"DMO_motion\s+\S+", f"DMO_motion {use_clip}", dmg_template, count=1)
        motion_Texts.append(f"motion {mname} {{\r\n{body.strip()}\r\n}}")

    full_def = "\r\n".join(parts_lines) + "\r\n\r\n" + "\r\n\r\n".join(motion_Texts) + "\r\n"
    return full_def.encode("cp932", "replace")


def convert_ps2_ruah_to_pc(
    iso: common.IsoReader,
    read_pc_b,
    encode_tga_fn,
    preview_dir: str | None = None,
) -> list[tuple[str, bytes]]:
    """
    Convert Ruah's official PS2 3D model, textures, animations, and .def from PA_BTL.DAT
    into PC battle1.dat assets.
    """
    subs = unpack_inner_flk(iso.read_flk_entry("PA_BTL.DAT", RUAH_BTL_FLK_IDX))
    mdp_bytes = subs[0]
    tim2_face = subs[1]
    tim2_body = subs[2]
    tim2_hair = subs[3]
    ps2_def_bytes = subs[9]

    # 1. Decode Ruah's 3 real official PS2 TIM2 textures
    im_face = common.decode_tim2_rgba(tim2_face)
    if isinstance(im_face, tuple):
        im_face = im_face[0]
    im_body = common.decode_tim2_rgba(tim2_body)
    if isinstance(im_body, tuple):
        im_body = im_body[0]
    im_hair = common.decode_tim2_rgba(tim2_hair)
    if isinstance(im_hair, tuple):
        im_hair = im_hair[0]

    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        im_face.save(os.path.join(preview_dir, "ph2chr09_face.png"))
        im_body.save(os.path.join(preview_dir, "ph2chr09.png"))
        im_hair.save(os.path.join(preview_dir, "ph2chr09_hair.png"))

    tga_face = encode_tga_fn(im_face, bpp=32, top_down=False)
    tga_body = encode_tga_fn(im_body, bpp=32, top_down=False)
    tga_hair = encode_tga_fn(im_hair, bpp=32, top_down=False)

    # 2. Parse PS2 MDP mesh & bones and build DirectX .X skin mesh
    bones, strips = parse_ps2_mdp(mdp_bytes)
    x_bytes = build_directx_x_file(bones, strips)

    # 3. Extract all 59 unique .mtn clips from Ruah's PS2 motion bank PA_BTL.DAT[108..719]
    mot_list_lines = iso.read_flk_entry("PA_BTL.DAT", RUAH_MOT_BANK_LIST).decode("cp932", "replace").splitlines()
    seen_clips = {}
    ordered_clip_names = []
    for idx, line in enumerate(mot_list_lines):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        cname = s.replace(".mtn", "").upper()
        if cname not in seen_clips:
            mot_blob = iso.read_flk_entry("PA_BTL.DAT", RUAH_MOT_BANK_START + idx)
            seen_clips[cname] = mot_blob
            ordered_clip_names.append(cname)

    assert "BASE" in seen_clips and ordered_clip_names[0] == "BASE"
    clips = []
    clip_frames_map = {}
    for cname in ordered_clip_names:
        min_f = 41 if cname in ("BASE", "PINCH") else (31 if cname == "RETIRE" else 2)
        nf, b_tracks = sample_mot_clip(seen_clips[cname], len(bones), min_frames=min_f)
        clips.append((cname, nf, b_tracks))
        clip_frames_map[cname] = nf

    # 4. Build PC ph2chr09.dmo
    ruah_dmo = build_ruah_dmo(bones, x_bytes, clips)

    # 5. Build PC ph2chr09.def & ph2chr09.cmn
    fel_cmn = read_pc_b("data/char/character/fel/ph2chr03.cmn")
    fel_def_text = read_pc_b("data/char/character/fel/ph2chr03.def").decode("cp932", "replace")
    ruah_def = build_ruah_def(bones, ps2_def_bytes, mot_list_lines, clip_frames_map, fel_def_text)

    return [
        ("data/char/character/ruah/ph2chr09.dmo", ruah_dmo),
        ("data/char/character/ruah/ph2chr09.cmn", fel_cmn),
        ("data/char/character/ruah/ph2chr09.def", ruah_def),
        ("data/char/character/ruah/ph2chr09.tga", tga_body),
        ("data/char/character/ruah/ph2chr09_face.tga", tga_face),
        ("data/char/character/ruah/ph2chr09_hair.tga", tga_hair),
    ]
