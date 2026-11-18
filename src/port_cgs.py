import os
import sys
import argparse
import struct
import ctypes
import time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PC_DIR = os.environ.get('PARK_PC_DIR', '.')
PS2_DIR = os.environ.get('PARK_PS2_DIR', '.')
ORIG_PA_CG = os.path.join(PS2_DIR, 'PA_CG.DAT')
NEW_PA_CG = os.path.join(PS2_DIR, 'PA_CG_NEW.DAT')

dll = None
def init_dll(dll_path: str):
    global dll
    dll = ctypes.CDLL(dll_path)
    dll.decompress_zzz.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.decompress_zzz.restype = ctypes.c_int
    dll.compress_zzz.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.compress_zzz.restype = ctypes.c_int
    dll.decode_epa.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    dll.decode_epa.restype = ctypes.c_int

IDX_SWIZZLE = np.array([(i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1) for i in range(256)], dtype=np.uint8)
SKIP_EPAS = {'mouse_on_se.epa', 'white.epa', 'black.epa', 'fl_yoru_zyo_g.epa', 'fl_yu_zyo_g.epa'}


def decompress_zzz(raw: bytes) -> bytes:
    out_len = struct.unpack_from('<I', raw, 8)[0]
    buf = ctypes.create_string_buffer(out_len + 256)
    n = dll.decompress_zzz(raw, len(raw), buf, len(buf))
    if n != out_len:
        raise RuntimeError(f'decompress_zzz mismatch: got {n}, expected {out_len}')
    return buf.raw[:n]


def compress_zzz(raw: bytes) -> bytes:
    max_out = len(raw) + len(raw) // 2 + 4096
    buf = ctypes.create_string_buffer(max_out)
    n = dll.compress_zzz(raw, len(raw), buf, max_out)
    if n <= 0:
        raise RuntimeError(f'compress_zzz failed: {n}')
    return buf.raw[:n]


def load_pc_index():
    pc_idx = {}
    handles = []
    for arch in ['archive.dat', 'archive1.dat', 'archive2.dat']:
        fh = open(os.path.join(PC_DIR, arch), 'rb')
        handles.append(fh)
        fh.read(12)
        c = struct.unpack('<I', fh.read(4))[0]
        names = [fh.read(32).split(b'\x00', 1)[0].decode('cp932', 'replace') for _ in range(c)]
        pairs = [struct.unpack('<II', fh.read(8)) for _ in range(c)]
        db = fh.tell()
        for k, n in enumerate(names):
            if n.lower().endswith('.epa'):
                val = (fh, db + pairs[k][0], pairs[k][1], n)
                pc_idx[n.upper()] = val
                pc_idx[os.path.splitext(n)[0].upper()] = val
    return pc_idx, handles


_epa_cache = {}
def decode_pc_epa(pc_idx, key: str) -> Image.Image | None:
    ukey = key.upper()
    if ukey in _epa_cache:
        return _epa_cache[ukey]
    ent = pc_idx.get(ukey)
    if not ent:
        return None
    fh, off, sz, _ = ent
    fh.seek(off)
    raw = fh.read(sz)
    if raw[:4] != b'EP\x01\x01':
        return None
    mode, w, h = struct.unpack_from('<III', raw, 4)
    m = mode & 0xff
    bpp = {0: 1, 1: 3, 2: 4}.get(m)
    if not bpp:
        return None
    target = w * h * bpp
    buf = ctypes.create_string_buffer(target)
    if dll.decode_epa(raw, len(raw), buf, target) != target:
        return None
    arr = np.frombuffer(buf.raw, dtype=np.uint8)
    if m == 0:
        pal = np.frombuffer(raw[16:16 + 0x300], dtype=np.uint8).reshape(256, 3)[:, ::-1]
        rgba = np.concatenate([pal[arr.reshape(h, w)], np.full((h, w, 1), 255, dtype=np.uint8)], axis=-1)
    elif m == 1:
        ch = arr.reshape(3, h, w)
        rgba = np.stack([ch[2], ch[1], ch[0], np.full((h, w), 255, dtype=np.uint8)], axis=-1)
    else:
        ch = arr.reshape(4, h, w)
        rgba = np.stack([ch[2], ch[1], ch[0], ch[3]], axis=-1)
    im = Image.fromarray(rgba, 'RGBA')
    if len(_epa_cache) < 256:
        _epa_cache[ukey] = im
    return im


