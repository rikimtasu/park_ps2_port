import os
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import common
import awake_movies

# 6 New PS2 Awake BGM tracks added to Music Mode Page 4 (M14..M19, track IDs 74..79)
OMAKE_NEW_BGMS = [
    # (slot_num 14..19, track_id 74..79, fn_name, bgm_flk_idx, display_title, callback_ip, cursor_fn_id)
    (14, 74, "SYS_OM_P4M14", 77,  "BGM_CS8", "ルーアのテーマ",             0x40DE54, 34321),
    (15, 75, "SYS_OM_P4M15", 125, "BGM99",   "覚醒の絆",                   0x40DEE8, 34322),
    (16, 76, "SYS_OM_P4M16", 80,  "BGM_OP1", "贖罪のラプソディー (Awake)", 0x40DF7C, 34323),
    (17, 77, "SYS_OM_P4M17", 81,  "BGM_OP2", "原罪のレクイエム (Awake)",   0x40E010, 34324),
    (18, 78, "SYS_OM_P4M18", 78,  "BGM_ED1", "Sigh… (Awake ED1)",          0x40E0A4, 34325),
    (19, 79, "SYS_OM_P4M19", 79,  "BGM_ED2", "追憶のノクターン (ルーアED)", 0x40E138, 34326),
]

# Standard 20-slot CG Gallery grid coordinates and button callbacks
CG_SLOT_COORDS = {
    1:  (111, 114, 222, 209, 0x4186A4),
    2:  (228, 114, 339, 209, 0x418720),
    3:  (345, 114, 456, 209, 0x41879C),
    4:  (462, 114, 573, 209, 0x418818),
    5:  (579, 114, 690, 209, 0x418894),
    6:  (111, 213, 222, 308, 0x418910),
    7:  (228, 213, 339, 308, 0x41898C),
    8:  (345, 213, 456, 308, 0x418A08),
    9:  (462, 213, 573, 308, 0x418A84),
    10: (579, 213, 690, 308, 0x418B00),
    11: (111, 312, 222, 407, 0x418B7C),
    12: (228, 312, 339, 407, 0x418BF8),
    13: (345, 312, 456, 407, 0x418C74),
    14: (462, 312, 573, 407, 0x418CF0),
    15: (579, 312, 690, 407, 0x418D6C),
    16: (111, 411, 222, 506, 0x418DE8),
    17: (228, 411, 339, 506, 0x418E64),
    18: (345, 411, 456, 506, 0x418EE0),
    19: (462, 411, 573, 506, 0x418F5C),
    20: (579, 411, 690, 506, 0x418FD8),
}

