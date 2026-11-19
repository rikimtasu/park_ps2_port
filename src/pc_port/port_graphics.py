import json
import os
import struct
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

STAGED_DIR = os.path.join(common.WORK_DIR, "staged")
GFX_OUT_DIR = os.path.join(STAGED_DIR, "gfx")
PREVIEW_DIR = os.path.join(STAGED_DIR, "gfx_preview")
MANIFEST_PATH = os.path.join(STAGED_DIR, "needed_assets.json")


def decode_tim2_indexed(buf: bytes, tpos: int = 0):
    """Return (idx_2d uint8[h,w], clut uint8[256,4] RGBA) for an 8-bit indexed TIM2."""
    assert buf[tpos:tpos + 4] == b"TIM2", f"Expected TIM2 at 0x{tpos:x}, got {buf[tpos:tpos+4]!r}"
    total_sz, clut_sz, img_sz, hdr_sz, clut_colors, pict_fmt, mip, clut_t, img_t, w, h = struct.unpack_from(
        "<IIIHHBBBBHH", buf, tpos + 16
    )
    assert img_t == 5 and clut_t == 3, f"Expected 8-bit indexed TIM2, got img_t={img_t} clut_t={clut_t}"
    img_off = tpos + 16 + hdr_sz
    clut_off = img_off + img_sz
    idx = np.frombuffer(buf, dtype=np.uint8, count=w * h, offset=img_off).reshape(h, w).copy()
    clut = np.frombuffer(buf, dtype=np.uint8, count=1024, offset=clut_off).reshape(256, 4)[common.IDX_SWIZZLE].copy()
    clut[:, 3] = np.clip((clut[:, 3].astype(np.int32) * 255 + 64) // 128, 0, 255).astype(np.uint8)
    return idx, clut


def upscale_ps2_layer(im: Image.Image, pc_w: int, pc_h: int) -> Image.Image:
    """Crop PS2 alignment padding and upscale PS2 0.8x/0.75x layer to PC exact resolution."""
    tw, th = im.size
    if pc_w == 0 or pc_h == 0:
        # Fallback for backgrounds with zero footer dims (e.g. PB017A: 640x456 -> 800x600)
        target_w = round(tw / 0.8)
        target_h = 600 if 448 <= th <= 464 else round(th / 0.75)
        src_w = min(tw, round(target_w * 0.8))
        src_h = min(th, round(target_h * 0.75))
    elif pc_w <= tw and pc_h <= th and (tw - pc_w) <= 16 and (th - pc_h) <= 16:
        # Unscaled 1:1 padded texture (e.g. PRISM_NAME_TEXT225: 179x21 in 184x21)
        target_w, target_h = pc_w, pc_h
        src_w, src_h = pc_w, pc_h
    else:
        fw0 = round(pc_w * 0.8)
        fh0 = round(pc_h * 0.75)
        cols = max(1, round(tw / fw0)) if (fw0 > 0 and tw >= fw0 * 1.5) else 1
        rows = max(1, round(th / fh0)) if (fh0 > 0 and th >= fh0 * 1.5) else 1
        target_w = pc_w * cols
        target_h = pc_h * rows
        src_w = min(tw, round(target_w * 0.8))
        src_h = min(th, round(target_h * 0.75))

    cropped = im.crop((0, 0, src_w, src_h)) if (src_w != tw or src_h != th) else im
    if cropped.size != (target_w, target_h):
        return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    return cropped


def extract_pag_gb_and_anm(dec: bytes, gb_seen: set, new_gb_recs: list, pc_existing_files: set, written_anms: dict):
    """Extract all embedded 1092B PJGraphicDef records and ANM1 files from a decompressed PAG."""
    magic, ver, lcnt, u1, u2, hoff, foff = struct.unpack_from("<4s6I", dec, 0)
    assert magic == b"PAG\x00", f"Bad PAG magic: {magic!r}"
    if hoff + 44 > len(dec):
        return []
    gb_off_rel, n_gb, _ = struct.unpack_from("<III", dec, hoff + 32)
    gb_abs = hoff + gb_off_rel
    rec_infos = []
    for k in range(n_gb):
        base = gb_abs + k * 0x668
        if base + 0x1c0 + 1092 > len(dec):
            break
        fw, fh, anm_off, anm_sz = struct.unpack_from("<4I", dec, base + 0x1b0)
        rec = dec[base + 0x1c0 : base + 0x1c0 + 1092]
        dname = rec[60:92].split(b"\x00", 1)[0].decode("cp932", "replace")
        epa_name = rec[92:124].split(b"\x00", 1)[0].decode("cp932", "replace")
        anm_name = rec[124:156].split(b"\x00", 1)[0].decode("cp932", "replace")
        rec_infos.append((dname, epa_name, anm_name))

        du = dname.upper()
        if du and du not in gb_seen:
            gb_seen.add(du)
            new_gb_recs.append(rec)

        if anm_name and anm_sz > 0:
            au = anm_name.upper()
            if au not in pc_existing_files and au not in written_anms:
                anm_bytes = dec[anm_off : anm_off + anm_sz]
                assert anm_bytes[:4] == b"ANM1", f"Bad ANM1 for {dname}/{anm_name} at 0x{anm_off:x}: {anm_bytes[:4]!r}"
                written_anms[au] = (anm_name, anm_bytes)
    return rec_infos


def main():
    os.makedirs(GFX_OUT_DIR, exist_ok=True)
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        man = json.load(f)

    # Index existing PC files so we never clobber vanilla EPAs/ANMs
    pc_existing_files = set()
    for arch in ("archive.dat", "archive1.dat", "archive2.dat"):
        names, _, _ = common.read_pc_archive_index(os.path.join(common.PC_DIR, arch))
        for n in names:
            pc_existing_files.add(n.upper())

    pc_gb_orig = bytearray(common.read_pc_archive_file("archive.dat", "graphic.bin"))
    pc_gb_cnt = struct.unpack_from("<I", pc_gb_orig, 12)[0]
    gb_seen = set()
    for i in range(pc_gb_cnt):
        dname = pc_gb_orig[16 + i * 1092 + 60 : 16 + i * 1092 + 92].split(b"\x00", 1)[0].decode("cp932", "replace")
        gb_seen.add(dname.upper())

    new_gb_recs = []
    written_epas = {}   # UPPER -> (exact_name, epa_bytes)
    written_anms = {}   # UPPER -> (exact_name, anm_bytes)

    iso = common.IsoReader()

    # ================================================================
    # 1. Process all needed PAGs
    # ================================================================
    print(f"=== Processing {len(man['pags'])} PAG graphics ===")
    for lo_s, nm in sorted(man["pags"].items(), key=lambda kv: int(kv[0])):
        lo = int(lo_s)
        raw = iso.read_flk_entry("PA_CG.DAT", lo)
        dec = common.decompress_zzz(raw)
        rec_infos = extract_pag_gb_and_anm(dec, gb_seen, new_gb_recs, pc_existing_files, written_anms)

        # Build preferred casing map from PJGraphicDef epa names
        casing = {epa.upper(): epa for _, epa, _ in rec_infos if epa}

        _, _, lcnt, _, _, hoff, foff = struct.unpack_from("<4s6I", dec, 0)
        for li in range(lcnt):
            ename_b, tpos, unk, pc_w, pc_h = struct.unpack_from("<32sIIHH", dec, foff + li * 44)
            ename = ename_b.split(b"\x00", 1)[0].decode("cp932", "replace")
            eu = ename.upper()
            if eu in pc_existing_files or eu in written_epas:
                continue
            tag = dec[tpos:tpos + 4]
            if tag not in (b"TIM2", b"PTL\x00"):
                raise RuntimeError(f"Unsupported non-PC texture tag {tag!r} in PAG[{lo}] {nm} layer {ename}")

            im = common.decode_tim2_rgba(dec, tpos)
            up = upscale_ps2_layer(im, pc_w, pc_h)
            epa_bytes = common.encode_epa_image(up)
            # Round-trip sanity check
            rt = common.decode_epa_image(epa_bytes)
            assert rt.size == up.size, f"EPA round-trip size mismatch for {ename}"

            out_name = casing.get(eu, ename)
            written_epas[eu] = (out_name, epa_bytes)

            # Save Prism #225 PNGs for battle1.dat TGA generation
            if lo == 1965:
                up.save(os.path.join(STAGED_DIR, "prism225.png"))
            elif lo == 1740:
                up.save(os.path.join(STAGED_DIR, "prism_name_text225.png"))

            # Save visual preview for key CGs
            if eu in ("PS02_8_00A.EPA", "PSED_8_00A.EPA", "PSMG_8_02A_RUA.EPA", "PS11_8_00A_CHR.EPA"):
                rt.save(os.path.join(PREVIEW_DIR, f"{os.path.splitext(out_name)[0]}.png"))

    print(f"  After PAGs: {len(new_gb_recs)} graphic.bin recs, {len(written_epas)} EPAs, {len(written_anms)} ANMs")

    # ================================================================
    # 2. Process all needed PXG sub-sprites (Ruah standing sprites)
    # ================================================================
    pxg_groups = {}
    for k_str, name in man["pxgs"].items():
        cg_idx_s, sub_idx_s = k_str.split(":")
        pxg_groups.setdefault(int(cg_idx_s), []).append((int(sub_idx_s), name))

    print(f"=== Processing {len(man['pxgs'])} PXG sub-sprites across {len(pxg_groups)} packs ===")
    previewed_pxg = 0
    for cg_idx, subs in sorted(pxg_groups.items()):
        raw = iso.read_flk_entry("PA_CG.DAT", cg_idx)
        assert raw[:4] == b"PXG\x00"
        _, n_sub, base_off, base_sz, tbl1_off, tbl2_off = struct.unpack_from("<4sIIIII", raw, 0)

        # Decode base TIM2
        base_dec = common.decompress_zzz(raw[base_off : base_off + base_sz])
        base_idx, clut = decode_tim2_indexed(base_dec, 0)
        bh, bw = base_idx.shape

        # Parse & decompress all active tbl1 diff-strip slots
        slots = []
        off = 0x38
        while off + 24 <= tbl2_off:
            zoff, zsz, dsz, sid, x, y, w, h = struct.unpack_from("<IIIIHHHH", raw, off)
            off += 24
            if zsz == 0 or w == 0 or h == 0:
                continue
            pool_raw = common.decompress_zzz(raw[zoff : zoff + zsz])
            n_rows = len(pool_raw) // w
            pool = np.frombuffer(pool_raw, dtype=np.uint8, count=n_rows * w).reshape(n_rows, w)
            slots.append((sid, x, y, w, h, pool))

        for sub_idx, sub_name in sorted(subs):
            ro = tbl2_off + sub_idx * 128
            z_off, z_sz, r1, r2, patch_off, patch_sz, _, _, s1, s2, s3 = struct.unpack_from("<8I32s32s32s", raw, ro)
            def_name = s1.split(b"\x00", 1)[0].decode("cp932", "replace")
            body_epa_tbl2 = s2.split(b"\x00", 1)[0].decode("cp932", "replace")
            eye_epa_tbl2 = s3.split(b"\x00", 1)[0].decode("cp932", "replace")

            pdec = common.decompress_zzz(raw[z_off : z_off + z_sz])
            rec_infos = extract_pag_gb_and_anm(pdec, gb_seen, new_gb_recs, pc_existing_files, written_anms)
            body_epa_name = rec_infos[0][1] if (rec_infos and rec_infos[0][1]) else body_epa_tbl2

            _, _, lcnt, _, _, hoff, foff = struct.unpack_from("<4s6I", pdec, 0)
            footers = []
            for li in range(lcnt):
                ename_b, tpos, unk, pc_w, pc_h = struct.unpack_from("<32sIIHH", pdec, foff + li * 44)
                footers.append((ename_b.split(b"\x00", 1)[0].decode("cp932", "replace"), pc_w, pc_h))

            # Reconstruct body canvas & eye-blink sheet
            row_indices = struct.unpack_from(f"<{patch_sz // 2}H", pdec, patch_off)
            canvas = base_idx.copy()
            eye_patch = None
            ri = 0
            for sid, x, y, w, h, pool in slots:
                idx_rows = np.array(row_indices[ri : ri + h], dtype=np.int32)
                ri += h
                patch = pool[idx_rows]
                if sid == 1:
                    eye_patch = patch
                    fh = h // 3
                    canvas[y : y + fh, x : x + w] = patch[:fh]
                else:
                    canvas[y : y + h, x : x + w] = patch
            assert ri == len(row_indices), f"Row index mismatch in PXG[{cg_idx}] sub {sub_idx}: {ri} vs {len(row_indices)}"

            # Export body EPA
            bu = body_epa_name.upper()
            if bu not in pc_existing_files and bu not in written_epas:
                pc_w0, pc_h0 = footers[0][1], footers[0][2]
                im_body = Image.fromarray(clut[canvas], "RGBA")
                up_body = upscale_ps2_layer(im_body, pc_w0, pc_h0)
                epa_bytes = common.encode_epa_image(up_body, force_rgba=True)
                rt = common.decode_epa_image(epa_bytes)
                assert rt.size == up_body.size
                written_epas[bu] = (body_epa_name, epa_bytes)

                if def_name.upper() in ("PA08_A_A00", "PA08_L_A00U", "PA08_L_B03") or previewed_pxg < 2:
                    rt.save(os.path.join(PREVIEW_DIR, f"{def_name}.png"))
                    previewed_pxg += 1

            # Export eye-blink EPA when animated (lcnt >= 2)
            if lcnt >= 2 and eye_patch is not None:
                # Get exact eye epa name from ANM1 or tbl2
                eye_epa_name = eye_epa_tbl2 or footers[1][0]
                eu = eye_epa_name.upper()
                if eu and eu not in pc_existing_files and eu not in written_epas:
                    pc_w1, pc_h1 = footers[1][1], footers[1][2]
                    im_eye = Image.fromarray(clut[eye_patch], "RGBA")
                    up_eye = im_eye.resize((pc_w1, pc_h1), Image.Resampling.LANCZOS) if im_eye.size != (pc_w1, pc_h1) else im_eye
                    epa_bytes = common.encode_epa_image(up_eye, force_rgba=True)
                    rt = common.decode_epa_image(epa_bytes)
                    assert rt.size == up_eye.size
                    written_epas[eu] = (eye_epa_name, epa_bytes)

                    if def_name.upper() == "PA08_A_A00":
                        rt.save(os.path.join(PREVIEW_DIR, f"{def_name}_eye.png"))

        print(f"  PXG[{cg_idx}]: processed {len(subs)} sprites")

    iso.close()

    # ================================================================
    # 3. Write all staged graphics & patched graphic.bin
    # ================================================================
    for _, (name, data) in written_epas.items():
        with open(os.path.join(GFX_OUT_DIR, name), "wb") as f:
            f.write(data)
    for _, (name, data) in written_anms.items():
        with open(os.path.join(GFX_OUT_DIR, name), "wb") as f:
            f.write(data)

    # Patch graphic.bin
    new_cnt = pc_gb_cnt + len(new_gb_recs)
    struct.pack_into("<I", pc_gb_orig, 12, new_cnt)
    for rec in new_gb_recs:
        pc_gb_orig.extend(rec)
    with open(os.path.join(STAGED_DIR, "graphic.bin"), "wb") as f:
        f.write(pc_gb_orig)

    # Save index manifest for build_mod.py
    gfx_manifest = {
        "epas": [name for _, (name, _) in sorted(written_epas.items())],
        "anms": [name for _, (name, _) in sorted(written_anms.items())],
        "new_gb_count": len(new_gb_recs),
        "total_gb_count": new_cnt,
    }
    with open(os.path.join(STAGED_DIR, "gfx_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(gfx_manifest, f, indent=2, ensure_ascii=False)

    print(f"\n=== Graphics Port Complete! ===")
    print(f"  graphic.bin: {len(pc_gb_orig):,} bytes ({new_cnt} entries, +{len(new_gb_recs)} new)")
    print(f"  EPAs written: {len(written_epas)}")
    print(f"  ANMs written: {len(written_anms)}")
    print(f"  Previews saved to: {PREVIEW_DIR}")


if __name__ == "__main__":
    main()
