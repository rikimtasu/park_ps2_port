import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import omake_assets

STAGED_DIR = os.path.join(common.WORK_DIR, "staged")
MANIFEST_PATH = os.path.join(STAGED_DIR, "needed_assets.json")

# Map PS2 PA_MOV.DAT (lo, mid) -> PC exp/POP*.DAT filename
PS2_MOVIE_MAP = {
    (0, 0): "POP08.DAT",
    (1, 0): "POP09.DAT",
    (2, 0): "POP10.DAT",
    (3, 0): "POP11.DAT",
    (4, 0): "POP12.DAT",
    (5, 0): "POP13.DAT",
    (6, 0): "POP14.DAT",
    (7, 0): "POP15.DAT",
    (8, 0): "POP16.DAT",
    (9, 0): "POP17.DAT",
    (10, 0): "POP18.DAT",
    (11, 0): "POP19.DAT",
    (12, 0): "POP20.DAT",
    (13, 0): "POP23.DAT",   # Awake OP1; keep all original PC movie files intact
    (14, 0): "POP24.DAT",   # Awake OP2
    (15, 0): "POP21.DAT",   # PS2 ED1 (extracted to exp/POP21.DAT)
    (16, 0): "POP22.DAT",   # PS2 ED2 (Ruah ending credits! extracted to exp/POP22.DAT)
    (17, 0): "POP00.DAT",
    (17, 1): "POP01.DAT",
    (17, 2): "POP02.DAT",
    (17, 3): "POP03.DAT",
    (17, 4): "POP04.DAT",
    (17, 5): "POP05.DAT",
    (17, 6): "POP06.DAT",
    (17, 7): "POP00.DAT",
}


def load_ps2_scr(iso: common.IsoReader, ci: int):
    chunk = iso.read_flk_entry("PA_SCR.DAT", ci)
    _, _, _, _, _, _, c2, _ = struct.unpack_from("<4s7I", chunk, 0)
    sub = [struct.unpack_from("<II", chunk, 32 + i * 8) for i in range(c2)]
    sf = chunk[sub[0][0] : sub[0][0] + sub[0][1]]
    tf = chunk[sub[1][0] : sub[1][0] + sub[1][1]]
    nfd = chunk[sub[2][0] : sub[2][0] + sub[2][1]]
    ncnt = struct.unpack_from("<I", nfd, 4)[0]
    nvals = struct.unpack_from(f"<{ncnt}I", nfd, 8)
    return sf, tf, nvals


def parse_sf_instructions(sf: bytes):
    """Parse all instructions from a PJADV_SF0001 buffer -> dict[ip] = (op, args, next_ip)."""
    ins = {}
    pos = 32
    n = len(sf)
    while pos + 4 <= n:
        w = struct.unpack_from("<I", sf, pos)[0]
        nw = w & 0xFF
        if nw == 0 or pos + nw * 4 > n:
            raise RuntimeError(f"Bad instruction at 0x{pos:x}: 0x{w:08x}")
        args = list(struct.unpack_from(f"<{nw - 1}I", sf, pos + 4)) if nw > 1 else []
        nxt = pos + nw * 4
        ins[pos] = (w, args, nxt)
        pos = nxt
    return ins


def trace_reachable(ins: dict, entry_ips: list[int]) -> list[int]:
    """BFS all reachable instruction IPs starting from entry_ips, sorted by IP."""
    visited = set()
    stack = list(entry_ips)
    while stack:
        ip = stack.pop()
        while ip in ins and ip not in visited:
            visited.add(ip)
            w, args, nxt = ins[ip]
            if w in common.IP_SLOTS:
                for k in common.IP_SLOTS[w]:
                    tgt = args[k]
                    if tgt not in visited:
                        stack.append(tgt)
            # Stop sequential fall-through on unconditional JMP or RET
            if w in (0x01000202, 0x01000401):
                break
            ip = nxt
    return sorted(visited)


