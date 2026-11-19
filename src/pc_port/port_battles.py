import json
import os
import re
import struct
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import ruah_battle_assets as rba

STAGED_DIR = os.path.join(common.WORK_DIR, "staged")
BATTLE_OUT = os.path.join(common.MOD_OUT_DIR, "battle1.dat")

# All 14 PS2-exclusive / Ruah-route battle IDs
RUAH_BIDS = {62, 808, 809, 810, 1810, 811, 1811, 2811, 3811, 812, 1812, 813, 1813, 2813}

RANK_NAMES = {0: "easy", 1: "normal", 2: "hard", 3: "boss", 4: "camp"}
ENEMY_ICONS = [
    "mokujin", "tetsujin", "ninja", "shinobi", "chizakura",
    "saburumu", "saburumu_m", "konoe", "ankoku", "hell",
    "litte", "suika", "gouriki", "kourin", "kousoku",
    "kyuukyoku", "wise1", "wise2", "wise3", "wise4",
    "judas", "nazo",
]

# Clean fallbacks for the 6 PS2-only camp_loading / camp_top TGAs
TGA_FALLBACKS = {
    "data/bg/camp_loading/battle_load_0111b.tga": "data/bg/CAMP_LOADING/BATTLE_LOAD_0111a.tga",
    "data/bg/camp_loading/battle_load_0811.tga":  "data/bg/CAMP_LOADING/BATTLE_LOAD_0111a.tga",
    "data/bg/camp_loading/battle_load_0812.tga":  "data/bg/CAMP_LOADING/BATTLE_LOAD_0112a.tga",
    "data/bg/camp_top/battle_top_0111b.tga":      "data/bg/CAMP_TOP/BATTLE_TOP_0111a.tga",
    "data/bg/camp_top/battle_top_0811.tga":       "data/bg/CAMP_TOP/BATTLE_TOP_0111a.tga",
    "data/bg/camp_top/battle_top_0812.tga":       "data/bg/CAMP_TOP/BATTLE_TOP_0112a.tga",
}

# Standard recommended prism decks for Ruah chapters
DEFAULT_OSUSUME = """
osusume1
use1  001
use2  065
use3  084
use4  097
use5  105
use6  137
use7  139

osusume2
use1  001
use2  065
use3  074
use4  097
use5  107
use6  137
use7  142

osusume3
use1  001
use2  086
use3  034
use4  051
use5  057
use6  099
use7  113
"""