def build_special_image(pc_idx, pname_u: str, ename_u: str, layer_idx: int, bw: int, bh: int) -> Image.Image | None:
    if ename_u == 'PG04_0_01_KYARA2.EPA':
        k2 = decode_pc_epa(pc_idx, 'PG04_0_01_KYARA2.EPA')
        k2_rs = k2.resize((round(k2.width * 0.8), 450), Image.Resampling.LANCZOS)
        crop = k2_rs.crop((589, 0, k2_rs.width, 450))
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        canvas.paste(crop, (0, 1))
        return canvas

    if ename_u == 'PG04_0_01_KYARA1.EPA':
        k1 = decode_pc_epa(pc_idx, 'PG04_0_01_KYARA1.EPA')
        k2 = decode_pc_epa(pc_idx, 'PG04_0_01_KYARA2.EPA')
        k1_rs = k1.resize((round(k1.width * 0.8), 450), Image.Resampling.LANCZOS)
        k2_rs = k2.resize((round(k2.width * 0.8), 450), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        filia_crop = k2_rs.crop((0, 0, 285, 439))
        canvas.paste(filia_crop, (500, 11), filia_crop)
        kp_crop = k1_rs.crop((2, 0, 787, 447))
        canvas.paste(kp_crop, (0, 3), kp_crop)
        return canvas

    if ename_u == 'PG09_6_00_BACK.EPA':
        bg = decode_pc_epa(pc_idx, 'PG09_6_00_BACK.EPA').crop((0, 0, 800, 600)).resize((640, 450), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        canvas.paste(bg, (0, 0))
        return canvas

    if ename_u == 'PG09_6_00_RITTE.EPA':
        rt = decode_pc_epa(pc_idx, 'PG09_6_00_RITTE.EPA').crop((0, 0, 800, 600)).resize((640, 450), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        canvas.paste(rt, (0, 0))
        return canvas

    if pname_u == 'PG09_6_00_MAIN' and ename_u == 'PG09_6_00.EPA':
        bg = decode_pc_epa(pc_idx, 'PG09_6_00_BACK.EPA').crop((0, 0, 800, 600))
        rt = decode_pc_epa(pc_idx, 'PG09_6_00_RITTE.EPA').crop((0, 0, 800, 600))
        comp = Image.alpha_composite(bg, rt).resize((640, 450), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        canvas.paste(comp, (0, 0))
        return canvas

    if pname_u == 'PGIN_7_03AS':
        if ename_u == 'PGIN_7_03L1.EPA':
            im = decode_pc_epa(pc_idx, 'PGIN_7_03L.EPA').crop((0, 0, 800, 1200)).resize((640, 900), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
            canvas.paste(im, (0, 0))
            return canvas
        if ename_u == 'PGIN_7_03L2.EPA':
            im = decode_pc_epa(pc_idx, 'PGIN_7_03L.EPA').crop((800, 0, 1600, 1200)).resize((640, 900), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
            canvas.paste(im, (0, 0))
            return canvas

    if ename_u in ('PG12_3_02L.EPA', 'PG12_3_02BKL.EPA'):
        im = decode_pc_epa(pc_idx, ename_u).resize((640, 740), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        canvas.paste(im, (0, 0))
        return canvas

    if pname_u == 'PG10_3_00_MAIN' and ename_u == 'PG10_3_00.EPA':
        # Already uncensored on PS2; preserve original layer untouched
        return None

    if ename_u == 'PG01_1_00SHIBUKI.EPA':
        # Scroll-width splash overlay; preserve PS2 framing
        return None

    if ename_u in ('PG13_0_CAP01.EPA', 'PG13_0_CAP02.EPA', 'PG13_0_CAP03.EPA'):
        im = decode_pc_epa(pc_idx, ename_u).crop((10, 10, 810, 610)).resize((640, 450), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
        canvas.paste(im, (0, 0))
        return canvas

    return False  # Not a special case


def quantize_to_ps2(canvas_im: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Quantize RGBA image to 256-color indexed buffer + CSM1-swizzled PS2 CLUT (alpha 0..0x80)."""
    rgba = np.array(canvas_im, dtype=np.uint8)
    h, w = rgba.shape[:2]
    alpha = rgba[:, :, 3]
    trans_mask = alpha == 0
    has_trans = bool(trans_mask.any())
    has_semitrans = bool(((alpha > 0) & (alpha < 255)).any())

    if has_trans and not has_semitrans:
        # Pure opaque content + transparent padding/cutout: use MEDIANCUT + FS on RGB for smooth gradients
        rgb_im = Image.fromarray(rgba[:, :, :3], 'RGB')
        q_im = rgb_im.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        raw_rgb = np.array(q_im.getpalette('RGB'), dtype=np.uint8).reshape(-1, 3)
        n_pal = min(255, len(raw_rgb))
        clut = np.zeros((256, 4), dtype=np.uint8)
        clut[1:1 + n_pal, :3] = raw_rgb[:n_pal]
        clut[1:1 + n_pal, 3] = 255
        idx = np.array(q_im, dtype=np.uint8) + 1
        idx[trans_mask] = 0
    elif has_trans:
        # Reserve index 0 for exact transparent [0,0,0,0]
        q_im = canvas_im.quantize(colors=255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
        raw_pal = np.array(q_im.getpalette('RGBA'), dtype=np.uint8).reshape(-1, 4)
        n_pal = min(255, len(raw_pal))
        clut = np.zeros((256, 4), dtype=np.uint8)
        clut[1:1 + n_pal] = raw_pal[:n_pal]
        idx = np.array(q_im, dtype=np.uint8) + 1
        idx[trans_mask] = 0
    else:
        rgb_im = Image.fromarray(rgba[:, :, :3], 'RGB')
        q_im = rgb_im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        raw_rgb = np.array(q_im.getpalette('RGB'), dtype=np.uint8).reshape(-1, 3)
        n_pal = min(256, len(raw_rgb))
        clut = np.zeros((256, 4), dtype=np.uint8)
        clut[:n_pal, :3] = raw_rgb[:n_pal]
        clut[:n_pal, 3] = 255
        idx = np.array(q_im, dtype=np.uint8)

    # Convert alpha 0..255 -> 0..128 (0x80)
    clut_ps2 = clut.copy()
    clut_ps2[:, 3] = np.clip((clut[:, 3].astype(np.int32) * 128 + 127) // 255, 0, 128).astype(np.uint8)
    clut_swz = clut_ps2[IDX_SWIZZLE]
    return idx.reshape(h, w), clut_swz


def patch_ps2_layer(dec_ba: bytearray, tpos: int, canvas_im: Image.Image):
    tag = bytes(dec_ba[tpos:tpos + 4])
    idx, clut_swz = quantize_to_ps2(canvas_im)
    clut_bytes = clut_swz.tobytes()

    if tag == b'TIM2':
        total_sz, clut_sz, img_sz, hdr_sz, clut_colors, pict_fmt, mip, clut_t, img_t, w, h = struct.unpack_from(
            '<IIIHHBBBBHH', dec_ba, tpos + 16
        )
        assert clut_t == 3 and img_t == 5 and clut_sz == 1024 and img_sz == w * h
        assert idx.shape == (h, w)
        img_off = tpos + 16 + hdr_sz
        clut_off = img_off + img_sz
        dec_ba[img_off:img_off + img_sz] = idx.tobytes()
        dec_ba[clut_off:clut_off + 1024] = clut_bytes
    elif tag == b'PTL\x00':
        _, ttype, cols, rows, n_tiles, tw, th, pw, ph = struct.unpack_from('<4sBBBBIIII', dec_ba, tpos)
        assert idx.shape == (th, tw)
        written_cluts = set()
        for t in range(n_tiles):
            tx, ty, aw, ah, bw_t, bh_t, px_off, clut_off = struct.unpack_from('<HHHHHHII', dec_ba, tpos + 0x20 + t * 20)
            if clut_off not in written_cluts:
                dec_ba[tpos + clut_off:tpos + clut_off + 1024] = clut_bytes
                written_cluts.add(clut_off)
            tile_buf = np.zeros((bh_t, bw_t), dtype=np.uint8)
            tile_buf[:ah, :aw] = idx[ty:ty + ah, tx:tx + aw]
            dec_ba[tpos + px_off:tpos + px_off + bw_t * bh_t] = tile_buf.tobytes()
    else:
        raise RuntimeError(f'Unsupported texture tag: {tag}')


def get_ps2_buf_size(dec: bytes, tpos: int):
    tag = dec[tpos:tpos + 4]
    if tag == b'TIM2':
        w, h = struct.unpack_from('<HH', dec, tpos + 16 + 20)
        return w, h
    elif tag == b'PTL\x00':
        tw, th = struct.unpack_from('<II', dec, tpos + 8)
        return tw, th
    return None, None


def is_target_pag(pname_u: str) -> bool:
    return (
        pname_u.startswith('PG')
        or 'MEMORY' in pname_u
        or 'BUST' in pname_u
        or pname_u.startswith('PK05_6_03')
        or pname_u.startswith('PK08_3_09')
    )


def main():
    global PC_DIR, PS2_DIR, ORIG_PA_CG, NEW_PA_CG
    parser = argparse.ArgumentParser(description='Port matching PC CGs into PS2 PA_CG.DAT')
    parser.add_argument('--pc-dir', default=PC_DIR, help='Directory containing PC archive*.dat')
    parser.add_argument('--ps2-dir', default=PS2_DIR, help='Directory containing extracted PA_CG.DAT')
    parser.add_argument('--dll', default=os.path.join(HERE, 'zzz_helper.dll'), help='Path to compiled zzz_helper.dll')
    parser.add_argument('--dry-run', action='store_true', help='Validate without writing PA_CG_NEW.DAT')
    args = parser.parse_args()
    PC_DIR = args.pc_dir
    PS2_DIR = args.ps2_dir
    ORIG_PA_CG = os.path.join(PS2_DIR, 'PA_CG.DAT')
    NEW_PA_CG = os.path.join(PS2_DIR, 'PA_CG_NEW.DAT')
    init_dll(args.dll)
    dry_run = args.dry_run
    pc_idx, pc_handles = load_pc_index()
    t0 = time.time()

    with open(ORIG_PA_CG, 'rb') as f:
        afs_hdr = f.read(0x800)
        f.seek(0x800)
        flk_hdr = f.read(32)
        magic, ver, u1, u2, u3, fsz, cnt, flags = struct.unpack('<4s7I', flk_hdr)
        assert magic == b'FLK\x00' and cnt == 3810
        orig_entries = [struct.unpack('<II', f.read(8)) for _ in range(cnt)]
        orig_file_size = os.path.getsize(ORIG_PA_CG)

        modified_blobs = {}
        over_dims = []
        ported_layers = 0
        ported_entries = []

        for idx in range(cnt - 1):
            off, sz = orig_entries[idx]
            f.seek(off)
            raw = f.read(sz)
            was_zzz = (raw[:4] == b'ZZZ\x00')
            dec = decompress_zzz(raw) if was_zzz else raw
            if dec[:4] != b'PAG\x00':
                continue
            _, _, lcnt, _, _, _, ftr_off = struct.unpack_from('<4s6I', dec, 0)
            pname = dec[0x64:0x84].split(b'\x00', 1)[0].decode('cp932', 'replace')
            pname_u = pname.upper()
            if not is_target_pag(pname_u):
                continue

            dec_ba = bytearray(dec)
            entry_changed = False
            for r in range(lcnt):
                ro = ftr_off + r * 44
                ename = dec[ro:ro + 32].split(b'\x00', 1)[0].decode('cp932', 'replace')
                ename_u = ename.upper()
                tpos, _, ew, eh = struct.unpack_from('<IIHH', dec, ro + 32)
                if tpos == 0 or ename.lower() in SKIP_EPAS:
                    continue
                bw, bh = get_ps2_buf_size(dec, tpos)
                if not bw:
                    continue

                sp = build_special_image(pc_idx, pname_u, ename_u, r, bw, bh)
                if sp is None:
                    continue  # Explicitly preserve
                if sp is not False:
                    canvas_im = sp
                else:
                    lookup_key = ename_u if ename_u in pc_idx else (pname_u if lcnt == 1 else '')
                    pc_im = decode_pc_epa(pc_idx, lookup_key) if lookup_key else None
                    if pc_im is None:
                        continue
                    sw = round(pc_im.width * 0.8)
                    sh = round(pc_im.height * 0.75)
                    if sw > bw or sh > bh:
                        over_dims.append((idx, r, pname, ename, pc_im.width, pc_im.height, sw, sh, bw, bh))
                        sw = min(sw, bw)
                        sh = min(sh, bh)
                    rs = pc_im.resize((sw, sh), Image.Resampling.LANCZOS)
                    canvas_im = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
                    canvas_im.paste(rs, (0, 0))

                patch_ps2_layer(dec_ba, tpos, canvas_im)
                entry_changed = True
                ported_layers += 1

            if entry_changed:
                ported_entries.append((idx, pname))
                if not dry_run:
                    new_blob = compress_zzz(bytes(dec_ba)) if was_zzz else bytes(dec_ba)
                    modified_blobs[idx] = new_blob

        print(f'Target PAG entries modified: {len(ported_entries)}, layers ported: {ported_layers}')
        print(f'Over-dim clamps: {len(over_dims)}')
        for od in over_dims[:20]:
            print('  OVER:', od)

        if dry_run:
            return

        # Rebuild PA_CG_NEW.DAT
        cur_off = orig_entries[0][0]
        new_entries = []
        with open(NEW_PA_CG, 'wb') as out:
            out.write(afs_hdr)
            out.write(flk_hdr)
            out.write(b'\x00' * (cnt * 8))
            if cur_off > out.tell():
                out.write(b'\x00' * (cur_off - out.tell()))

            for idx in range(cnt):
                if idx in modified_blobs:
                    blob = modified_blobs[idx]
                else:
                    off, sz = orig_entries[idx]
                    f.seek(off)
                    blob = f.read(sz)
                out.seek(cur_off)
                out.write(blob)
                new_entries.append((cur_off, len(blob)))
                cur_off = (cur_off + len(blob) + 0x7ff) & ~0x7ff

            print(f'Rebuilt used end: {cur_off} (0x{cur_off:x}), orig limit: {orig_file_size} (0x{orig_file_size:x}), diff: {cur_off - orig_file_size:+d} bytes')
            if cur_off <= orig_file_size:
                if orig_file_size > out.tell():
                    out.seek(orig_file_size - 1)
                    out.write(b'\x00')
            out.seek(0x820)
            for o, s in new_entries:
                out.write(struct.pack('<II', o, s))

    print(f'Done in {time.time() - t0:.2f}s')


if __name__ == '__main__':
    main()