# 15 New CG Sets added to CG Gallery:
#   - Page 4 (Karin, [0x20000230]==3): Slot 12 (cg_id=72)
#   - Page 7 (Filia, [0x20000230]==6): Slot 9  (cg_id=129)
#   - Page 8 (Other/Ruah, [0x20000230]==7): Slots 7..17 (cg_id=147..157)
#   - Page 9C (Mini-CG 3, [0x20000230]==10): Slots 9..10 (cg_id=209..210)
# Each variation in `variations` is a list of ops:
#   ("BG", cg_name)
#   ("DRAW", slot, cg_name, anchor)
#   ("POS", slot, x, y)
OMAKE_NEW_CGS = [
    # Karin Tab (Page 4, Slot 12, cg_id=72)
    (3, 12, 72, "SYS_OC_THUMB0412", "PS04_4_00A.epa", [
        [("DRAW", 520, "PS04_4_00A", 3)],
    ]),
    # Filia Tab (Page 7, Slot 9, cg_id=129)
    (6, 9, 129, "SYS_OC_THUMB0709", "PS06_7_00A.epa", [
        [("DRAW", 520, "PS06_7_00A", 3)],
        [("DRAW", 520, "PS06_7_00B", 3)],
        [("DRAW", 520, "PS06_7_00C", 3)],
        [("DRAW", 520, "PS06_7_00D", 3)],
    ]),
    # Other / Ruah Tab (Page 8, Slots 7..17, cg_id=147..157)
    (7, 7, 147, "SYS_OC_THUMB0807", "PS02_8_00B.epa", [
        [("DRAW", 520, "PS02_8_00B", 3)],
        [("DRAW", 520, "PS02_8_00A", 3)],
    ]),
    (7, 8, 148, "SYS_OC_THUMB0808", "PS03_8_00B.epa", [
        [("DRAW", 520, "PS03_8_00BG", 3), ("DRAW", 521, "PS03_8_00A", 3), ("POS", 521, 200, 0)],
        [("DRAW", 520, "PS03_8_00B", 3)],
        [("DRAW", 520, "PS03_8_00BG", 3), ("DRAW", 521, "PS03_8_00C", 3), ("POS", 521, 200, 0)],
    ]),
    (7, 9, 149, "SYS_OC_THUMB0809", "PS04_8_00A.epa", [
        [("DRAW", 520, "PS04_8_00A", 3)],
    ]),
    (7, 10, 150, "SYS_OC_THUMB0810", "PS05_8_00B.epa", [
        [("DRAW", 520, "PS05_8_00B", 3)],
        [("DRAW", 520, "PS05_8_00A", 3)],
    ]),
    (7, 11, 151, "SYS_OC_THUMB0811", "PS06_8_00A.epa", [
        [("DRAW", 520, "PS06_8_00A", 3)],
        [("DRAW", 520, "PS06_8_00B", 3)],
        [("DRAW", 520, "PS06_8_00C", 3)],
    ]),
    (7, 12, 152, "SYS_OC_THUMB0812", "PS10_8_00A.epa", [
        [("DRAW", 520, "PS10_8_00A", 3)],
    ]),
    (7, 13, 153, "SYS_OC_THUMB0813", "PS11_8_00.epa", [
        [("DRAW", 520, "PS11_8_00A", 3), ("DRAW", 521, "PS11_8_00B", 3)],
        [("DRAW", 520, "PS11_8_00A", 3), ("DRAW", 521, "PS11_8_00B", 3), ("DRAW", 522, "PS11_8_00C", 3)],
        [("DRAW", 520, "PS11_8_00", 3)],
    ]),
    (7, 14, 154, "SYS_OC_THUMB0814", "PS11_8_01A.epa", [
        [("DRAW", 520, "PS11_8_01A", 3)],
    ]),
    (7, 15, 155, "SYS_OC_THUMB0815", "PS12_8_00B.epa", [
        [("DRAW", 520, "PS12_8_00A", 3)],
        [("DRAW", 520, "PS12_8_00B", 3)],
        [("DRAW", 520, "PS12_8_00C", 3)],
    ]),
    (7, 16, 156, "SYS_OC_THUMB0816", "COMP_PS13_8_00", [
        [("DRAW", 520, "PS13_8_00_BG", 3), ("DRAW", 521, "PS13_8_00_RUA", 3), ("DRAW", 522, "PS13_8_00_HYA", 3)],
    ]),
    (7, 17, 157, "SYS_OC_THUMB0817", "PSED_8_00A.epa", [
        [("DRAW", 520, "PSED_8_00A", 3)],
    ]),
    # Mini-CG Page 3 (Page 9C, Slots 9..10, cg_id=209..210)
    (10, 9, 209, "SYS_OC_THUMB0949", "COMP_PSMG_8_02", [
        [("BG", "PB021_4Y"), ("DRAW", 520, "PSMG_8_02A", 3)],
        [("BG", "PB021_4Y"), ("DRAW", 520, "PSMG_8_02B", 3)],
        [("BG", "PB021_4Y"), ("DRAW", 520, "PSMG_8_02B", 3), ("DRAW", 521, "PSMG_8_02C", 3)],
        [("BG", "PB021_4Y"), ("DRAW", 520, "PSMG_8_02B", 3), ("DRAW", 521, "PSMG_8_02C", 3), ("DRAW", 522, "PSMG_8_02D", 3)],
    ]),
    (10, 10, 210, "SYS_OC_THUMB0950", "COMP_PSMG_8_03", [
        [("BG", "PB056"), ("DRAW", 520, "PSMG_8_03A", 3)],
        [("BG", "PB056"), ("DRAW", 520, "PSMG_8_03B", 3)],
        [("BG", "PB056"), ("DRAW", 520, "PSMG_8_03C", 3)],
        [("BG", "PB056"), ("DRAW", 520, "PSMG_8_03D", 3)],
        [("BG", "PB056"), ("DRAW", 520, "PSMG_8_03E", 3)],
    ]),
]

# Extra PA_CG.DAT PAG indices required by Omake CG Gallery
OMAKE_REQUIRED_PAGS = {
    3514: "PS02_8_00A",
    3515: "PS03_8_00A",
    3516: "PS03_8_00B",
    3517: "PS03_8_00C",
    3518: "PS04_4_00A",
    3519: "PS04_8_00A",
    3520: "PS05_8_00A",
    3521: "PS06_7_00A",
    3522: "PS06_7_00B",
    3523: "PS06_7_00C",
    3524: "PS06_7_00D",
    3525: "PS06_8_00A",
    3526: "PS06_8_00B",
    3527: "PS06_8_00C",
    3549: "PS10_8_00A",
    3555: "PS11_8_00A",
    3556: "PS11_8_00B",
    3557: "PS11_8_00C",
    3558: "PS11_8_01A",
    3565: "PS12_8_00A",
    3566: "PS12_8_00B",
    3569: "PSED_8_00A",
    3574: "PSMG_8_02A",
    3575: "PSMG_8_02B",
    3576: "PSMG_8_02C",
    3577: "PSMG_8_03A",
    3578: "PSMG_8_03B",
    3579: "PSMG_8_03C",
    3580: "PSMG_8_03D",
    3581: "PSMG_8_03E",
    3793: "PS02_8_00B",
    3794: "PS02_8_00C",
    3795: "PS03_8_00BG",
    3796: "PS05_8_00B",
    3800: "PS12_8_00C",
    3801: "PS13_8_00_BG",
    3802: "PS13_8_00_HYA",
    3803: "PS13_8_00_RUA",
    3805: "PS11_8_00",
    3806: "PSMG_8_02D",
}