# New Prism #225 (Heart of Peace) + Ruah's exclusive ally & boss skills (PR 5000..5008)
RUAH_PRISMS_TXT = """\r
\r
;=====================================================================\r
; Prism Ark - Awake (Ruah Route) Additional Prisms\r
;=====================================================================\r
\r
[平和の心]\r
PR = 225\r
\r
PRISM_TYPE = SPECIAL\r
PRISM_LEVEL = 0\r
document = 0,"【平和の心】"\r
document = 1,"ルーアが追い求める、理想の世界。"\r
\r
ATTRIB = NORMAL\r
TYPE = STATUS\r
\r
\r
[ノーア・シャローム]\r
PR = 5000\r
document = 0,"【ノーア・シャローム】"\r
document = 1,"ルーアの基本攻撃。鋭い穂先で突く。"\r
ATTRIB = NORMAL\r
TYPE = ATTACK\r
PLAYER_COMMAND = ENEMY\r
\r
EXEC\r
object(enemy)\r
attack(00701 , normal , 100)\r
\r
\r
[リリトー・イフターハ]\r
PR = 5001\r
document = 0,"【リリトー・イフターハ】　　　消費ＴＰ：２２"\r
document = 1,"光属性攻撃。ルーアの想いを込めた槍は、全てを貫く。"\r
ATTRIB = SHINE\r
TYPE = MAGIC\r
COST = 22\r
PLAYER_COMMAND = ENEMY\r
\r
EXEC\r
object(enemy)\r
magic(00063 , SHINE , 160)\r
\r
\r
[記憶喪失？]\r
PR = 5002\r
document = 0,"【記憶喪失？】"\r
document = 1,"わたしは、いったい誰なのでしょう？"\r
ATTRIB = NORMAL\r
TYPE = DEFENCE\r
PLAYER_COMMAND = OWN_GOAL\r
\r
EXEC\r
object(OWN_GOAL)\r
defense(00027 , 200)\r
\r
\r
[ノーア・シャローム]\r
PR = 5003\r
document = 0,"【ノーア・シャローム】"\r
document = 1,"ルーアの基本攻撃。鋭い穂先で突く。"\r
ATTRIB = NORMAL\r
TYPE = ATTACK\r
PLAYER_COMMAND = ENEMY\r
\r
EXEC\r
object(enemy)\r
attack(00701 , normal , 100)\r
\r
\r
[リリトー・イフターハ]\r
PR = 5004\r
document = 0,"【リリトー・イフターハ】　　　消費ＴＰ：２２"\r
document = 1,"光属性攻撃。ルーアの想いを込めた槍は、全てを貫く。"\r
ATTRIB = SHINE\r
TYPE = MAGIC\r
COST = 22\r
PLAYER_COMMAND = ENEMY\r
\r
EXEC\r
object(enemy)\r
magic(00063 , SHINE , 160)\r
\r
\r
[記憶喪失？]\r
PR = 5005\r
document = 0,"【記憶喪失？】"\r
document = 1,"わたしは、いったい誰なのでしょう？"\r
ATTRIB = NORMAL\r
TYPE = DEFENCE\r
PLAYER_COMMAND = OWN_GOAL\r
\r
EXEC\r
object(OWN_GOAL)\r
defense(00027 , 200)\r
\r
\r
[ノーア・シャローム]\r
PR = 5006\r
document = 0,"【ノーア・シャローム】"\r
document = 1,"ルーアの基本攻撃。鋭い穂先で突く。"\r
ATTRIB = NORMAL\r
TYPE = ATTACK\r
PLAYER_COMMAND = ENEMY\r
\r
EXEC\r
object(enemy)\r
attack(00701 , normal , 110)\r
\r
\r
[ウーリー・ゼカルヤー]\r
PR = 5007\r
document = 0,"【ウーリー・ゼカルヤー】　　　消費ＴＰ：４４"\r
document = 1,"光属性全体攻撃。ルーアの想いが全てを包む光となる。"\r
ATTRIB = SHINE\r
TYPE = MAGIC\r
COST = 44\r
PLAYER_COMMAND = ENEMY_ALL\r
\r
EXEC\r
object_all(enemy)\r
magic(00063 , SHINE , 180)\r
\r
\r
[白き優しき風]\r
PR = 5008\r
document = 0,"【白き優しき風】"\r
document = 1,"白き純粋な心に、愛しき風が生まれる。"\r
ATTRIB = NORMAL\r
TYPE = ASSIST\r
COST = 30\r
PLAYER_COMMAND = OWN_GOAL\r
\r
EXEC\r
object(OWN_GOAL)\r
heal2(00066 , 30)\r
"""


def encode_tga_32(im: Image.Image, bpp: int = 32, top_down: bool = False) -> bytes:
    """Encode PIL Image as uncompressed TGA (32-bit BGRA or 24-bit BGR)."""
    rgba = np.ascontiguousarray(im.convert("RGBA"), dtype=np.uint8)
    h, w = rgba.shape[:2]
    if not top_down:
        rgba = rgba[::-1, :, :]
    if bpp == 24:
        pixels = np.ascontiguousarray(rgba[:, :, [2, 1, 0]]).tobytes()
        desc = 0x20 if top_down else 0x00
    else:
        pixels = np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]]).tobytes()
        desc = 0x28 if top_down else 0x08
    hdr = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, bpp, desc)
    return hdr + pixels


