import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import patch_exe


def read_pac2_member(arch_path: str, member_upper: str, cache: dict) -> bytes | None:
    if arch_path not in cache:
        names, pairs, db = common.read_pc_archive_index(arch_path)
        cache[arch_path] = ({n.upper(): (o, s) for n, (o, s) in zip(names, pairs)}, db)
    idx_map, db = cache[arch_path]
    if member_upper not in idx_map:
        return None
    o, s = idx_map[member_upper]
    with open(arch_path, "rb") as f:
        f.seek(db + o)
        return f.read(s)


def open_prsm_index(path: str, dec_tbl: bytes):
    with open(path, "rb") as f:
        magic, cnt, hsz = struct.unpack("<4sII", f.read(12))
        assert magic == b"PRSM", f"Bad PRSM magic in {path}"
        f.seek(0)
        hdr = bytearray(f.read(hsz))
        for i in range(12, hsz):
            hdr[i] = dec_tbl[(i % 6) * 256 + hdr[i]]
        files = {}
        for idx in range(cnt):
            noff, foff, fsz = struct.unpack_from("<III", hdr, 12 + idx * 12)
            rec = common.prsm_lz_decode(hdr, noff)
            name = rec[:0x7F].split(b"\x00", 1)[0].decode("cp932", "replace")
            files[name.lower().replace("\\", "/")] = (name, foff, fsz, rec[0x7F], struct.unpack_from("<I", rec, 0x80)[0])
    return files


def read_prsm_member(path: str, entry, dec_tbl: bytes) -> bytes:
    _, foff, fsz, kb, usz = entry
    with open(path, "rb") as f:
        f.seek(foff)
        raw = bytearray(f.read(fsz))
    for i in range(fsz):
        raw[i] = dec_tbl[(i % 6) * 256 + ((raw[i] - kb) & 0xFF)]
    return common.prsm_lz_decode(raw, 0) if usz > 0 else bytes(raw)