def patch_movie_theater(pc_sf_orig, ensure_fn_id, patch_u32, emit):
    """Keep the original grid and add Ruah ED2 plus two Awake replay buttons."""
    movie_cb20_ip = emit([
        (0x02000103, [0x30000000, 20]),
        (0x02000103, [0x20000226, 0x30000000]),
        (0x01000401, []),
    ])
    movie_reg19_20_ip = emit([
        (0x0102010A, [3, 19, 462, 402, 573, 497, 1, 0x8743, 0x42FAF4]),
        (0x0102010A, [3, 20, 579, 402, 690, 497, 1, ensure_fn_id("SYS_OV_B20"), movie_cb20_ip]),
        (0x01000202, [0x42F37C]),
    ])
    assert struct.unpack_from("<I", pc_sf_orig, 0x42F354)[0] == 0x0102010A
    struct.pack_into("<10I", pc_sf_orig, 0x42F354,
                     0x01000202, movie_reg19_20_ip, *([0x01000202, 0x42F37C] * 4))

    # Use the existing footer group (5), not grid slots above the PC limit.
    # Its existing enable/cleanup instructions also cover these new buttons.
    replay_reg_ops = [(0x0102010A, [5, 1, 323, 564, 478, 590, 1, 34345, 0x42F4F4])]
    for slot, (_, _, choice, button, (x, y)) in enumerate(awake_movies.OPENINGS, start=2):
        callback = emit([
            (0x02000103, [0x30000000, choice]),
            (0x02000103, [0x20000226, 0x30000000]),
            (0x01000401, []),
        ])
        replay_reg_ops.append((0x0102010A, [5, slot, x, y, x + 247, y + 31, 1, ensure_fn_id(button), callback]))
    replay_reg_ops.append((0x01000202, [0x42F3B8]))
    replay_reg_ip = emit(replay_reg_ops)
    assert struct.unpack_from("<I", pc_sf_orig, 0x42F390)[0] == 0x0102010A
    struct.pack_into("<10I", pc_sf_orig, 0x42F390,
                     0x01000202, replay_reg_ip, *([0x01000202, 0x42F3B8] * 4))

    dispatch_ip = len(pc_sf_orig)
    movies = [(20, "POP22.DAT")] + [(movie[2], movie[1]) for movie in awake_movies.OPENINGS]
    for choice, filename in movies:
        next_ip = len(pc_sf_orig) + 13 * 4
        emit([
            (0x02000103, [0x30000001, choice]),
            (0x02010003, [0x30000001, 0x30000000]),
            (0x01000703, [0x30000001, next_ip]),
            (0x05030002, [ensure_fn_id(filename)]),
            (0x01000202, [0x42F8F8]),
        ])
    emit([(0x01000202, [0x42F8F8])])
    patch_u32(0x42F8DC + 8, 0x42F8F8, dispatch_ip, "Movie Mode play Ruah ED2 / Awake OP1 / Awake OP2")