def open_pc_prsm():
    dec_tbl, _ = common.load_prsm_tables()
    bp = os.path.join(common.PC_DIR, "battle.dat")
    with open(bp, "rb") as f:
        magic, cnt, hsz = struct.unpack("<4sII", f.read(12))
        assert magic == b"PRSM"
        f.seek(0)
        hdr = bytearray(f.read(hsz))
        for i in range(12, hsz):
            hdr[i] = dec_tbl[(i % 6) * 256 + hdr[i]]
        index = {}
        for idx in range(cnt):
            noff, foff, fsz = struct.unpack_from("<III", hdr, 12 + idx * 12)
            rec = common.prsm_lz_decode(hdr, noff)
            name = rec[:0x7F].split(b"\x00", 1)[0].decode("cp932", "replace")
            index[name.lower().replace("\\", "/")] = (name, foff, fsz, rec[0x7F], struct.unpack_from("<I", rec, 0x80)[0])

    def read_file(rel_path: str) -> bytes:
        _, foff, fsz, kb, usz = index[rel_path.lower().replace("\\", "/")]
        with open(bp, "rb") as f:
            f.seek(foff)
            raw = bytearray(f.read(fsz))
        for i in range(fsz):
            raw[i] = dec_tbl[(i % 6) * 256 + ((raw[i] - kb) & 0xFF)]
        return common.prsm_lz_decode(raw, 0) if usz > 0 else bytes(raw)

    return index, read_file


def extract_pc_unit_templates(b_idx, read_pc_b):
    """Harvest exact PC .dmo model/shadow/objectsize/LIGHT templates per ch ID."""
    templates = {}
    for k in sorted(b_idx.keys()):
        if ("/char_" in k or "/field_" in k) and k.endswith(".txt"):
            txt = read_pc_b(k).decode("cp932", "replace")
            for blk in re.split(r"(?=^\[)", txt, flags=re.M):
                m = re.search(r"^\s*ch\s*=\s*(\d+)", blk, re.M | re.I)
                if not m:
                    continue
                ch = int(m.group(1))
                if ch in templates:
                    continue
                obj = re.search(r'^\s*object\s*=\s*"([^"]+)"', blk, re.M | re.I)
                if not obj:
                    continue
                shd = re.search(r'^\s*shadow\s*=\s*"([^"]+)"', blk, re.M | re.I)
                osz = re.search(r'^\s*objectsize\s*=\s*([^\r\n;/]+)', blk, re.M | re.I)
                lgt = re.search(r'^\s*LIGHT\s*=\s*([^\r\n;/]+)', blk, re.M | re.I)
                ssc = re.search(r'^\s*shadow_scale\s*=\s*([^\r\n;/]+)', blk, re.M | re.I)
                sal = re.search(r'^\s*shadow_alpha\s*=\s*([^\r\n;/]+)', blk, re.M | re.I)
                templates[ch] = {
                    "object": obj.group(1),
                    "shadow": shd.group(1) if shd else "",
                    "objectsize": osz.group(1).strip() if osz else "2, 2",
                    "light": lgt.group(1).strip() if lgt else "0",
                    "shadow_scale": ssc.group(1).strip() if ssc else "",
                    "shadow_alpha": sal.group(1).strip() if sal else "",
                }
    return templates


def build_enemy_ai(ch_id: int, prisms: list[int]) -> str:
    """Build clean native PC battle AI script using all non-zero prisms on this enemy."""
    n = len(prisms)
    if n <= 1:
        return "exec\r\nselect_prism(1)\r\n"
    lines = ["exec", f"_F750 = RANDOM({n * 10})"]
    for idx in range(1, n):
        thresh = idx * 10
        if idx == 1:
            lines.append(f"_if _F750 < {thresh}")
        else:
            lines.append("_else")
            lines.append(f"_if _F750 < {thresh}")
        lines.append(f"    _F751 = {idx}")
    lines.append("_else")
    lines.append(f"    _F751 = {n}")
    for _ in range(n - 1):
        lines.append("_endif")
    lines += [
        "_if check_tp(_F751) == 0",
        "    _F751 = 1",
        "_endif",
        f"_F755 = ST_SEAL({ch_id})",
        "_if _F755 >= 1",
        "    _F751 = 1",
        "_endif",
        "select_prism(_F751)",
    ]
    return "\r\n".join(lines) + "\r\n"