def load_pxg_sub_names(iso: common.IsoReader, cg_list: list[str]) -> dict[tuple[int, int], str]:
    """For every .pxg entry in PA_CG.DAT, read its tbl2 sub-entry names: (cg_idx, sub_idx) -> PJGraphicDef name."""
    res = {}
    for lo, nm in enumerate(cg_list):
        if not nm.lower().endswith(".pxg"):
            continue
        raw = iso.read_flk_entry("PA_CG.DAT", lo)
        if raw[:4] != b"PXG\x00":
            continue
        _, n_sub, _, _, _, tbl2_off = struct.unpack_from("<4sIIIII", raw, 0)
        for mid in range(n_sub):
            ro = tbl2_off + mid * 128
            s1 = raw[ro + 32:ro + 64].split(b"\x00", 1)[0].decode("cp932", "replace")
            res[(lo, mid)] = s1
    return res


def read_tf_raw_bytes(tf: bytes, off: int) -> bytes:
    end = tf.find(b"\x00", off)
    if end == -1:
        end = len(tf)
    return tf[off:end]


def main():
    os.makedirs(STAGED_DIR, exist_ok=True)
    iso = common.IsoReader()

    # Load PS2 asset lists
    cg_list = [l.split("\t")[-1].strip() for l in iso.read_flk_names("PA_CG.DAT")]
    bgm_list = iso.read_flk_names("PA_BGM.DAT")
    voi_list = iso.read_flk_names("PA_VOI.DAT")
    print(f"PS2 lists: CG={len(cg_list)}, BGM={len(bgm_list)}, VOI={len(voi_list)}")

    pxg_names = load_pxg_sub_names(iso, cg_list)
    print(f"Indexed {len(pxg_names)} PXG sub-sprite names across PA_CG.DAT")

    # Load PC original tables
    pc_sf_orig = bytearray(common.read_pc_archive_file("archive.dat", "scenario.dat"))
    pc_tf_orig = bytearray(common.crypt_textdata(common.read_pc_archive_file("archive.dat", "textdata.bin")))
    pc_fn_raw = common.read_pc_archive_file("archive.dat", "filename.dat")
    pc_fn_cnt = struct.unpack_from("<I", pc_fn_raw, 12)[0]
    pc_fn_list = [
        pc_fn_raw[16 + i * 32:16 + (i + 1) * 32].split(b"\x00", 1)[0].decode("cp932", "replace")
        for i in range(pc_fn_cnt)
    ]
    pc_fn_upper_to_idx = {}
    for i, nm in enumerate(pc_fn_list):
        u = nm.upper()
        if u not in pc_fn_upper_to_idx:
            pc_fn_upper_to_idx[u] = i
        # Also map # -> _ normalized voice lookup!
        un = u.replace("#", "_")
        if un not in pc_fn_upper_to_idx:
            pc_fn_upper_to_idx[un] = i

    # Load PC existing asset sets to know what's genuinely NEW!
    pc_gb = common.read_pc_archive_file("archive.dat", "graphic.bin")
    pc_gb_cnt = struct.unpack_from("<I", pc_gb, 12)[0]
    pc_gb_set = {
        pc_gb[16 + i * 1092 + 60:16 + i * 1092 + 92].split(b"\x00", 1)[0].decode("cp932", "replace").upper()
        for i in range(pc_gb_cnt)
    }
    pc_epa_stems = set()
    pc_epa_names = set()
    for arch in ("archive.dat", "archive1.dat", "archive2.dat"):
        names, _, _ = common.read_pc_archive_index(os.path.join(common.PC_DIR, arch))
        for n in names:
            if n.lower().endswith(".epa"):
                pc_epa_stems.add(os.path.splitext(n)[0].upper())
                pc_epa_names.add(n.upper())
    pc_existing_gfx = pc_gb_set | pc_epa_stems | pc_epa_names

    pag_iname_cache = {}
    def get_pag_internal_name(lo: int, fallback: str) -> str:
        if lo not in pag_iname_cache:
            raw = iso.read_flk_entry("PA_CG.DAT", lo)
            dec = common.decompress_zzz(raw)
            if len(dec) >= 0x84 and dec[:4] == b"PAG\x00":
                iname = dec[0x64:0x84].split(b"\x00", 1)[0].decode("cp932", "replace")
                pag_iname_cache[lo] = iname if iname else fallback
            else:
                pag_iname_cache[lo] = fallback
        return pag_iname_cache[lo]

    pc_bgm_stems = set()
    bgm_ini_raw = common.read_pc_archive_file("archive.dat", "BGM.ini").decode("cp932", "replace")
    for line in bgm_ini_raw.splitlines():
        ls = line.strip()
        if ls.startswith("[") and ls.endswith("]"):
            pc_bgm_stems.add(ls[1:-1].upper())

    pc_voi_files = {}
    for arch in ("voice.dat", "voice1.dat", "voice2.dat"):
        names, _, _ = common.read_pc_archive_index(os.path.join(common.PC_DIR, arch))
        for n in names:
            stem = os.path.splitext(n)[0]
            pc_voi_files[stem.upper()] = stem
            pc_voi_files[stem.upper().replace("#", "_")] = stem

    pc_se_files = {}
    names, _, _ = common.read_pc_archive_index(os.path.join(common.PC_DIR, "se.dat"))
    for n in names:
        stem = os.path.splitext(n)[0]
        pc_se_files[stem.upper()] = stem

    # Asset manifest to export for port_graphics.py & port_audio.py
    needed_pags = {}   # cg_idx -> name
    needed_pxgs = {}   # (cg_idx, mid) -> name
    needed_vois = {}   # voi_idx -> stem
    needed_bgms = {}   # bgm_idx -> stem
    needed_ses = {}    # se_idx -> stem (e.g. PS2_SE_0123)
    needed_movs = {}   # mov_idx -> POPxx.DAT

    def ensure_fn_id(name: str) -> int:
        """Return 1-based PC filename.dat index, appending if new."""
        u = name.upper()
        if u in pc_fn_upper_to_idx:
            return pc_fn_upper_to_idx[u] + 1
        idx = len(pc_fn_list)
        if len(name.encode("cp932")) > 31:
            raise ValueError(f"filename.dat name > 31B: {name!r}")
        pc_fn_list.append(name)
        pc_fn_upper_to_idx[u] = idx
        return idx + 1

    def resolve_nfd_to_pc_fn(nv: int, op: int) -> int:
        hi = nv >> 24
        mid = (nv >> 16) & 0xFF
        lo = nv & 0xFFFF
        if hi == 0x40:
            nm = cg_list[lo]
            if nm.lower().endswith(".pxg"):
                sub_idx = mid - 1
                sub_name = pxg_names[(lo, sub_idx)]
                if sub_name.upper() not in pc_existing_gfx:
                    needed_pxgs[(lo, sub_idx)] = sub_name
                return ensure_fn_id(sub_name)
            else:
                if not nm:
                    return ensure_fn_id("BLACK")
                if nm.upper() not in pc_existing_gfx:
                    iname = get_pag_internal_name(lo, nm)
                    if iname.upper() in pc_existing_gfx:
                        return ensure_fn_id(iname)
                    needed_pags[lo] = iname
                    return ensure_fn_id(iname)
                return ensure_fn_id(nm)
        elif hi == 0x50:
            # Always extract exact PS2 SE as PS2_SE_XXXX (100% authentic, zero mismatch!)
            # Note: if op is 0x05000003 / 0x05000504 (PLAY_BGM using ambient SE!), we register it in BGM.ini too!
            stem = f"PS2_SE_{lo:04d}"
            needed_ses[lo] = stem
            if op in (0x05000003, 0x05000504):
                needed_bgms[f"SE_{lo}"] = stem
            return ensure_fn_id(stem)
        elif hi == 0x60:
            stem = os.path.splitext(bgm_list[lo])[0]
            if stem.upper() not in pc_bgm_stems:
                needed_bgms[lo] = stem
            return ensure_fn_id(stem)
        elif hi == 0x70:
            pop_name = PS2_MOVIE_MAP[(lo, mid)]
            if lo in (13, 14, 15, 16):
                needed_movs[lo] = pop_name
            return ensure_fn_id(pop_name)
        elif hi == 0x80:
            stem = os.path.splitext(voi_list[lo])[0]
            u = stem.upper()
            if u in pc_voi_files:
                return ensure_fn_id(pc_voi_files[u])
            needed_vois[lo] = stem
            return ensure_fn_id(stem)
        else:
            raise RuntimeError(f"Unknown NFD value 0x{nv:08x} for op 0x{op:08x}")

    # Textdata dedup & append helper
    tf_str_map = {}  # raw cp932 bytes -> offset in pc_tf_orig
    tp = 16
    while tp < len(pc_tf_orig):
        z = pc_tf_orig.find(b"\x00", tp)
        if z == -1:
            break
        raw_s = bytes(pc_tf_orig[tp:z])
        if raw_s not in tf_str_map:
            tf_str_map[raw_s] = tp
        tp = z + 2
    tf_count = struct.unpack_from("<I", pc_tf_orig, 12)[0]

    def append_tf_str(raw_s: bytes) -> int:
        nonlocal tf_count
        if raw_s in tf_str_map:
            return tf_str_map[raw_s]
        off = len(pc_tf_orig)
        pc_tf_orig.extend(raw_s + b"\x00\x00")
        tf_str_map[raw_s] = off
        tf_count += 1
        return off

    # Define ALL PS2 script units to compile & append into pc_sf_orig!
    # Format: name -> (scr_idx, [entry_ips_to_keep])
    UNITS = [
        ("ch2",    2,  [0x170, 0x2f2e0]),
        ("ch3",    3,  [0x114]),
        ("ch4",    4,  [0x110]),
        ("inter",  24, [0x438]),
        ("ch5",    5,  [0x12c]),
        ("ch6",    6,  [0x114]),
        ("ch7",    7,  [0x114]),
        ("ch8",    8,  [0x4a4]),
        ("ruah9",  16, [0x0ec]),
        ("ruah10", 17, [0x4e668, 0x526c8]),
        ("ruah11", 18, [0x46074, 0x4a650]),
        ("ruah12", 19, [0x36168]),
        ("ruah13", 20, [0x4cf0c]),
        ("ruah14", 21, [0x5d9ec]),
        ("ruahEp", 22, [0xf178]),
    ]

    unit_entries = {}  # (unit_name, old_entry_ip) -> new_pc_ip
    total_ported_ins = 0
    next_msg_id = struct.unpack_from("<I", pc_sf_orig, 12)[0] + 1

    for uname, ci, entries in UNITS:
        sf, tf, nvals = load_ps2_scr(iso, ci)
        ins = parse_sf_instructions(sf)
        reach = trace_reachable(ins, entries)

        # Assign contiguous new PC IPs starting at len(pc_sf_orig)
        ip_map = {}
        cur_ip = len(pc_sf_orig)
        for old_ip in reach:
            ip_map[old_ip] = cur_ip
            w, args, nxt = ins[old_ip]
            cur_ip += (w & 0xFF) * 4

        # Emit relocated instructions
        out_chunk = bytearray()
        for old_ip in reach:
            w, args, nxt = ins[old_ip]
            new_args = list(args)

            # Replace PS2-only 0x00100d02 (checkpoint) with 0x01000a02 (wait 0ms)
            if w == 0x00100d02:
                w = 0x01000a02
                new_args = [0]
            else:
                if w in common.IP_SLOTS:
                    for k in common.IP_SLOTS[w]:
                        tgt = new_args[k]
                        assert tgt in ip_map, f"Unmapped target 0x{tgt:x} in {uname} @0x{old_ip:x}"
                        new_args[k] = ip_map[tgt]
                if w in common.TF_SLOTS:
                    for k in common.TF_SLOTS[w]:
                        toff = new_args[k]
                        if toff != 0:
                            raw_s = read_tf_raw_bytes(tf, toff)
                            new_args[k] = append_tf_str(raw_s)
                if w in common.NFD_SLOTS:
                    for k in common.NFD_SLOTS[w]:
                        a = new_args[k]
                        if a == 0:
                            continue
                        nv = nvals[a - 1]
                        new_args[k] = resolve_nfd_to_pc_fn(nv, w)
                # Assign strictly unique msg_id so P_ARK201.exe save/load (0x43fda1) and read-skip work 100%!
                if w == 0x80000307:
                    new_args[3] = next_msg_id
                    next_msg_id += 1
                elif w == 0x01030d02:
                    new_args[0] = next_msg_id
                    next_msg_id += 1

            out_chunk.extend(struct.pack("<I", w))
            for a in new_args:
                out_chunk.extend(struct.pack("<I", a))

        pc_sf_orig.extend(out_chunk)
        for e in entries:
            unit_entries[(uname, e)] = ip_map[e]
        total_ported_ins += len(reach)
        print(f"  Compiled {uname:7s} (SCR[{ci:2d}]): {len(reach):5d} reachable ins ({len(out_chunk):7d} bytes) entries={[hex(ip_map[e]) for e in entries]}")

    # Helper to emit small wrapper stubs at end of pc_sf_orig
    def emit_stub(inst_list: list[tuple[int, list[int]]]) -> int:
        start = len(pc_sf_orig)
        for w, args in inst_list:
            assert (w & 0xFF) == 1 + len(args)
            pc_sf_orig.extend(struct.pack("<I", w))
            for a in args:
                pc_sf_orig.extend(struct.pack("<I", a))
        return start

    # Build wrapper for Ch.2 (calls 0x170 then 0x2f2e0 then RET)
    stub_ch2 = emit_stub([
        (0x01000302, [unit_entries[("ch2", 0x170)]]),
        (0x01000302, [unit_entries[("ch2", 0x2f2e0)]]),
        (0x01000401, []),
    ])

    # Build Ruah route branch stubs for Ch.9..Ch.14 + Epilogue!
    # Pattern for Ch.9..14:
    #   if var[0x10000000] == 8:
    #       CALL ruah_part(s)
    #       if var[0x10000031] == 1: JMP 0x003170 (Game Over / Bad End)
    #   JMP rejoin_ip
    def emit_ruah_branch(call_ips: list[int], rejoin_ip: int, check_gameover: bool = False, mid_check_gameover: bool = False) -> int:
        base = len(pc_sf_orig)
        # We compute exact offsets carefully:
        # 0x00: 0x02000103 [0x30000000, 0x10000000] (12B)
        # 0x0c: 0x02000103 [0x30000001, 8]          (12B)
        # 0x18: 0x02010003 [0x30000000, 0x30000001] (12B)  # ==
        # 0x24: 0x02000103 [0x30000002, 0x30000000] (12B)
        # 0x30: 0x01000703 [0x30000002, rejoin_ip]  (12B)  # JZ rejoin_ip
        ops = [
            (0x02000103, [0x30000000, 0x10000000]),
            (0x02000103, [0x30000001, 8]),
            (0x02010003, [0x30000000, 0x30000001]),
            (0x02000103, [0x30000002, 0x30000000]),
            (0x01000703, [0x30000002, rejoin_ip]),
        ]
        for idx_c, cip in enumerate(call_ips):
            ops.append((0x01000302, [cip]))
            if check_gameover and (mid_check_gameover or idx_c == len(call_ips) - 1):
                # Check if var[0x10000031] == 1 -> JMP 0x003170!
                cur_sz = sum((w & 0xFF) * 4 for w, _ in ops)
                after_go = base + cur_sz + 12 * 5 + 8
                ops.extend([
                    (0x02000103, [0x30000000, 0x10000031]),
                    (0x02000103, [0x30000001, 1]),
                    (0x02010003, [0x30000000, 0x30000001]),
                    (0x02000103, [0x30000002, 0x30000000]),
                    (0x01000703, [0x30000002, after_go]),
                    (0x01000202, [0x003170]),
                ])
        ops.append((0x01000202, [rejoin_ip]))
        return emit_stub(ops)

    stub_ruah9  = emit_ruah_branch([unit_entries[("ruah9", 0x0ec)]], 0x0026ac, check_gameover=False)
    stub_ruah10 = emit_ruah_branch([unit_entries[("ruah10", 0x4e668)], unit_entries[("ruah10", 0x526c8)]], 0x002880, check_gameover=True)
    stub_ruah11 = emit_ruah_branch([unit_entries[("ruah11", 0x46074)], unit_entries[("ruah11", 0x4a650)]], 0x002a4c, check_gameover=True, mid_check_gameover=True)
    stub_ruah12 = emit_ruah_branch([unit_entries[("ruah12", 0x36168)]], 0x002c28, check_gameover=True)
    stub_ruah13 = emit_ruah_branch([unit_entries[("ruah13", 0x4cf0c)]], 0x002dfc, check_gameover=True)
    stub_ruah14 = emit_ruah_branch([unit_entries[("ruah14", 0x5d9ec)]], 0x002fc8, check_gameover=True)

    # Epilogue stub for Ruah: play ED2 (POP22.DAT), call 0xf178 (旅だちの日に), set title ルーア編 クリア,
    # record Ruah's PS2 route clear flag (sys[0x20000123] = 1, sys[0x200000f0] += 1 on first clear), then rejoin 0x003160!
    ruah_clear_tf = append_tf_str("ルーア編　クリア".encode("cp932"))
    pop22_fn = ensure_fn_id("POP22.DAT")
    needed_movs[16] = "POP22.DAT"
    ep_base = len(pc_sf_orig)
    ep_ops = [
        (0x02000103, [0x30000000, 0x10000000]),
        (0x02000103, [0x30000001, 8]),
        (0x02010003, [0x30000000, 0x30000001]),
        (0x02000103, [0x30000002, 0x30000000]),
        (0x01000703, [0x30000002, 0x003160]),
        (0x05030002, [pop22_fn]),                          # Play PS2 Awake ED2 movie!
        (0x01000302, [unit_entries[("ruahEp", 0xf178)]]),  # 旅だちの日に
        (0x01000d02, [ruah_clear_tf]),                     # ルーア編 クリア
        # Mirror PS2 PA_SCR[22] 0x14b8..0x1520: if sys[0x20000123] == 0, increment sys[0x200000f0] and set sys[0x20000123] = 1
        (0x02000103, [0x30000001, 0x20000123]),
        (0x02000103, [0x30000002, 0]),
        (0x02010003, [0x30000001, 0x30000002]),
        (0x02000103, [0x30000003, 0x30000001]),
    ]
    jz_after_inc_off = sum((w & 0xFF) * 4 for w, _ in ep_ops)
    after_inc_ip = ep_base + jz_after_inc_off + 12 + 12 + 8 + 12
    ep_ops.extend([
        (0x01000703, [0x30000003, after_inc_ip]),
        (0x02000103, [0x30000001, 0x200000f0]),
        (0x02000702, [0x30000001]),
        (0x02000103, [0x200000f0, 0x30000001]),
        (0x02000103, [0x30000001, 1]),
        (0x02000103, [0x20000123, 0x30000001]),
        (0x02000103, [0x200000e0, 0x30000001]),
        (0x01000202, [0x003160]),                          # PC clear-save & return to Title
    ])
    assert ep_base + sum((w & 0xFF) * 4 for w, _ in ep_ops[:-4]) == after_inc_ip
    stub_ruahEp = emit_stub(ep_ops)

    # ---- Patch PC Master Chapter Dispatcher (ZERO relocation of existing PC code!) ----
    def patch_u32(off: int, expected: int, new_val: int, desc: str):
        cur = struct.unpack_from("<I", pc_sf_orig, off)[0]
        assert cur == expected, f"Patch mismatch at 0x{off:x} ({desc}): got 0x{cur:x}, expected 0x{expected:x}"
        struct.pack_into("<I", pc_sf_orig, off, new_val)
        print(f"  PATCH 0x{off:06x} ({desc}): 0x{expected:06x} -> 0x{new_val:06x}")

    print("\n=== Patching PC Master Chapter Dispatcher ===")
    # Common Route CALL targets (Ch.2..Ch.8 + Intermission):
    patch_u32(0x001f54 + 4, 0x024840, stub_ch2, "Ch.2 -> PS2 Ch.2 + Ruah intro")
    patch_u32(0x001fd8 + 4, 0x048b40, unit_entries[("ch3", 0x114)], "Ch.3 -> PS2 Ch.3")
    patch_u32(0x00205c + 4, 0x06ecfc, unit_entries[("ch4", 0x110)], "Ch.4 -> PS2 Ch.4")
    patch_u32(0x0020d8 + 4, 0x09d2a0, unit_entries[("inter", 0x438)], "Intermission -> PS2 6 Interludes")
    patch_u32(0x42fe08 + 4, 0x0b8e80, unit_entries[("ch5", 0x12c)], "Ch.5 -> PS2 Ch.5")
    patch_u32(0x0023a4 + 4, 0x0e7630, unit_entries[("ch6", 0x114)], "Ch.6 -> PS2 Ch.6 Mediard")
    patch_u32(0x002428 + 4, 0x103c4c, unit_entries[("ch7", 0x114)], "Ch.7 -> PS2 Ch.7")
    patch_u32(0x0024ac + 4, 0x14b18c, unit_entries[("ch8", 0x4a4)], "Ch.8 -> PS2 Ch.8 Route Select")

    # Heroine Route == 8 (Ruah) dispatch hooks after route == 7 (or route == 6 for Epilogue):
    patch_u32(0x002690 + 8, 0x0026ac, stub_ruah9,  "Ch.9  route==8 -> Ruah Ch.9")
    patch_u32(0x002864 + 8, 0x002880, stub_ruah10, "Ch.10 route==8 -> Ruah Ch.10")
    patch_u32(0x002a30 + 8, 0x002a4c, stub_ruah11, "Ch.11 route==8 -> Ruah Ch.11")
    patch_u32(0x002c0c + 8, 0x002c28, stub_ruah12, "Ch.12 route==8 -> Ruah Ch.12")
    patch_u32(0x002de0 + 8, 0x002dfc, stub_ruah13, "Ch.13 route==8 -> Ruah Ch.13")
    patch_u32(0x002fac + 8, 0x002fc8, stub_ruah14, "Ch.14 route==8 -> Ruah Ch.14")
    patch_u32(0x003144 + 8, 0x003160, stub_ruahEp, "Epilogue route==8 -> Ruah Epilogue")

    # Fix vanilla Pajama Soft compiler bug at 0x3f7f54: 21-dword opcode 0x80030b15 was emitted
    # with low byte 0x14 (20), causing 0x43fda1 (Save/Load linear msg_id scanner) to land on its
    # 20th argument (0x00010000 at 0x3f7fa4, nw==0) and halt before reaching appended scripts!
    # P_ARK201.exe (0x44c23c..0x44c24c) explicitly accepts 0x80030b15 (21 dwords).
    patch_u32(0x3f7f54, 0x80030b14, 0x80030b15, "Fix vanilla 0x80030b14 -> 0x80030b15 (21 dwords) for 0x43fda1 save/load scan")

    # Expand Omake (SPECIAL) Menu: CG Gallery, Scene Replay, Music Mode, Movie Mode
    omake_assets.patch_omake_scripts(
        pc_sf_orig, ensure_fn_id, patch_u32, unit_entries,
        needed_pags, needed_bgms, needed_movs,
    )

    # Update header max_msg_id & write staged scenario.dat, filename.dat, textdata.bin
    struct.pack_into("<I", pc_sf_orig, 12, next_msg_id - 1)
    struct.pack_into("<I", pc_tf_orig, 12, tf_count)

    # Build filename.dat
    fn_out = bytearray(b"PJADV_FL0001")
    fn_out.extend(struct.pack("<I", len(pc_fn_list)))
    for nm in pc_fn_list:
        nb = nm.encode("cp932")
        fn_out.extend(nb + b"\x00" * (32 - len(nb)))

    with open(os.path.join(STAGED_DIR, "scenario.dat"), "wb") as f:
        f.write(pc_sf_orig)
    with open(os.path.join(STAGED_DIR, "filename.dat"), "wb") as f:
        f.write(fn_out)
    with open(os.path.join(STAGED_DIR, "textdata.bin"), "wb") as f:
        f.write(common.crypt_textdata(bytes(pc_tf_orig)))

    # Save exact asset manifest!
    manifest = {
        "pags": {str(k): v for k, v in sorted(needed_pags.items())},
        "pxgs": {f"{k[0]}:{k[1]}": v for k, v in sorted(needed_pxgs.items())},
        "vois": {str(k): v for k, v in sorted(needed_vois.items())},
        "bgms": {str(k): v for k, v in sorted(needed_bgms.items(), key=lambda x: str(x[0]))},
        "ses":  {str(k): v for k, v in sorted(needed_ses.items())},
        "movs": {str(k): v for k, v in sorted(needed_movs.items())},
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("\n=== Script Port Complete! ===")
    print(f"  scenario.dat: {len(pc_sf_orig):,} bytes (+{len(pc_sf_orig) - 4413456:,} B)")
    print(f"  textdata.bin: {len(pc_tf_orig):,} bytes ({tf_count:,} strings)")
    print(f"  filename.dat: {len(fn_out):,} bytes ({len(pc_fn_list):,} entries, +{len(pc_fn_list) - pc_fn_cnt:,} new)")
    print(f"  EXACT New Assets Needed:")
    print(f"    PAG graphics: {len(needed_pags)}")
    print(f"    PXG sub-sprites: {len(needed_pxgs)} (across {len({k[0] for k in needed_pxgs})} PXG packs)")
    print(f"    Voices: {len(needed_vois)}")
    print(f"    BGMs: {len(needed_bgms)} -> {list(needed_bgms.values())}")
    print(f"    SEs: {len(needed_ses)}")
    print(f"    Movies: {needed_movs}")
    iso.close()


if __name__ == "__main__":
    main()