def patch_omake_scripts(
    pc_sf_orig: bytearray,
    ensure_fn_id,
    patch_u32,
    unit_entries: dict,
    needed_pags: dict,
    needed_bgms: dict,
    needed_movs: dict,
):
    """Expand Omake (CG Gallery, Music Mode, Movie Mode) in scenario.dat."""
    print("\n=== Expanding Omake (CG Gallery, Music Mode, Movie Mode) ===")

    # 1. Ensure all Omake PAGs, BGMs, and Movies are in needed_assets and filename.dat
    for lo, iname in OMAKE_REQUIRED_PAGS.items():
        needed_pags[lo] = iname
        ensure_fn_id(iname)

    for _, _, p4_name, bgm_lo, bgm_stem, _, _, _ in OMAKE_NEW_BGMS:
        needed_bgms[bgm_lo] = bgm_stem
        ensure_fn_id(p4_name)
        ensure_fn_id(bgm_stem)

    needed_movs[16] = "POP22.DAT"
    ensure_fn_id("POP22.DAT")
    ensure_fn_id("SYS_OV_B20")
    for movie_index, filename, _, _, _ in awake_movies.OPENINGS:
        needed_movs[movie_index] = filename

    for _, _, _, thumb_name, _, var_list in OMAKE_NEW_CGS:
        ensure_fn_id(thumb_name)
        for vops in var_list:
            for op_tup in vops:
                if op_tup[0] == "BG":
                    ensure_fn_id(op_tup[1])
                elif op_tup[0] == "DRAW":
                    ensure_fn_id(op_tup[2])

    # 2. Unlock Title Screen OMAKE button and all Omake gallery items by replacing
    #    `0x02000103 <reg>, 0x200001f6` with `0x02000103 <reg>, 1` across scenario.dat
    pos = 32
    unlocked_cnt = 0
    while pos + 4 <= len(pc_sf_orig):
        w = struct.unpack_from("<I", pc_sf_orig, pos)[0]
        nw = w & 0xFF
        if nw == 0:
            pos += 4
            continue
        if w == 0x02000103 and nw == 3:
            reg, val = struct.unpack_from("<II", pc_sf_orig, pos + 4)
            if val == 0x200001F6:
                struct.pack_into("<I", pc_sf_orig, pos + 8, 1)
                unlocked_cnt += 1
        pos += nw * 4
    print(f"  Unlocked Title Screen OMAKE button & {unlocked_cnt} Omake gallery checks (0x200001f6 -> 1)")

    def emit(inst_list: list[tuple[int, list[int]]]) -> int:
        start = len(pc_sf_orig)
        for w, args in inst_list:
            assert (w & 0xFF) == 1 + len(args), f"Bad word count for 0x{w:08x}: {len(args)}"
            pc_sf_orig.extend(struct.pack("<I", w))
            for a in args:
                pc_sf_orig.extend(struct.pack("<I", a & 0xFFFFFFFF))
        return start

    # ================================================================
    # A. MUSIC MODE (SOUND THEATER) EXPANSION (Page 4: M14..M19)
    # ================================================================
    # 1) Register buttons 14..19 on Page 4 (hooked at 0x40c364 JMP 0x40c36c)
    music_reg_ops = []
    for idx_m, (slot_num, _, p4_name, _, _, _, cb_ip, _) in enumerate(OMAKE_NEW_BGMS):
        y0 = 237 + idx_m * 44
        y1 = y0 + 31
        music_reg_ops.append((0x0102010A, [4, slot_num, 455, y0, 702, y1, 1, ensure_fn_id(p4_name), cb_ip]))
    music_reg_ops.append((0x01000202, [0x40C36C]))
    music_p4_reg_ip = emit(music_reg_ops)
    patch_u32(0x40C364 + 4, 0x40C36C, music_p4_reg_ip, "Music Mode Page 4 register M14..M19")

    # 2) Cursor display on Page 4 for track IDs 74..79 (hooked at 0x40d56c JZ 0x40d590)
    music_p4_cur_ip = len(pc_sf_orig)
    for _, track_id, _, _, _, _, _, cur_fn in OMAKE_NEW_BGMS:
        blk_start = len(pc_sf_orig)
        nxt_blk = blk_start + (3 + 3 + 3 + 4 + 2) * 4
        emit([
            (0x02000103, [0x30000002, track_id]),
            (0x02010003, [0x30000002, 0x30000001]),
            (0x01000703, [0x30000002, nxt_blk]),
            (0x04000004, [103, cur_fn, 0]),
            (0x01000202, [0x40D590]),
        ])
    emit([(0x01000202, [0x40D590])])
    patch_u32(0x40D56C + 8, 0x40D590, music_p4_cur_ip, "Music Mode Page 4 cursor M14..M19")

    # 3) BGM playback for track IDs 74..79 (hooked at 0x40f284 JZ 0x40f2a4)
    music_p4_play_ip = len(pc_sf_orig)
    for _, track_id, _, _, bgm_stem, _, _, _ in OMAKE_NEW_BGMS:
        blk_start = len(pc_sf_orig)
        nxt_blk = blk_start + (3 + 3 + 3 + 3 + 2) * 4
        emit([
            (0x02000103, [0x30000001, track_id]),
            (0x02010003, [0x30000001, 0x30000000]),
            (0x01000703, [0x30000001, nxt_blk]),
            (0x05000003, [ensure_fn_id(bgm_stem), 1]),
            (0x01000202, [0x40F2A4]),
        ])
    emit([(0x01000202, [0x40F2A4])])
    patch_u32(0x40F284 + 8, 0x40F2A4, music_p4_play_ip, "Music Mode Page 4 play M14..M19")

    # ================================================================
    # B. MOVIE MODE: Ruah ending in slot 20; Awake openings in the footer
    # ================================================================
    patch_movie_theater(pc_sf_orig, ensure_fn_id, patch_u32, emit)

    # ================================================================
    # C. CG GALLERY (ART GALLERY) EXPANSION (15 New CG Sets across Pages 4, 7, 8, 9C)
    # ================================================================
    # Switch Tab 8 (その他 / Ruah, [0x20000230]==7) BGM to BGM_CS8 (Ruah's Theme)
    patch_u32(0x419228 + 4, 301, ensure_fn_id("BGM_CS8"), "CG Gallery Page 8 BGM -> BGM_CS8")

    # Group new CGs by page_idx (3=Page4, 6=Page7, 7=Page8, 10=Page9C)
    page_jmp_locs = {
        3:  (0x413FA8 + 4, "SYS_OC_BASE04"),   # SYS_OC_BASE04 end JMP 0x4186a0
        6:  (0x41575C + 4, "SYS_OC_BASE07"),   # SYS_OC_BASE07 end JMP 0x4186a0
        7:  (0x415BD8 + 4, "SYS_OC_BASE08"),   # SYS_OC_BASE08 end JMP 0x4186a0
        10: (0x417BEC + 4, "SYS_OC_BASE09C"),  # SYS_OC_BASE09C end JMP 0x4186a0
    }
    for page_idx, (jmp_off, base_name) in page_jmp_locs.items():
        page_cgs = [c for c in OMAKE_NEW_CGS if c[0] == page_idx]
        reg_ops = []
        for _, slot_num, _, thumb_name, _, _ in page_cgs:
            x0, y0, x1, y1, cb_ip = CG_SLOT_COORDS[slot_num]
            reg_ops.append((0x0102010A, [3, slot_num, x0, y0, x1, y1, 1, ensure_fn_id(thumb_name), cb_ip]))
        reg_ops.extend([
            (0x04000102, [0x68]),
            (0x04000004, [0x68, ensure_fn_id(base_name), 3]),
            (0x01000202, [0x4186A0]),
        ])
        ext_ip = emit(reg_ops)
        patch_u32(jmp_off, 0x4186A0, ext_ip, f"CG Gallery Page {page_idx} register {len(page_cgs)} new CG thumbnails")

    # Emit CG Viewer sequences for all 15 new CG IDs (hooked at 0x42e59c JZ 0x42ef9c)
    cg_viewer_ext_ip = len(pc_sf_orig)
    for _, _, cg_id, _, _, var_list in OMAKE_NEW_CGS:
        # Build variation sub-blocks first in a temporary list so we know exact byte sizes
        # When [0x20000231] (in 0x30000000) == cg_id:
        #   Load [0x10000237] into 0x30000001
        #   Check var_idx = 1..len(var_list)
        #   If none match, set [0x10000238] = 1 and JMP 0x42efbc
        var_blocks = []
        for v_idx, vops in enumerate(var_list, start=1):
            b_ops = [
                (0x02000103, [0x30000002, v_idx]),
                (0x02010003, [0x30000002, 0x30000001]),
                (0x01000703, [0x30000002, 0]),  # placeholder for next var block IP
                # Always clear overlay slots 521, 522, 523 before drawing variation
                (0x04000102, [521]),
                (0x04000102, [522]),
                (0x04000102, [523]),
            ]
            for op_tup in vops:
                if op_tup[0] == "BG":
                    b_ops.append((0x80010102, [ensure_fn_id(op_tup[1])]))
                elif op_tup[0] == "DRAW":
                    _, slot, cg_name, anchor = op_tup
                    fn_id = ensure_fn_id(cg_name)
                    b_ops.append((0x04000004, [slot, fn_id, anchor]))
                    if slot == 520:
                        b_ops.extend([
                            (0x02000103, [0x30000002, fn_id]),
                            (0x02000103, [0x1000023A, 0x30000002]),
                        ])
                elif op_tup[0] == "POS":
                    _, slot, px, py = op_tup
                    b_ops.append((0x04000304, [slot, px, py]))
            b_ops.extend([
                (0x02000103, [0x30000002, 1]),
                (0x02000103, [0x10000239, 0x30000002]),
                (0x01000202, [0x42EFBC]),
            ])
            var_blocks.append(b_ops)

        # End-of-variations block: clear 521..523, set [0x10000238] = 1, JMP 0x42efbc
        end_var_ops = [
            (0x04000102, [521]),
            (0x04000102, [522]),
            (0x04000102, [523]),
            (0x02000103, [0x30000002, 1]),
            (0x02000103, [0x10000238, 0x30000002]),
            (0x01000202, [0x42EFBC]),
        ]

        # Calculate total size of this cg_id block
        hdr_ops_sz = (3 + 3 + 3 + 3) * 4  # MOV cg_id, EQ, JZ next_cg, MOV 0x30000001=[0x10000237]
        var_szs = [sum((w & 0xFF) * 4 for w, _ in b) for b in var_blocks]
        end_sz = sum((w & 0xFF) * 4 for w, _ in end_var_ops)
        next_cg_ip = len(pc_sf_orig) + hdr_ops_sz + sum(var_szs) + end_sz

        emit([
            (0x02000103, [0x30000002, cg_id]),
            (0x02010003, [0x30000002, 0x30000000]),
            (0x01000703, [0x30000002, next_cg_ip]),
            (0x02000103, [0x30000001, 0x10000237]),
        ])
        for b_ops, b_sz in zip(var_blocks, var_szs):
            nxt_v_ip = len(pc_sf_orig) + b_sz
            b_ops[2] = (0x01000703, [0x30000002, nxt_v_ip])
            emit(b_ops)
        emit(end_var_ops)
        assert len(pc_sf_orig) == next_cg_ip

    emit([(0x01000202, [0x42EF9C])])
    patch_u32(0x42E59C + 8, 0x42EF9C, cg_viewer_ext_ip, "CG Gallery Viewer dispatch 15 new CG sets")
    awake_movies.patch_startup_movie(pc_sf_orig, ensure_fn_id(awake_movies.OPENINGS[0][1]))
    awake_movies.patch_title_idle_movies(
        pc_sf_orig, tuple(ensure_fn_id(name) for name in awake_movies.TITLE_IDLE_MOVIES),
    )