def format_unit_block(rec_tuple, out_ch: int, templates: dict) -> str:
    """Format a parsed PS2 MCD record as a PC char_*.txt / #character.txt block."""
    nm, orig_ch, num, utype, lv, maxlp, maxtp, atk, dfn, mag, agl, prisms = rec_tuple
    tpl = templates.get(out_ch) or templates.get(171) or templates[0]
    lines = [
        nm,
        f"ch      = {out_ch}",
        f"number  = {num:04d}",
        f"type    = {'enemy' if utype == 1 else 'friend'}",
        f"lv      = {max(1, lv)}",
        f"maxlp   = {max(1, maxlp)}",
        f"maxtp   = {maxtp}",
        f"atk     = {atk}",
        f"def     = {dfn}",
        f"mag     = {mag}",
        f"agl     = {agl}",
    ]
    for pi, pr in enumerate(prisms, 1):
        lines.append(f"prism{pi}  = {pr}")
    lines.append(f'object = "{tpl["object"]}"')
    if tpl["shadow"]:
        lines.append(f'shadow = "{tpl["shadow"]}"')
    if tpl["shadow_scale"]:
        lines.append(f'shadow_scale = {tpl["shadow_scale"]}')
    if tpl["shadow_alpha"]:
        lines.append(f'shadow_alpha = {tpl["shadow_alpha"]}')
    if tpl["objectsize"]:
        lines.append(f'objectsize = {tpl["objectsize"]}')
    lines.append(f'LIGHT = {tpl["light"]}')
    if utype == 1:
        lines.append(build_enemy_ai(out_ch, prisms))
    return "\r\n".join(lines) + "\r\n"