def main():
    errors = []
    mod_dir = common.MOD_OUT_DIR
    pc_dir = common.PC_DIR

    # ================================================================
    # 1. Verify Non-Destructive File List (Zero Collisions with Vanilla PC Files)
    # ================================================================
    print("=== [1/6] Checking Non-Destructive Mod Isolation ===")
    vanilla_pc_files = {
        "p_ark201.exe", "psetup.exe", "install.ini",
        "archive.dat", "archive1.dat", "archive2.dat",
        "battle.dat", "bgm.dat", "se.dat",
        "voice.dat", "voice1.dat", "voice2.dat",
    } | {f"exp\\pop{i:02d}.dat" for i in range(21)}
    mod_rel_files = []
    for root, _, fns in os.walk(mod_dir):
        for fn in fns:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, mod_dir)
            mod_rel_files.append(rel)
            if rel.lower() in vanilla_pc_files:
                errors.append(f"COLLISION with original PC file: {rel}")
    print(f"  Mod files ({len(mod_rel_files)}): {sorted(mod_rel_files)}")
    assert not errors, f"Non-destructive check failed: {errors}"
    print("  PASS: Zero collisions with original PC game files!")

    # ================================================================
    # 2. Simulate P_ARK201.exe archive.ini First-Archive-Wins Mount
    # ================================================================
    print("\n=== [2/6] Simulating archive.ini Mount Order ===")
    with open(os.path.join(mod_dir, "archive.ini"), "r", encoding="ascii") as f:
        mount_list = [l.strip()[5:] for l in f if l.strip().lower().startswith("file=")]
    print(f"  Mount order: {mount_list}")

    vfs = {}  # UPPER -> (arch_path, orig_name, offset, size, db)
    for arch_name in mount_list:
        p = os.path.join(mod_dir, arch_name)
        if not os.path.exists(p):
            p = os.path.join(pc_dir, arch_name)
        assert os.path.exists(p), f"Archive listed in archive.ini missing: {arch_name}"
        names, pairs, db = common.read_pc_archive_index(p)
        added = 0
        for nm, (o, s) in zip(names, pairs):
            u = nm.upper()
            if u not in vfs:
                vfs[u] = (p, nm, o, s, db)
                added += 1
        print(f"  Mounted {arch_name:16s}: {len(names):6d} entries ({added:6d} active/winning)")

    def read_vfs(name: str) -> bytes:
        p, _, o, s, db = vfs[name.upper()]
        with open(p, "rb") as f:
            f.seek(db + o)
            return f.read(s)

    # Confirm core files win from ruah_mod.dat!
    for core in ("scenario.dat", "textdata.bin", "filename.dat", "graphic.bin", "BGM.ini"):
        winner = os.path.basename(vfs[core.upper()][0])
        assert winner == "ruah_mod.dat", f"{core} did not resolve to ruah_mod.dat (got {winner})"
    print("  PASS: All 5 core data files resolve to ruah_mod.dat!")

    # ================================================================
    # 3. Verify graphic.bin, EPAs, ANMs, and OGGs in ruah_mod.dat & ruah_voice.dat
    # ================================================================
    print("\n=== [3/6] Verifying All New Graphics (EPA/ANM/graphic.bin) & Audio (OGG) ===")
    gb_raw = read_vfs("graphic.bin")
    gb_cnt = struct.unpack_from("<I", gb_raw, 12)[0]
    assert len(gb_raw) == 16 + gb_cnt * 1092, "graphic.bin size mismatch!"
    gb_map = {}
    for i in range(gb_cnt):
        rec = gb_raw[16 + i * 1092 : 16 + (i + 1) * 1092]
        dn = rec[60:92].split(b"\x00", 1)[0].decode("cp932", "replace")
        ep = rec[92:124].split(b"\x00", 1)[0].decode("cp932", "replace")
        an = rec[124:156].split(b"\x00", 1)[0].decode("cp932", "replace")
        gb_map[dn.upper()] = (ep, an)

    orig_gb_cnt = struct.unpack_from("<I", common.read_pc_archive_file("archive.dat", "graphic.bin"), 12)[0]
    # Check ALL new graphic.bin entries point to existing EPAs & ANMs!
    for i in range(orig_gb_cnt, gb_cnt):
        rec = gb_raw[16 + i * 1092 : 16 + (i + 1) * 1092]
        dn = rec[60:92].split(b"\x00", 1)[0].decode("cp932", "replace")
        ep = rec[92:124].split(b"\x00", 1)[0].decode("cp932", "replace")
        an = rec[124:156].split(b"\x00", 1)[0].decode("cp932", "replace")
        if ep and ep.upper() not in vfs:
            errors.append(f"New graphic.bin entry {dn} missing EPA: {ep}")
        if an and an.upper() not in vfs:
            errors.append(f"New graphic.bin entry {dn} missing ANM: {an}")

    # Decode EVERY EPA and verify EVERY ANM/OGG inside ruah_mod.dat!
    mod_names, mod_pairs, mod_db = common.read_pc_archive_index(os.path.join(mod_dir, "ruah_mod.dat"))
    epa_ok = anm_ok = ogg_ok = 0
    with open(os.path.join(mod_dir, "ruah_mod.dat"), "rb") as f:
        for nm, (o, s) in zip(mod_names, mod_pairs):
            f.seek(mod_db + o)
            data = f.read(s)
            nl = nm.lower()
            if nl.endswith(".epa"):
                im = common.decode_epa_image(data)
                assert im.width > 0 and im.height > 0
                epa_ok += 1
            elif nl.endswith(".anm"):
                assert data[:4] == b"ANM1", f"Bad ANM1 header in {nm}"
                anm_ok += 1
            elif nl.endswith(".ogg"):
                assert data[:4] == b"OggS", f"Bad OggS header in {nm}"
                # Vorbis identification header starts at byte 28 ("\x01vorbis"), sample rate uint32 at +12 = byte 40
                sr = struct.unpack_from("<I", data, 40)[0]
                if sr != 44100:
                    errors.append(f"Wrong sample rate {sr} Hz (expected 44100) in ruah_mod.dat/{nm}")
                ogg_ok += 1

    # Verify EVERY OGG in ruah_voice.dat starts with OggS and is 44100 Hz!
    voi_names, voi_pairs, voi_db = common.read_pc_archive_index(os.path.join(mod_dir, "ruah_voice.dat"))
    voi_ok = 0
    with open(os.path.join(mod_dir, "ruah_voice.dat"), "rb") as f:
        for nm, (o, s) in zip(voi_names, voi_pairs):
            f.seek(voi_db + o)
            hdr44 = f.read(44)
            if hdr44[:4] != b"OggS":
                errors.append(f"Bad OggS header in ruah_voice.dat/{nm}")
            elif struct.unpack_from("<I", hdr44, 40)[0] != 44100:
                errors.append(f"Wrong sample rate in ruah_voice.dat/{nm}: {struct.unpack_from('<I', hdr44, 40)[0]}")
            else:
                voi_ok += 1

    print(f"  PASS: Decoded {epa_ok} EPAs, verified {anm_ok} ANMs, {ogg_ok} BGM/SE OGGs, {voi_ok} Voice OGGs, {gb_cnt - orig_gb_cnt} new graphic.bin entries!")

    # ================================================================
    # 4. Full scenario.dat Bytecode & 100% Asset Resolution Audit
    # ================================================================
    print("\n=== [4/6] Auditing scenario.dat Bytecode, Textdata, & 100% Asset Resolution ===")
    sf = read_vfs("scenario.dat")
    tf = common.crypt_textdata(read_vfs("textdata.bin"))
    fn_raw = read_vfs("filename.dat")
    fn_cnt = struct.unpack_from("<I", fn_raw, 12)[0]
    fn_list = [fn_raw[16 + i * 32 : 16 + (i + 1) * 32].split(b"\x00", 1)[0].decode("cp932", "replace") for i in range(fn_cnt)]

    # Parse BGM.ini sections (we verify .ogg targets for all referenced & newly added BGMs below!)
    bgm_ini = read_vfs("BGM.ini").decode("cp932", "replace")
    bgm_sections = {}
    cur_sec = None
    for line in bgm_ini.splitlines():
        ls = line.strip()
        if ls.startswith("[") and ls.endswith("]"):
            cur_sec = ls[1:-1].upper()
            bgm_sections[cur_sec] = []
        elif cur_sec and ("ogg_intro_src" in ls or "ogg_loop_src" in ls):
            val = ls.split("=", 1)[1].strip()
            bgm_sections[cur_sec].append(val)

    orig_sf_len = len(common.read_pc_archive_file("archive.dat", "scenario.dat"))
    # Simulate P_ARK201.exe 0x43fda1 linear scan from offset 0x20 ALL the way to EOF!
    # Any nw==0 anywhere in scenario.dat would halt save/load lookup prematurely!
    scan_pos = 32
    seen_msg_ids = {}
    while scan_pos + 4 <= len(sf):
        w = struct.unpack_from("<I", sf, scan_pos)[0]
        nw = w & 0xFF
        if nw == 0:
            errors.append(f"0x43fda1 linear scan halted prematurely at 0x{scan_pos:x} (word=0x{w:08x})!")
            break
        if w == 0x80000307:
            mid = struct.unpack_from("<I", sf, scan_pos + 16)[0]
            if scan_pos >= orig_sf_len and mid in seen_msg_ids:
                errors.append(f"Duplicate ported msg_id {mid} at 0x{scan_pos:x} (prev 0x{seen_msg_ids[mid]:x})")
            seen_msg_ids.setdefault(mid, scan_pos)
        elif w == 0x01030d02:
            mid = struct.unpack_from("<I", sf, scan_pos + 4)[0]
            if scan_pos >= orig_sf_len and mid in seen_msg_ids:
                errors.append(f"Duplicate ported save_pt msg_id {mid} at 0x{scan_pos:x}")
            seen_msg_ids.setdefault(mid, scan_pos)
        scan_pos += nw * 4
    if scan_pos != len(sf):
        errors.append(f"0x43fda1 linear scan ended at 0x{scan_pos:x} != len(sf) 0x{len(sf):x}")
    for test_mid in (67567, 93588, 93888, 95173):
        if test_mid not in seen_msg_ids or seen_msg_ids[test_mid] < orig_sf_len:
            errors.append(f"Test save msg_id {test_mid} unreachable by 0x43fda1!")

    # Index all valid instruction boundaries in ported region [orig_sf_len .. len(sf)]
    valid_ips = set()
    ported_ins = []
    pos = orig_sf_len
    while pos + 4 <= len(sf):
        valid_ips.add(pos)
        w = struct.unpack_from("<I", sf, pos)[0]
        nw = w & 0xFF
        assert nw > 0 and pos + nw * 4 <= len(sf), f"Bad ported instruction at 0x{pos:x}: 0x{w:08x}"
        args = struct.unpack_from(f"<{nw - 1}I", sf, pos + 4) if nw > 1 else ()
        ported_ins.append((pos, w, args))
        pos += nw * 4

    # Check all 15 patched Master Dispatcher hooks + 10 Omake hooks land on valid instruction boundaries!
    hook_offsets = [0x1f58, 0x1fdc, 0x2060, 0x20dc, 0x42fe0c, 0x23a8, 0x242c, 0x24b0,
                    0x2698, 0x286c, 0x2a38, 0x2c14, 0x2de8, 0x2fb4, 0x314c,
                    0x40c368, 0x40d574, 0x40f28c, 0x42f358, 0x42f8e4,
                    0x413fac, 0x415760, 0x415bdc, 0x417bf0, 0x42e5a4]
    for ho in hook_offsets:
        tgt = struct.unpack_from("<I", sf, ho)[0]
        if tgt not in valid_ips:
            errors.append(f"Hook at 0x{ho:x} target 0x{tgt:x} not a valid ported IP!")

    # Verify Expanded Omake base plates (winning from ruah_mod.dat) & 22 new Omake graphic.bin records
    for omake_base in ("sys_oc_base04.EPA", "sys_oc_base07.EPA", "sys_oc_base08.EPA", "sys_oc_base09c.EPA",
                       "sys_ov_base01.EPA", "sys_m_base4.EPA", "sys_m_files05.EPA"):
        winner = os.path.basename(vfs[omake_base.upper()][0])
        if winner != "ruah_mod.dat":
            errors.append(f"Omake base {omake_base} did not resolve to ruah_mod.dat (got {winner})")
    im_mf05 = common.decode_epa_image(read_vfs("sys_m_files05.EPA"))
    if im_mf05.size != (512, 768):
        errors.append(f"sys_m_files05.EPA size {im_mf05.size} != (512, 768)")

    # Verify non-overlapping screen (x, y) coordinates at graphic.bin offset 1028..1036 for Omake buttons
    gb_xy = {}
    for i in range(gb_cnt):
        rec = gb_raw[16 + i * 1092 : 16 + (i + 1) * 1092]
        dn = rec[60:92].split(b"\x00", 1)[0].decode("cp932", "replace").upper()
        gb_xy[dn] = struct.unpack_from("<ii", rec, 1028)
    for s in range(14, 20):
        if gb_xy.get(f"SYS_OM_P4M{s:02d}") != (455, 237 + (s - 14) * 44):
            errors.append(f"Bad graphic.bin (x, y) for SYS_OM_P4M{s:02d}: {gb_xy.get(f'SYS_OM_P4M{s:02d}')}")
    if gb_xy.get("SYS_OV_B20") != (579, 402):
        errors.append(f"Bad graphic.bin (x, y) for SYS_OV_B20: {gb_xy.get('SYS_OV_B20')}")
    if len({gb_xy.get(f"SYS_OC_THUMB08{s:02d}") for s in range(7, 18)}) != 11:
        errors.append("Duplicate (x, y) coordinates among SYS_OC_THUMB0807..0817 in graphic.bin!")

    # Verify every single ported instruction's IP, TF, and NFD references!
    gfx_ops = {0x01010009, 0x04000004, 0x80010102, 0x80010204, 0x80010604, 0x80020002, 0x80020302}
    bgm_ops = {0x05000003, 0x05000504}
    se_ops  = {0x05010004, 0x05020003}
    mov_ops = {0x05030002}
    voi_ops = {0x80000307}

    checked_gfx = set()
    checked_bgm = set()
    checked_se  = set()
    checked_voi = set()
    checked_mov = set()

    for ip, w, args in ported_ins:
        if w == 0x00100d02:
            errors.append(f"Unpatched PS2 opcode 0x00100d02 at 0x{ip:x}")
        if w in common.IP_SLOTS:
            for k in common.IP_SLOTS[w]:
                tgt = args[k]
                if tgt >= orig_sf_len and tgt not in valid_ips:
                    errors.append(f"Bad IP target 0x{tgt:x} at 0x{ip:x}")
        if w in common.TF_SLOTS:
            for k in common.TF_SLOTS[w]:
                toff = args[k]
                if toff != 0 and toff >= len(tf):
                    errors.append(f"Out-of-bounds textdata offset 0x{toff:x} at 0x{ip:x}")
        if w in common.NFD_SLOTS:
            for k in common.NFD_SLOTS[w]:
                a = args[k]
                if a == 0:
                    continue
                if a > len(fn_list):
                    errors.append(f"Out-of-bounds filename.dat id {a} at 0x{ip:x}")
                    continue
                nm = fn_list[a - 1]
                u = nm.upper()
                is_choice_audio = (w == 0x01010009 and k in (5, 6, 7))
                if w == 0x04000004:
                    # Polymorphic overlay/voice opcode: resolves to graphic.bin, .epa, or .ogg
                    if u not in checked_gfx:
                        checked_gfx.add(u)
                        if u in gb_map:
                            ep, _ = gb_map[u]
                            if ep and ep.upper() not in vfs:
                                errors.append(f"Missing EPA {ep} for gfx {nm}")
                        elif u not in vfs and (u + ".EPA") not in vfs and (u + ".OGG") not in vfs:
                            errors.append(f"Missing 0x04000004 asset {nm} (neither graphic nor audio)")
                elif w in gfx_ops and not is_choice_audio:
                    if u not in checked_gfx:
                        checked_gfx.add(u)
                        if u in gb_map:
                            ep, _ = gb_map[u]
                            if ep and ep.upper() not in vfs:
                                errors.append(f"Missing EPA {ep} for gfx {nm}")
                        elif u not in vfs and (u + ".EPA") not in vfs:
                            errors.append(f"Missing graphic {nm} (neither in graphic.bin nor VFS)")
                elif is_choice_audio:
                    if u not in checked_se:
                        checked_se.add(u)
                        if (u + ".OGG") not in vfs and u not in vfs:
                            errors.append(f"Missing choice audio {nm}.ogg in VFS")
                elif w in bgm_ops:
                    if u not in checked_bgm:
                        checked_bgm.add(u)
                        if u not in bgm_sections:
                            errors.append(f"Missing BGM [{nm}] in BGM.ini")
                        else:
                            for ogg_fn in bgm_sections[u]:
                                if ogg_fn.upper() not in vfs:
                                    errors.append(f"Referenced BGM [{nm}] points to missing OGG: {ogg_fn}")
                elif w in se_ops:
                    if u not in checked_se:
                        checked_se.add(u)
                        if (u + ".OGG") not in vfs and u not in vfs:
                            errors.append(f"Missing SE {nm}.ogg in VFS")
                elif w in voi_ops:
                    if u not in checked_voi:
                        checked_voi.add(u)
                        if (u + ".OGG") not in vfs and u not in vfs:
                            errors.append(f"Missing Voice {nm}.ogg in VFS")
                elif w in mov_ops:
                    if u not in checked_mov:
                        checked_mov.add(u)
                        mp1 = os.path.join(mod_dir, "exp", nm)
                        mp2 = os.path.join(pc_dir, "exp", nm)
                        if not os.path.exists(mp1) and not os.path.exists(mp2):
                            errors.append(f"Missing movie exp/{nm}")

    print(f"  Audited {len(ported_ins):,} ported instructions + 15 Master Dispatcher hooks:")
    print(f"    Resolved {len(checked_gfx)} unique graphics, {len(checked_bgm)} BGMs, {len(checked_se)} SEs, {len(checked_voi)} Voices, {len(checked_mov)} Movies")

    # ================================================================
    # 5. Verify POP22.DAT Movie Format via ffprobe
    # ================================================================
    print("\n=== [5/6] Verifying exp/POP22.DAT Video/Audio Codecs ===")
    pop22 = os.path.join(mod_dir, "exp", "POP22.DAT")
    r = subprocess.run(["ffprobe", "-hide_banner", pop22], capture_output=True, text=True)
    probe = r.stderr
    assert "mpeg1video" in probe and "800x600" in probe, f"POP22.DAT video not 800x600 mpeg1video:\n{probe}"
    assert "mp2" in probe and "44100 Hz" in probe, f"POP22.DAT audio not 44100Hz mp2:\n{probe}"
    print("  PASS: exp/POP22.DAT verified as 800x600 mpeg1video + 44100Hz stereo mp2 (exact PC format)!")

    # ================================================================
    # 6. Verify battle1.dat (PRSM), Playable Ally Ruah (ch = 9), & All 14 Ruah Battles
    # ================================================================
    print("\n=== [6/7] Verifying battle1.dat (PRSM), Playable Ally Ruah (ch = 9), & All 14 Battles ===")
    dec_tbl, _ = common.load_prsm_tables()
    b0_idx = open_prsm_index(os.path.join(pc_dir, "battle.dat"), dec_tbl)
    b1_path = os.path.join(mod_dir, "battle1.dat")
    b1_idx = open_prsm_index(b1_path, dec_tbl)
    battle_vfs = dict(b0_idx)
    battle_vfs.update(b1_idx)

    ally_ruah_fields = 0
    b_rua_oggs = 0
    # Check every file in battle1.dat decrypts cleanly and has valid references!
    for k, ent in b1_idx.items():
        data = read_prsm_member(b1_path, ent, dec_tbl)
        if k.endswith(".ogg"):
            if data[:4] != b"OggS":
                errors.append(f"Bad OggS header in battle1.dat/{ent[0]}")
            else:
                sr = struct.unpack_from("<I", data, 40)[0]
                if sr != 44100:
                    errors.append(f"Wrong sample rate {sr} Hz in battle1.dat/{ent[0]}")
                elif "/b_rua_" in k:
                    b_rua_oggs += 1
        elif k.endswith(".txt"):
            txt = data.decode("cp932", "replace")
            if re.search(r"^\s*character\s*=\s*9\b", txt, re.M | re.I):
                ally_ruah_fields += 1
            # Check all .tga paths referenced exist in battle_vfs!
            for m in re.finditer(r'"(data/[^"]+\.tga)"', txt, re.I):
                tp = m.group(1).lower().replace("\\", "/")
                if tp not in battle_vfs:
                    errors.append(f"Missing battle TGA {tp} referenced in {ent[0]}")
            # Check all object = "..." 3D models referenced exist in battle_vfs and end in .dmo!
            for m in re.finditer(r'^\s*object\s*=\s*"(data/[^"]+)"', txt, re.M | re.I):
                dp = m.group(1).lower().replace("\\", "/")
                if not dp.endswith(".dmo"):
                    errors.append(f"object path missing .dmo suffix: {dp} in {ent[0]}")
                elif dp not in battle_vfs:
                    errors.append(f"Missing battle DMO {dp} referenced in {ent[0]}")
            # For map_*.txt: validate every link connects two distinct defined areas and every battle field exists!
            if "/map_" in k:
                defined_areas = {
                    (int(m.group(1)), int(m.group(2)))
                    for m in re.finditer(r"^\s*area\s+(\d+)\s*,\s*(\d+)", txt, re.M | re.I)
                }
                for m in re.finditer(r"^\s*link\s+(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", txt, re.M | re.I):
                    a1 = (int(m.group(1)), int(m.group(2)))
                    a2 = (int(m.group(3)), int(m.group(4)))
                    if a1 == a2 or a1 not in defined_areas or a2 not in defined_areas:
                        errors.append(f"Invalid map link {a1}->{a2} in {ent[0]} (areas={sorted(defined_areas)})")
                for m in re.finditer(r"^\s*battle\s+(\d+)\s*,\s*(\d+)", txt, re.M | re.I):
                    mbid, mstg = int(m.group(1)), int(m.group(2))
                    fp = f"data/mapscript/map{mbid % 100:02d}/field_{mbid:04d}_{mstg:03d}.txt"
                    if fp not in battle_vfs:
                        errors.append(f"Missing field {fp} referenced by {ent[0]}")
            # For field_*.txt with #character.txt: verify EVERY character/chdef source is defined inside #character.txt!
            if "/field_" in k and "#character.txt" in txt.lower():
                hdr_part, char_part = re.split(r"#character\.txt", txt, maxsplit=1, flags=re.I)
                defined_units = set()
                for blk in re.split(r"(?=^\[)", char_part, flags=re.M):
                    m1 = re.search(r"^\s*ch\s*=\s*(\d+)", blk, re.M | re.I)
                    m2 = re.search(r"^\s*number\s*=\s*(\d+)", blk, re.M | re.I)
                    if m1 and m2:
                        defined_units.add((int(m1.group(1)), int(m2.group(1))))
                chdef_map = {}
                for m in re.finditer(r"^\s*chdef\s*=\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", hdr_part, re.M | re.I):
                    chdef_map[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))
                for m in re.finditer(r"^\s*character\s*=\s*(\d+)\s*,\s*(\d+)", hdr_part, re.M | re.I):
                    c_id, c_num = int(m.group(1)), int(m.group(2))
                    lookup = chdef_map.get(c_id, (c_id, c_num))
                    if lookup not in defined_units:
                        errors.append(f"Unit {lookup} (for ch={c_id}) missing in #character.txt of {ent[0]}!")

    if ally_ruah_fields == 0:
        errors.append("No playable ally Ruah (character = 9) found in any battle1.dat field file!")
    if b_rua_oggs != 104:
        errors.append(f"Expected 104 Ruah battle voices (B_RUA_0000..0103.ogg) in battle1.dat, found {b_rua_oggs}")

    # Verify all required Playable Ally Ruah UI, 3D model, ch_sheet, common.se, random.se assets
    req_ruah_battle_assets = [
        "ch_sheet.txt",
        "animelist.txt",
        "data/se/common.se",
        "data/se/random.se",
        "data/char/character/ruah/ph2chr09.dmo",
        "data/char/character/ruah/ph2chr09.def",
        "data/char/character/ruah/ph2chr09.cmn",
        "data/char/character/ruah/ph2chr09.tga",
        "data/char/character/ruah/ph2chr09_face.tga",
        "data/char/character/ruah/ph2chr09_hair.tga",
        "data/manabe/キャラステータス関連/キャラクター/bt_v09.tga",
        "data/manabe/キャラステータス関連/キャラステータス/bt_a09.tga",
        "data/manabe/戦闘終了画像/cut_09.tga",
        "data/manabe/戦闘終了画像/bte_09a.tga",
        "data/manabe/戦闘終了画像/bte_09b.tga",
        "data/campaign/ステータス/キャラ文字/st_e09.tga",
        "data/campaign/キャラクターシート/キャラクター/ca_b09.tga",
        "data/campaign/キャラクターシート/説明/ca_c09.tga",
        "data/bg/BATTLE_LOADING/BWP_RUAH01.tga",
        "data/bg/CAMP_LOADING/BATTLE_LOAD_0111b.tga",
        "data/bg/CAMP_LOADING/BATTLE_LOAD_0811.tga",
        "data/bg/CAMP_LOADING/BATTLE_LOAD_0812.tga",
    ]
    for req in req_ruah_battle_assets:
        if req.lower() not in b1_idx:
            errors.append(f"Missing required Playable Ruah asset in battle1.dat: {req}")

    # Ensure official PS2 loading TGAs are 800x600 and fully opaque (min alpha == 255)
    from PIL import Image
    import io
    for loading_tga in (
        "data/bg/BATTLE_LOADING/BWP_RUAH01.tga",
        "data/bg/CAMP_LOADING/BATTLE_LOAD_0111b.tga",
        "data/bg/CAMP_LOADING/BATTLE_LOAD_0811.tga",
        "data/bg/CAMP_LOADING/BATTLE_LOAD_0812.tga",
    ):
        kl = loading_tga.lower()
        if kl in b1_idx:
            raw_tga = read_prsm_member(b1_path, b1_idx[kl], dec_tbl)
            im_tga = Image.open(io.BytesIO(raw_tga)).convert("RGBA")
            a_min, a_max = im_tga.getextrema()[3]
            if im_tga.size != (800, 600) or a_min != 255:
                errors.append(
                    f"Loading TGA {loading_tga} invalid: size={im_tga.size} alpha=({a_min},{a_max})"
                )

    if "ch_sheet.txt" in b1_idx:
        ch_txt = read_prsm_member(b1_path, b1_idx["ch_sheet.txt"], dec_tbl).decode("cp932", "replace")
        if "[ルーア]" not in ch_txt:
            errors.append("[ルーア] missing from battle1.dat/ch_sheet.txt")

    if "animelist.txt" in b1_idx:
        al_txt = read_prsm_member(b1_path, b1_idx["animelist.txt"], dec_tbl).decode("cp932", "replace")
        for aid, anm in [("20000", "LUAH_AK_01"), ("20001", "LUAH_SP_01"), ("20002", "LUAH_SP_02")]:
            if aid not in al_txt or anm not in al_txt:
                errors.append(f"{aid} {anm} missing from battle1.dat/animelist.txt")

    if "data/char/character/ruah/ph2chr09.dmo" in b1_idx:
        ruah_dmo_b = read_prsm_member(b1_path, b1_idx["data/char/character/ruah/ph2chr09.dmo"], dec_tbl)
        for marker in (b"ph2chr09_Layer1", b"ph2chr09.tga", b"ph2chr09_face.tga", b"ph2chr09_hair.tga"):
            if marker not in ruah_dmo_b:
                errors.append(f"Official PS2 Ruah marker {marker!r} missing in ph2chr09.dmo")

    # Check Prism #225 & Ruah ally/boss skills 5000..5008 in prism.txt
    ptxt = read_prsm_member(b1_path, b1_idx["prism.txt"], dec_tbl).decode("cp932", "replace")
    for pr in (225, 5000, 5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008):
        if f"PR = {pr}" not in ptxt:
            errors.append(f"PR = {pr} missing from battle1.dat/prism.txt")

    # Verify all 14 Ruah battle IDs have at least one field file
    for bid in (62, 808, 809, 810, 1810, 811, 1811, 2811, 3811, 812, 1812, 813, 1813, 2813):
        m = bid % 100
        prefix = f"data/mapscript/map{m:02d}/field_{bid:04d}_"
        hits = [k for k in b1_idx if k.startswith(prefix)]
        if not hits:
            errors.append(f"No field files for Ruah battle {bid}!")

    print(
        f"  Verified all {len(b1_idx)} files in battle1.dat "
        f"(ally ch=9 in {ally_ruah_fields} battle stages, {b_rua_oggs} 44.1kHz Ruah battle voices, "
        f"ph2chr09 3D model, 6 UI TGAs, ch_sheet, Prism #225 + 5000..5008)!"
    )

    # ================================================================
    # 7. Verify P_ARK201_Ruah.exe (UPX Hook + .ruah Section + Simulated Boot Patch)
    # ================================================================
    print("\n=== [7/7] Verifying P_ARK201_Ruah.exe Binary Patch ===")
    exe_ruah = os.path.join(mod_dir, "P_ARK201_Ruah.exe")
    if not os.path.exists(exe_ruah):
        errors.append("P_ARK201_Ruah.exe missing from mod directory!")
    else:
        applied = patch_exe.simulate_and_verify(exe_ruah, verbose=False)
        if applied < 62:
            errors.append(f"Expected >= 62 verified patches in P_ARK201_Ruah.exe, got {applied}")
        print(f"  PASS: P_ARK201_Ruah.exe verified ({os.path.getsize(exe_ruah):,} bytes, {applied} patches cleanly simulated)!")

    # ================================================================
    # Final Verdict
    # ================================================================
    print("\n============================================================")
    if errors:
        print(f"VERIFICATION FAILED WITH {len(errors)} ERRORS:")
        for e in errors[:30]:
            print("  ERROR:", e)
        sys.exit(1)
    else:
        print("ALL 7 VERIFICATION SUITES PASSED WITH ZERO ERRORS!")
        print("============================================================")


if __name__ == "__main__":
    main()