def _load_vanilla_epa(name: str) -> Image.Image:
    raw = common.read_pc_archive_file("archive.dat", name) or common.read_pc_archive_file("archive1.dat", name)
    if not raw:
        raise RuntimeError(f"Vanilla EPA not found: {name}")
    return common.decode_epa_image(common.decompress_zzz(raw))


def _make_2state_thumb(template_arr: np.ndarray, src_im: Image.Image) -> Image.Image:
    """Create a 111x190 2-state thumbnail (top 111x95 normal + bottom 111x95 hover) matching vanilla PC style."""
    out = template_arr.copy()
    # Center-crop src_im to 107:79 aspect ratio before Lanczos downscaling to (107, 79)
    sw, sh = src_im.size
    # If tall scrolling CG (e.g. 800x1000), crop the main 800x600 portion featuring the character
    if sh > 650:
        src_im = src_im.crop((0, 0, min(sw, 800), 600))
        sw, sh = src_im.size
    elif sw > 850:
        x_off = (sw - 800) // 2
        src_im = src_im.crop((x_off, 0, x_off + 800, min(sh, 600)))
        sw, sh = src_im.size

    rgb_im = src_im.convert("RGB").resize((107, 79), Image.Resampling.LANCZOS)
    rgb = np.array(rgb_im, dtype=np.float32)

    # Normal state (x=2..109, y=14..93) with 2px inner bevel shadow on left (x=2..3) and top (y=14..15)
    norm = rgb.copy()
    norm[:2, :, :] *= 0.30
    norm[:, :2, :] *= 0.30
    out[14:93, 2:109, :3] = np.clip(norm, 0, 255).astype(np.uint8)
    out[14:93, 2:109, 3] = 255

    # Hover state (x=2..109, y=109..188): warm orange-gold highlight + 2px inner bevel shadow
    orange = np.array([255.0, 140.0, 65.0], dtype=np.float32)
    hov = np.clip(rgb * 0.68 + orange * 0.42, 0, 255)
    hov[:2, :, :] *= 0.30
    hov[:, :2, :] *= 0.30
    out[109:188, 2:109, :3] = np.clip(hov, 0, 255).astype(np.uint8)
    out[109:188, 2:109, 3] = 255

    return Image.fromarray(out, "RGBA")