def main():
    b_idx, read_pc_b = open_pc_prsm()
    templates = extract_pc_unit_templates(b_idx, read_pc_b)
    # Register Playable Ally Ruah (ch = 9) 3D model template (based on Fel's shadow/light metrics)
    fel_tpl = templates.get(3) or templates[0]
    ruah_tpl = dict(fel_tpl)
    ruah_tpl["object"] = "data/char/character/ruah/ph2chr09"
    templates[9] = ruah_tpl
    print(f"Harvested {len(templates)} PC unit model templates from battle.dat (+ ch=9 Ruah)")

    # Index existing (map_m, ch, num) in PC char_00XX.txt so we only embed missing units
    pc_char_units = {}
    for m in (8, 9, 10, 11, 12, 13, 62):
        k = f"data/mapscript/map{m:02d}/char_{m:04d}.txt"
        pc_char_units[m] = set()
        if k in b_idx:
            ct = read_pc_b(k).decode("cp932", "replace")
            cur_ch = None
            for line in ct.splitlines():
                ls = line.split(";")[0].split("//")[0].strip()
                m1 = re.match(r"ch\s*=\s*(\d+)", ls, re.I)
                m2 = re.match(r"number\s*=\s*(\d+)", ls, re.I)
                if m1:
                    cur_ch = int(m1.group(1))
                elif m2 and cur_ch is not None:
                    pc_char_units[m].add((cur_ch, int(m2.group(1))))

    # Load PS2 PA_FILE.DAT[318, 319, 320] (FED, MCD, MPD) + Ruah battle voices directly from ISO
    iso = common.IsoReader()
    def get_pf(idx: int) -> bytes:
        r = iso.read_flk_entry("PA_FILE.DAT", idx)
        return common.decompress_zzz(r) if r[:4] == b"ZZZ\x00" else r
    fed = get_pf(318)
    mcd = get_pf(319)
    mpd = get_pf(320)
    ruah_battle_voices = rba.convert_ruah_battle_voices(iso)
    iso.close()

    # Parse all PS2 MCD records -> dict[(ch, num)] = tuple
    mcd_cnt = struct.unpack_from("<I", mcd, 4)[0]
    mcd_map = {}
    for idx in range(mcd_cnt):
        rec = mcd[16 + idx * 88 : 16 + (idx + 1) * 88]
        nm = rec[:32].split(b"\x00", 1)[0].decode("cp932", "replace")
        h = struct.unpack_from("<28H", rec, 32)
        lv = h[0]
        ch = h[1]
        num = h[2]
        utype = h[3]  # 0=friend, 1=enemy
        maxlp = struct.unpack_from("<I", rec, 32 + 8)[0]
        maxtp = struct.unpack_from("<I", rec, 32 + 12)[0]
        atk, dfn, mag, agl = h[8], h[9], h[10], h[11]
        prisms = [h[16 + k] for k in range(8) if h[16 + k] != 0]
        mcd_map[(ch, num)] = (nm, ch, num, utype, lv, maxlp, maxtp, atk, dfn, mag, agl, prisms)

    out_files = []  # [(rel_path, bytes), ...]
    added_paths = set()

    def add_file(rel_path: str, data: bytes):
        norm = rel_path.replace("/", "\\")
        key = norm.lower()
        if key not in added_paths:
            added_paths.add(key)
            out_files.append((norm, data))

    def resolve_tga(p: str, default_p: str) -> str:
        if not p:
            return default_p
        pl = p.lower().replace("\\", "/")
        if pl == "data/bg/battle_loading/bwp_ruah01.tga":
            return "data/bg/BATTLE_LOADING/BWP_RUAH01.tga"
        if pl in TGA_FALLBACKS:
            return TGA_FALLBACKS[pl]
        if pl in b_idx:
            return b_idx[pl][0].replace("\\", "/")
        return default_p

    # ================================================================
    # 1. Generate real BWP_RUAH01.tga (Ruah battle loading screen!)
    # ================================================================
    filia_bwp = read_pc_b("data/bg/BATTLE_LOADING/BWP_FILIA01.tga")
    bw_w, bw_h, bw_bpp, bw_desc = struct.unpack_from("<HHBB", filia_bwp, 12)
    print(f"PC BWP_FILIA01.tga format: {bw_w}x{bw_h} {bw_bpp}bpp desc=0x{bw_desc:02x}")
    ruah_cg_epa = os.path.join(STAGED_DIR, "gfx", "PS03_8_00B.epa")
    im_ruah_bwp = common.decode_epa_image(open(ruah_cg_epa, "rb").read()).resize((bw_w, bw_h), Image.Resampling.LANCZOS)
    add_file("data\\bg\\BATTLE_LOADING\\BWP_RUAH01.tga", encode_tga_32(im_ruah_bwp, bpp=bw_bpp, top_down=bool(bw_desc & 0x20)))

    # ================================================================
    # 2. Prism #225 (Heart of Peace) assets + prism.txt + prismlist.txt
    # ================================================================
    im_p225 = Image.open(os.path.join(STAGED_DIR, "prism225.png")).convert("RGBA")
    im_p225_txt = Image.open(os.path.join(STAGED_DIR, "prism_name_text225.png")).convert("RGBA")
    add_file("data\\prismget\\prism\\prism225.tga", encode_tga_32(im_p225.resize((110, 110), Image.Resampling.LANCZOS), bpp=32, top_down=False))
    add_file("data\\prismget\\prism_name_text225.tga", encode_tga_32(im_p225_txt, bpp=32, top_down=False))
    add_file("data\\プリズム\\prism225.tga", encode_tga_32(im_p225.resize((32, 32), Image.Resampling.LANCZOS), bpp=32, top_down=False))

    p224_x = read_pc_b("data/プリズム/prism224.x").replace(b"prism224.tga", b"prism225.tga").replace(b"PRISM224.TGA", b"prism225.tga")
    add_file("data\\プリズム\\prism225.x", p224_x)

    pc_prism_txt = read_pc_b("prism.txt").decode("cp932", "replace")
    add_file("prism.txt", (pc_prism_txt + RUAH_PRISMS_TXT).encode("cp932", "replace"))

    pc_prismlist = read_pc_b("prismlist.txt").decode("cp932", "replace").rstrip("\r\n")
    new_prismlist = pc_prismlist + "\r\ndata\\プリズム\\prism225.x data\\プリズム\\prism_REF01.tga 11 0.300000 0.00000\r\n"
    add_file("prismlist.txt", new_prismlist.encode("cp932", "replace"))

    # ================================================================
    # 2b. Playable Ally Ruah (ch = 9): ch_sheet, UI TGAs, 3D model, battle voices
    # ================================================================
    orig_ch_sheet = read_pc_b("ch_sheet.txt").decode("cp932", "replace")
    add_file("ch_sheet.txt", rba.build_ruah_ch_sheet(orig_ch_sheet))

    for rel_p, data in rba.generate_ruah_ui_tgas(read_pc_b):
        add_file(rel_p, data)

    for rel_p, data in rba.generate_ruah_3d_model(read_pc_b):
        add_file(rel_p, data)

    for rel_p, data in ruah_battle_voices:
        add_file(rel_p, data)

    orig_common_se = read_pc_b("data/se/common.se").decode("cp932", "replace")
    add_file("data\\se\\common.se", rba.build_ruah_common_se(orig_common_se))

    orig_random_se = read_pc_b("data/se/random.se").decode("cp932", "replace")
    add_file("data\\se\\random.se", rba.build_ruah_random_se(orig_random_se))

    # ================================================================
    # 3. Decompile all 14 Ruah battles' FED -> field_XXXX_YYY.txt
    # ================================================================
    fed_cnt = struct.unpack_from("<I", fed, 4)[0]
    fed_entries = [struct.unpack_from("<HHI", fed, 16 + i * 8) for i in range(fed_cnt)]
    seen_field = set()
    map62_units = {}
    field_count = 0

    for i, (bid, stg, off) in enumerate(fed_entries):
        if bid not in RUAH_BIDS:
            continue
        if (bid, stg) in seen_field:
            continue
        seen_field.add((bid, stg))

        nxt = fed_entries[i + 1][2] if i + 1 < fed_cnt else len(fed)
        blk = fed[off:nxt]

        title = blk[0x00:0x40].split(b"\x00", 1)[0].decode("cp932", "replace") or f"[{bid:04d}-{stg:03d}]"
        cload = resolve_tga(blk[0x40:0x80].split(b"\x00", 1)[0].decode("cp932", "replace"), "data/bg/CAMP_LOADING/BATTLE_LOAD_0111a.tga")
        ctop  = resolve_tga(blk[0x80:0xc0].split(b"\x00", 1)[0].decode("cp932", "replace"), "data/bg/CAMP_TOP/BATTLE_TOP_0111a.tga")
        bload = resolve_tga(blk[0xc0:0x100].split(b"\x00", 1)[0].decode("cp932", "replace"), "data/bg/BATTLE_LOADING/BWP_RUAH01.tga")
        bbg   = resolve_tga(blk[0x100:0x140].split(b"\x00", 1)[0].decode("cp932", "replace"), "data/bg/BATTLE_BG/BATTLEBG_022B.tga")
        mbgm  = blk[0x140:0x150].split(b"\x00", 1)[0].decode("cp932", "replace") or "BGM33"
        bgm   = blk[0x150:0x160].split(b"\x00", 1)[0].decode("cp932", "replace") or "bgm33"

        h = struct.unpack_from("<24H", blk, 0x160)
        ret_flag, win_type, lose_type, ef, osusume = h[2], h[3], h[4], h[5], h[6]
        n_ch, n_def, n_ev = h[7], h[8], h[9]
        lose_ch = h[10]
        lose_voices = list(h[16:24])

        raw_chs = [struct.unpack_from("<5H", blk, 0x190 + c * 10) for c in range(n_ch)]
        raw_defs = [struct.unpack_from("<3H", blk, 0x190 + n_ch * 10 + d * 6) for d in range(n_def)]
        ev_off = 0x190 + n_ch * 10 + n_def * 6
        raw_evs = [struct.unpack_from("<4H", blk, ev_off + e * 8) for e in range(n_ev)]

        # Playable Ally Ruah (ch = 9, friend) enabled natively via P_ARK201_Ruah.exe!
        # Enemy boss [ルーア] (3811 / 1812) maps to ch=171 using Ruah's own 3D model template.
        ch9_remap = {}
        final_chs = []
        embedded_units = []
        embedded_seen = set()
        m_dir = bid % 100

        for ch, num, x, y, delay in raw_chs:
            u = mcd_map.get((ch, num))
            use_tpl_map = templates
            if ch == 9:
                if u is not None and u[3] == 1:
                    # Enemy boss [ルーア] -> ch=171 with Ruah's own ph2chr09 3D model!
                    out_ch = 171
                    ch9_remap[9] = 171
                    use_tpl_map = dict(templates)
                    use_tpl_map[171] = templates[9]
                else:
                    # Playable Ally Ruah (ch = 9)!
                    out_ch = 9
                    ch9_remap[9] = 9
            else:
                out_ch = ch

            final_chs.append((out_ch, num, x, y, delay))

            # If unit is not a chdef clone and not in PC char_00XX.txt, embed its exact MCD definition!
            is_clone = any(d[0] == ch for d in raw_defs)
            if not is_clone and (out_ch, num) not in pc_char_units.get(m_dir, set()):
                if u is not None and (out_ch, num) not in embedded_seen:
                    embedded_seen.add((out_ch, num))
                    ublk = format_unit_block(u, out_ch, use_tpl_map)
                    if m_dir == 62:
                        map62_units[(out_ch, num)] = ublk
                    else:
                        embedded_units.append(ublk)

        lines = [
            title,
            f"battle = {bid}",
            f"stage  = {stg}",
            f'MENUBGM = "{mbgm}"',
            f'BGM     = "{bgm}"',
            f'camp_loading_bg = "{cload}"',
            f'camp_bg         = "{ctop}"',
            f'loading_bg      = "{bload}"',
            f'bg              = "{bbg}"',
            f"return_flag = {ret_flag}",
            f"Win_type    = {win_type}",
            f"Lose_type   = {lose_type}",
        ]
        if lose_ch != 0:
            lines.append(f"Lose_ch     = {lose_ch:03d}")
        if any(lose_voices):
            lines.append("Lose_voice  = " + ",".join(str(v) for v in lose_voices))
        lines.append(f"ef  = {ef}")
        lines.append(f"osusume = {osusume}")

        for out_ch, num, x, y, delay in final_chs:
            lines.append(f"character = {out_ch}, {num:04d}, {x}, {y}, {delay}")
        for dst, src, num in raw_defs:
            if dst == 9 or src == 9:
                continue
            lines.append(f"chdef     = {dst}, {src}, {num:04d}")

        lines.append('txtwin  = "全ての敵の戦闘不能"')
        lines.append('txtlose = "全ての味方の戦闘不能"')

        # Emit battle events (remapping boss ch=9 -> 171, skipping ally ch=9)
        first_emitted = True
        for ev_op, ev_res, ev_cond, ev_val in raw_evs:
            if ev_cond == 0 and ev_val == 9:
                mapped = ch9_remap.get(9)
                if mapped is None:
                    continue
                ev_val = mapped
            kw = "event" if (ev_op == 0 or first_emitted) else ("event_and" if ev_op == 1 else "event_or")
            res_s = "BATTLE_win" if ev_res == 0 else "BATTLE_lose"
            lines.append(f"{kw:9s} = {res_s}, {ev_cond}, {ev_val}, 0")
            first_emitted = False

        if embedded_units:
            lines.append("")
            lines.append("#character.txt")
            lines.extend(embedded_units)

        rel = f"data\\mapscript\\map{m_dir:02d}\\field_{bid:04d}_{stg:03d}.txt"
        add_file(rel, ("\r\n".join(lines) + "\r\n").encode("cp932", "replace"))
        field_count += 1

    # Write char_0062.txt for battle 62 (map62)
    if map62_units:
        c62 = "\r\n".join(v for _, v in sorted(map62_units.items()))
        add_file("data\\mapscript\\map62\\char_0062.txt", c62.encode("cp932", "replace"))

    # ================================================================
    # 4. Decompile all Ruah MPD maps -> map_XXXX.txt
    # ================================================================
    mpd_cnt, mpd_u1, mpd_u2 = struct.unpack_from("<III", mpd, 4)
    map_count = 0
    for i in range(mpd_cnt):
        rec = mpd[16 + i * 688 : 16 + (i + 1) * 688]
        bid = struct.unpack_from("<H", rec, 680)[0]
        if bid not in RUAH_BIDS:
            continue
        first_a = struct.unpack_from("<H", rec, 676)[0]
        nxt_a = struct.unpack_from("<H", mpd, 16 + (i + 1) * 688 + 676)[0] if i + 1 < mpd_cnt else mpd_u1
        bgm_s = rec[32:64].split(b"\x00", 1)[0].decode("cp932", "replace") or "bgm33"

        lines = [f'bgm = "{bgm_s}"']
        for pk in range(6):
            pr = struct.unpack_from("<H", rec, 352 + pk * 2)[0]
            if pr != 0:
                lines.append(f"get_prism = {pr}")
        lines.append("")

        for ai in range(first_a, nxt_a):
            a = mpd[mpd_u2 + ai * 244 : mpd_u2 + (ai + 1) * 244]
            tname = a[0x00:0x40].split(b"\x00", 1)[0].decode("cp932", "replace")
            pname = a[0x40:0x80].split(b"\x00", 1)[0].decode("cp932", "replace")
            th = struct.unpack_from("<58H", a, 0x80)
            ax, ay = th[0], th[1]
            act_flag = th[12]
            rank = RANK_NAMES.get(th[13], "easy")
            repair = th[14]
            n_en = th[15]
            abid, astg = th[16], th[17]
            ret_adv = th[50]

            lines.append(f"area {ax}, {ay}")
            lines.append("    active_area" if act_flag == 2 else "    active")
            lines.append(f"    battle {abid}, {astg}")
            lines.append(f"    rank   {rank}")
            if repair:
                lines.append("    repair")
            if tname:
                tname_ok = resolve_tga(tname, "data/bg/MAP_NAME/MAP_BATTLENAME_06.tga")
                lines.append(f'    title_name   = "{tname_ok}"')
            if pname:
                pname_ok = resolve_tga(pname, "data/bg/MAP_BG/MAPBG_022B.tga")
                lines.append(f'    picture_name = "{pname_ok}"')
            for ei in range(min(n_en, 16)):
                eid = th[30 + ei]
                if eid < len(ENEMY_ICONS):
                    lines.append(f"    enemy {ENEMY_ICONS[eid]}")
            for ti in range(4):
                pid, cond, val = th[18 + ti * 3], th[19 + ti * 3], th[20 + ti * 3]
                if pid != 0:
                    lines.append(f"    get_prism_term = {pid}, {cond}, {val}")
            if ret_adv:
                lines.append(f"    return_adv {ret_adv}")
            lines.append("")

        n_links = struct.unpack_from("<H", rec, 666)[0]
        for li in range(n_links):
            x1, y1, x2, y2 = struct.unpack_from("<4H", rec, 364 + li * 8)
            lines.append(f"link {x1},{y1}, {x2},{y2}")

        lines.append(DEFAULT_OSUSUME)

        m_dir = bid % 100
        rel = f"data\\mapscript\\map{m_dir:02d}\\map_{bid:04d}.txt"
        add_file(rel, ("\r\n".join(lines) + "\r\n").encode("cp932", "replace"))
        map_count += 1

    # Also ensure direct-launch battles without an MPD record (1810, 1811, 2811, 3811, 1812, 2813) work cleanly
    # (P_ARK201.exe only loads map_XXXX.txt for map battles; direct battles load field_XXXX_YYY.txt directly!)

    # ================================================================
    # 5. Pack battle1.dat (PRSM) & round-trip verify every member!
    # ================================================================
    common.write_prsm_archive(BATTLE_OUT, out_files)

    # Round-trip verification of battle1.dat!
    dec_tbl, _ = common.load_prsm_tables()
    with open(BATTLE_OUT, "rb") as f:
        magic, cnt, hsz = struct.unpack("<4sII", f.read(12))
        assert magic == b"PRSM" and cnt == len(out_files)
        f.seek(0)
        hdr = bytearray(f.read(hsz))
        for i in range(12, hsz):
            hdr[i] = dec_tbl[(i % 6) * 256 + hdr[i]]
        for idx in range(cnt):
            noff, foff, fsz = struct.unpack_from("<III", hdr, 12 + idx * 12)
            rec = common.prsm_lz_decode(hdr, noff)
            nm = rec[:0x7F].split(b"\x00", 1)[0].decode("cp932", "replace")
            kb = rec[0x7F]
            usz = struct.unpack_from("<I", rec, 0x80)[0]
            assert usz == len(out_files[idx][1]) and kb == 0
            f.seek(foff)
            raw = bytearray(f.read(fsz))
            for i in range(fsz):
                raw[i] = dec_tbl[(i % 6) * 256 + raw[i]]
            dec_data = common.prsm_lz_decode(raw, 0)
            assert nm == out_files[idx][0] and dec_data == out_files[idx][1]

    print(f"\n=== Battle Port Complete & Round-Trip Verified! ===")
    print(f"  Output: {BATTLE_OUT} ({os.path.getsize(BATTLE_OUT):,} bytes)")
    print(f"  Total files packed: {len(out_files)} ({field_count} field_*.txt, {map_count} map_*.txt, char_0062.txt, prism.txt, prismlist.txt, Prism #225 TGAs/.x, BWP_RUAH01.tga)")


if __name__ == "__main__":
    main()