def _make_gb_record(
    template_rec: bytes,
    dname: str,
    epa_name: str,
    anm_name: str,
    xy: tuple[int, int] | None = None,
) -> bytes:
    rec = bytearray(template_rec)
    db = dname.encode("cp932")
    eb = epa_name.encode("cp932")
    ab = anm_name.encode("cp932")
    rec[60:92] = db + b"\x00" * (32 - len(db))
    rec[92:124] = eb + b"\x00" * (32 - len(eb))
    rec[124:156] = ab + b"\x00" * (32 - len(ab))
    if xy is not None:
        struct.pack_into("<ii", rec, 1028, xy[0], xy[1])
    return bytes(rec)


def _render_music_titles_on_sheet(sheet: Image.Image) -> Image.Image:
    """Extend 512x512 sys_m_files05.EPA to 512x768 and draw M14..M19 normal+hover titles."""
    canvas = Image.new("RGBA", (512, 768), (0, 0, 0, 0))
    canvas.paste(sheet, (0, 0))

    # UV coordinates from sys_om_p1m14..19.bnm:
    # (x_base, y_normal, y_hover, title_str)
    slots = [
        (256, 318, 349, "ルーアのテーマ"),
        (256, 380, 411, "覚醒の絆"),
        (256, 442, 473, "贖罪のラプソディー (Awake)"),
        (0,   512, 543, "原罪のレクイエム (Awake)"),
        (0,   574, 605, "Sigh… (Awake ED1)"),
        (0,   636, 667, "追憶のノクターン (ルーアED)"),
    ]

    font_path = r"C:\Windows\Fonts\msgothic.ttc"
    if not os.path.exists(font_path):
        font_path = r"C:\Windows\Fonts\meiryo.ttc"

    for xb, yn, yh, title in slots:
        f_sz = 17 if len(title) <= 12 else 14
        font = ImageFont.truetype(font_path, f_sz)

        # Render normal plate (247x31): white bold text with dark gray/black outline & drop shadow
        norm_tile = Image.new("RGBA", (247, 31), (0, 0, 0, 0))
        nd = ImageDraw.Draw(norm_tile)
        bbox = nd.textbbox((0, 0), title, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (247 - tw) // 2 - bbox[0]
        ty = (31 - th) // 2 - bbox[1]
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (2, 1), (1, 2)]:
            nd.text((tx + dx, ty + dy), title, font=font, fill=(35, 35, 35, 255))
        nd.text((tx, ty), title, font=font, fill=(250, 250, 250, 255))
        canvas.alpha_composite(norm_tile, (xb, yn))

        # Render hover plate (247x31): cyan/blue outer glow + crisp white inner text
        glow_tile = Image.new("RGBA", (247, 31), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_tile)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                gd.text((tx + dx, ty + dy), title, font=font, fill=(25, 115, 210, 220))
        glow_tile = glow_tile.filter(ImageFilter.GaussianBlur(radius=1.2))
        hd = ImageDraw.Draw(glow_tile)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            hd.text((tx + dx, ty + dy), title, font=font, fill=(15, 75, 165, 255))
        hd.text((tx, ty), title, font=font, fill=(235, 250, 255, 255))
        canvas.alpha_composite(glow_tile, (xb, yh))

    return canvas


def _render_movie_button(title: str) -> Image.Image:
    """Use the existing 247x31 music-button animation's normal/hover UVs."""
    sheet = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    font = ImageFont.truetype(r"C:\Windows\Fonts\msgothic.ttc", 17)
    for y, border in ((318, (70, 70, 85, 255)), (349, (65, 170, 240, 255))):
        tile = Image.new("RGBA", (247, 31), (20, 30, 50, 235))
        draw = ImageDraw.Draw(tile)
        draw.rounded_rectangle((0, 0, 246, 30), radius=4, outline=border, width=2)
        box = draw.textbbox((0, 0), title, font=font)
        x = (247 - (box[2] - box[0])) // 2 - box[0]
        ty = (31 - (box[3] - box[1])) // 2 - box[1]
        draw.text((x, ty), title, font=font, fill=(245, 250, 255, 255))
        sheet.alpha_composite(tile, (256, y))
    return sheet


def build_omake_graphics(
    pc_gb_orig: bytearray,
    gb_seen: set,
    new_gb_recs: list,
    written_epas: dict,
    preview_dir: str,
):
    """Build all expanded Omake UI base plates, thumbnails, and graphic.bin records."""
    print("=== Building Expanded Omake UI Textures & Thumbnails ===")

    # Helper to decode a staged or vanilla EPA
    def get_epa_im(epa_name: str) -> Image.Image:
        eu = epa_name.upper()
        if eu in written_epas:
            return common.decode_epa_image(written_epas[eu][1])
        return _load_vanilla_epa(epa_name)

    def save_epa(exact_name: str, im: Image.Image):
        epa_bytes = common.encode_epa_image(im)
        rt = common.decode_epa_image(epa_bytes)
        assert rt.size == im.size
        written_epas[exact_name.upper()] = (exact_name, epa_bytes)

    # 1. Expand numbered grid bases using vanilla sys_oc_base09a.EPA (which has all 20 numbered boxes 01..20!)
    base_all20 = _load_vanilla_epa("sys_oc_base09a.epa")
    xs = [0, 117, 234, 351, 468]
    ys = [0, 99, 198, 297]

    def copy_slots(dst_im: Image.Image, slot_nums: list[int]) -> Image.Image:
        out = dst_im.copy()
        for s in slot_nums:
            r, c = (s - 1) // 5, (s - 1) % 5
            x, y = xs[c], ys[r]
            box = base_all20.crop((x, y, x + 111, y + 95))
            out.paste(box, (x, y))
        return out

    save_epa("sys_oc_base04.EPA",  copy_slots(_load_vanilla_epa("sys_oc_base04.epa"),  [12]))
    save_epa("sys_oc_base07.EPA",  copy_slots(_load_vanilla_epa("sys_oc_base07.epa"),  [9]))
    save_epa("sys_oc_base08.EPA",  copy_slots(_load_vanilla_epa("sys_oc_base08.epa"),  list(range(7, 18))))
    save_epa("sys_oc_base09c.EPA", copy_slots(_load_vanilla_epa("sys_oc_base09c.epa"), [9, 10]))
    save_epa("sys_ov_base01.EPA",  copy_slots(_load_vanilla_epa("sys_ov_base01.epa"),  [20]))

    # 2. Expand Music Mode Page 4 base (sys_m_base4.EPA) with M14..M19 bars from sys_m_base1.EPA
    m_base1 = _load_vanilla_epa("sys_m_base1.epa")
    m_base4 = _load_vanilla_epa("sys_m_base4.epa").copy()
    # Right column M14..M19 sits at x=310..626, y=132..396
    m14_19_crop = m_base1.crop((310, 132, 626, 396))
    m_base4.paste(m14_19_crop, (310, 132))
    save_epa("sys_m_base4.EPA", m_base4)
    m_base4.save(os.path.join(preview_dir, "sys_m_base4_expanded.png"))

    # 3. Extend sys_m_files05.EPA (512x512 -> 512x768) with M14..M19 song titles
    m_files05 = _render_music_titles_on_sheet(_load_vanilla_epa("sys_m_files05.epa"))
    save_epa("sys_m_files05.EPA", m_files05)
    m_files05.save(os.path.join(preview_dir, "sys_m_files05_expanded.png"))

    # 4. Build composite source images for multi-layer CGs (PS13_8_00, PSMG_8_02, PSMG_8_03)
    comp_ps13 = get_epa_im("ps13_8_00_haikei.epa").convert("RGBA")
    for lyr_nm in ("ps13_8_00_ruah.epa", "ps13_8_00_haya.epa"):
        lyr = get_epa_im(lyr_nm).convert("RGBA")
        xo = (lyr.width - comp_ps13.width) // 2
        comp_ps13.alpha_composite(lyr.crop((xo, 0, xo + comp_ps13.width, comp_ps13.height)))

    comp_mg02 = get_epa_im("PB021_4Y.epa").convert("RGBA")
    for lyr_nm in ("psmg_8_02_haikei.epa", "psmg_8_02a_haya.epa", "psmg_8_02a_rua.epa", "psmg_8_02_hibana.epa"):
        lyr = get_epa_im(lyr_nm).convert("RGBA")
        comp_mg02.alpha_composite(lyr, ((800 - lyr.width) // 2, (600 - lyr.height) // 2))

    comp_mg03 = get_epa_im("PB056.epa").convert("RGBA")
    for lyr_nm in ("psmg_8_03_haikei.epa", "psmg_8_03a_haya.epa", "psmg_8_03a_rua.epa"):
        lyr = get_epa_im(lyr_nm).convert("RGBA")
        comp_mg03.alpha_composite(lyr, ((800 - lyr.width) // 2, (600 - lyr.height) // 2))

    composites = {
        "COMP_PS13_8_00": comp_ps13,
        "COMP_PSMG_8_02": comp_mg02,
        "COMP_PSMG_8_03": comp_mg03,
    }

    # 5. Generate all 16 111x190 2-state thumbnail EPAs (15 CG Gallery + 1 Movie Mode)
    thumb_tmpl = np.array(_load_vanilla_epa("sys_os_thumb0101.epa"))

    for _, _, _, thumb_name, src_key, _ in OMAKE_NEW_CGS:
        src_im = composites[src_key] if src_key in composites else get_epa_im(src_key)
        th_im = _make_2state_thumb(thumb_tmpl, src_im)
        epa_name = f"{thumb_name.lower()}.EPA"
        save_epa(epa_name, th_im)

    # Movie Mode Slot 20 thumbnail (sys_ov_thum20.EPA from PSED_8_00A.epa)
    ov20_im = _make_2state_thumb(thumb_tmpl, get_epa_im("PSED_8_00A.epa"))
    save_epa("sys_ov_thum20.EPA", ov20_im)
    ov20_im.save(os.path.join(preview_dir, "sys_ov_thum20.png"))
    for number, (_, _, _, button, _) in enumerate(awake_movies.OPENINGS, start=1):
        image = _render_movie_button(f"Awake OP{number}")
        save_epa(f"{button.lower()}.EPA", image)
        image.save(os.path.join(preview_dir, f"{button.lower()}.png"))

    # 6. Append the 22 new 1092-byte PJGraphicDef records to graphic.bin
    # Index vanilla slot templates so each button gets its exact screen (x, y) at 1028..1036
    # and sheet UV (src_x, src_y, w, h) at 1076..1092!
    cnt = struct.unpack_from("<I", pc_gb_orig, 12)[0]
    vanilla_gb = {}
    for i in range(cnt):
        rec = bytes(pc_gb_orig[16 + i * 1092 : 16 + (i + 1) * 1092])
        dn = rec[60:92].split(b"\x00", 1)[0].decode("cp932", "replace").upper()
        vanilla_gb[dn] = rec

    def add_gb(tmpl: bytes, dname: str, epa_name: str, anm_name: str, xy: tuple[int, int] | None = None):
        du = dname.upper()
        if du not in gb_seen:
            gb_seen.add(du)
            new_gb_recs.append(_make_gb_record(tmpl, dname.lower(), epa_name, anm_name, xy=xy))

    # Music Mode Page 4 M14..M19: clone from SYS_OM_P1M14..19 (exact screen x,y + sheet UV src_x,src_y)
    for slot_num, _, p4_name, _, _, _, _, _ in OMAKE_NEW_BGMS:
        tmpl_m = vanilla_gb[f"SYS_OM_P1M{slot_num:02d}"]
        add_gb(tmpl_m, p4_name, "sys_m_files05.EPA", f"sys_om_p1m{slot_num:02d}.bnm")

    # Movie Mode Slot 20: clone from SYS_OV_B19 and set screen (x, y) = (579, 402)
    add_gb(vanilla_gb["SYS_OV_B19"], "sys_ov_b20", "sys_ov_thum20.EPA", "sys_ov_b.bnm", xy=(579, 402))
    for _, _, _, button, xy in awake_movies.OPENINGS:
        add_gb(vanilla_gb["SYS_OM_P1M14"], button, f"{button.lower()}.EPA", "sys_om_p1m14.bnm", xy=xy)

    # CG Gallery 15 new thumbnails: clone from SYS_OC_THUMB01{slot_num:02d} (exact screen x,y for slot_num!)
    for _, slot_num, _, thumb_name, _, _ in OMAKE_NEW_CGS:
        tmpl_c = vanilla_gb[f"SYS_OC_THUMB01{slot_num:02d}"]
        add_gb(tmpl_c, thumb_name, f"{thumb_name.lower()}.EPA", "sys_oc_thumb.bnm")

    print(f"  Added 7 expanded Omake base plates, 16 thumbnails, 2 Awake movie buttons, and 24 graphic.bin records!")
