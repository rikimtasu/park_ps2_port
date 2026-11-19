"""
Generate all Playable Ally Ruah (ch = 9) battle assets for battle1.dat:
  - ch_sheet.txt (appends exact PS2 CHD[8] [ルーア] growth curve into slot 8)
  - 6 battle UI TGAs (bt_v09, bt_a09, cut_09, bte_09a, bte_09b, st_e09)
  - 3D battle model data/char/character/ruah/ph2chr09.{dmo,def,cmn,tga,_face.tga}
  - 104 battle voices (B_RUA_0000..0103.ogg @ 44100 Hz mono) + common.se + random.se
"""
import io
import os
import re
import shutil
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

RUAH_SE_BASE = 2100  # 02100..02203 -> B_RUA_0000..0103.ogg

# Exact PS2 PA_FILE.DAT[315] CHD[8] ([ルーア]) growth curve
RUAH_CH_SHEET_BLOCK = """\r
\r
[ルーア]\r
\r
lpBase  = 60.0\r
lpRise  =  7.8\r
\r
tpBase  =  6.0\r
tpRise  =  3.2\r
\r
atkBase =  8.0\r
atkRise =  4.6\r
\r
defBase =  5.0\r
defRise =  4.5\r
\r
magBase =  9.0\r
magRise =  5.0\r
\r
aglBase =  7.0\r
aglRise =  3.1\r
\r
glow    =  1.47\r
exp     =  3.0\r
"""


def encode_tga(im: Image.Image, bpp: int = 32, top_down: bool = False) -> bytes:
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


def _load_font(candidates: list[str], size: int):
    font_dir = r"C:\Windows\Fonts"
    for fn in candidates:
        p = os.path.join(font_dir, fn)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _load_ruah_sprite() -> Image.Image:
    """Load Ruah's standing sprite (PA08_A_A00.epa) from staged gfx."""
    p = os.path.join(common.WORK_DIR, "staged", "gfx", "PA08_A_A00.epa")
    if not os.path.exists(p):
        raise FileNotFoundError(f"Ruah sprite not found: {p} (run port_graphics first)")
    return common.decode_epa_image(open(p, "rb").read()).convert("RGBA")


def _clean_box_horizontal_fill(arr: np.ndarray, y0: int, y1: int, x0: int, x1: int, sample_x: int):
    """Fill a rectangular text area with clean parchment pixels sampled from a clean column/region."""
    for y in range(y0, y1):
        arr[y, x0:x1] = arr[y, sample_x]


def generate_ruah_ui_tgas(read_pc_b, preview_dir: str | None = None) -> list[tuple[str, bytes]]:
    """Build all 6 Ruah battle UI TGAs matching PC Prism Ark's exact layouts & dimensions."""
    ruah = _load_ruah_sprite()  # 700x600 RGBA
    # Crop Ruah's head+shoulders (around x=140..560, y=25..310)
    ruah_head = ruah.crop((145, 30, 560, 315))
    # Crop Ruah's full standing sprite tightly
    bbox = ruah.getbbox()
    ruah_tight = ruah.crop(bbox) if bbox else ruah

    f_serif_lg = _load_font(["yumindb.ttf", "msmincho.ttc", "BIZ-UDMinchoM.ttc"], 26)
    f_serif_md = _load_font(["yumindb.ttf", "msmincho.ttc", "BIZ-UDMinchoM.ttc"], 22)
    f_serif_sm = _load_font(["yumindb.ttf", "msmincho.ttc", "timesbd.ttf"], 14)
    f_serif_st = _load_font(["yumindb.ttf", "msmincho.ttc", "BIZ-UDMinchoM.ttc"], 36)
    f_serif_st_en = _load_font(["yumindb.ttf", "timesbd.ttf", "msmincho.ttc"], 15)
    f_card = _load_font(["YuGothB.ttc", "meiryob.ttc", "BIZ-UDGothicB.ttc"], 21)

    results = []

    def emit(rel_path: str, im: Image.Image):
        results.append((rel_path, encode_tga(im, bpp=32, top_down=False)))
        if preview_dir:
            os.makedirs(preview_dir, exist_ok=True)
            im.save(os.path.join(preview_dir, os.path.basename(rel_path).replace(".tga", ".png")))

    # ------------------------------------------------------------------
    # 1. bt_v09.tga (272x160): Battle bottom portrait + parchment nameplate
    # ------------------------------------------------------------------
    btv_base = Image.open(io.BytesIO(read_pc_b("data/manabe/キャラステータス関連/キャラクター/bt_v06.tga"))).convert("RGBA")
    arr = np.array(btv_base)
    # Build clean 272x160 canvas: keep parchment strip (y=118..156) using clean light parchment column from x=12..24
    btv_out = Image.new("RGBA", (272, 160), (0, 0, 0, 0))
    # Reconstruct clean parchment bar (y=118..156) preserving left fade alpha from btv_base
    bar = np.zeros((160, 272, 4), dtype=np.uint8)
    for y in range(118, 157):
        # Clean beige parchment color from bottom-left interior of original bar
        base_rgb = np.array([232, 215, 168], dtype=np.float32)
        for x in range(272):
            a = int(arr[y, x, 3])
            if a == 0:
                continue
            # Slight warm gradient matching original parchment
            shade = 1.0 - 0.08 * ((y - 118) / 39.0) + 0.04 * np.sin(x * 0.05)
            rgb = np.clip(base_rgb * shade, 0, 255).astype(np.uint8)
            bar[y, x, :3] = rgb
            bar[y, x, 3] = a
    btv_out = Image.fromarray(bar, "RGBA")
    # Paste Ruah bust on the right side (x=122..272, y=22..160)
    bust = ruah_head.resize((166, 115), Image.Resampling.LANCZOS)
    btv_out.alpha_composite(bust, (112, 45))
    draw = ImageDraw.Draw(btv_out)
    draw.text((22, 117), "ルーア", font=f_serif_lg, fill=(45, 36, 26, 255))
    draw.text((34, 142), "R  u  a  h", font=f_serif_sm, fill=(55, 44, 32, 255))
    emit("data/manabe/キャラステータス関連/キャラクター/bt_v09.tga", btv_out)

    # ------------------------------------------------------------------
    # 2. bt_a09.tga (184x80): Battle HUD status card ("ルーア")
    # ------------------------------------------------------------------
    bta_base = Image.open(io.BytesIO(read_pc_b("data/manabe/キャラステータス関連/キャラステータス/bt_a06.tga"))).convert("RGBA")
    arr = np.array(bta_base)
    # Erase "リッテ" cleanly (y=5..25, x=28..132) using clean parchment row y=5..25 from x=13..25 (above LP!)
    patch_tile = arr[5:25, 13:25].copy()
    for x in range(28, 132, patch_tile.shape[1]):
        w = min(patch_tile.shape[1], 132 - x)
        arr[5:25, x : x + w] = patch_tile[:, :w]
    bta_out = Image.fromarray(arr, "RGBA")
    draw = ImageDraw.Draw(bta_out)
    # White text with thick warm-brown stroke matching bt_a06.tga
    draw.text(
        (36, 3),
        "ルーア",
        font=f_card,
        fill=(255, 255, 255, 255),
        stroke_width=2,
        stroke_fill=(102, 54, 16, 255),
    )
    emit("data/manabe/キャラステータス関連/キャラステータス/bt_a09.tga", bta_out)

    # ------------------------------------------------------------------
    # 3. cut_09.tga (480x800): Level-up / victory cut-in sprite
    # ------------------------------------------------------------------
    cut_out = Image.new("RGBA", (480, 800), (0, 0, 0, 0))
    # Scale Ruah standing sprite cleanly to fit 480 width (~480x440) positioned in center-upper frame
    scale = min(470.0 / ruah_tight.width, 620.0 / ruah_tight.height)
    nw, nh = int(ruah_tight.width * scale), int(ruah_tight.height * scale)
    ruah_cut = ruah_tight.resize((nw, nh), Image.Resampling.LANCZOS)
    cut_out.alpha_composite(ruah_cut, ((480 - nw) // 2, 110))
    emit("data/manabe/戦闘終了画像/cut_09.tga", cut_out)

    # ------------------------------------------------------------------
    # 4. bte_09a.tga & bte_09b.tga (800x80): Battle victory EXP bar banners
    # ------------------------------------------------------------------
    for suffix, src_name in [("a", "bte_06a.tga"), ("b", "bte_06b.tga")]:
        bte_base = Image.open(io.BytesIO(read_pc_b(f"data/manabe/戦闘終了画像/{src_name}"))).convert("RGBA")
        arr = np.array(bte_base, dtype=np.float32)
        # Smoothly blend out Filia's name & portrait with clean parchment color sampled from row edges
        parch = np.array([242.0, 229.0, 190.0], dtype=np.float32) if suffix == "a" else np.array([248.0, 236.0, 198.0], dtype=np.float32)
        # Erase Filia portrait x=112..214, y=2..78 and Filia name x=14..116, y=43..77 with smooth gradient
        for y in range(2, 78):
            gy = 1.0 - 0.08 * ((y - 2) / 76.0)
            arr[y, 112:214, :3] = parch * gy
            if y >= 43:
                arr[y, 14:116, :3] = parch * gy
        bte_out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
        # Composite Ruah head portrait in x=106..218, y=2..78
        face_crop = ruah_head.resize((114, 78), Image.Resampling.LANCZOS)
        bte_out.alpha_composite(face_crop, (108, 2))
        draw = ImageDraw.Draw(bte_out)
        draw.text((22, 42), "ルーア", font=f_serif_md, fill=(45, 36, 26, 255))
        draw.text((28, 63), "R  u  a  h", font=f_serif_sm, fill=(55, 44, 32, 255))
        emit(f"data/manabe/戦闘終了画像/bte_09{suffix}.tga", bte_out)

    # ------------------------------------------------------------------
    # 5. st_e09.tga (800x64): In-battle Status screen header
    # ------------------------------------------------------------------
    ste_base = Image.open(io.BytesIO(read_pc_b("data/campaign/ステータス/キャラ文字/st_e06.tga"))).convert("RGBA")
    arr = np.array(ste_base)
    # Erase "フィーリア FILIA" (x=130..360, y=4..44), keeping horizontal rule (y>=45) and "LV / EXP" (x>=380)
    arr[4:44, 130:360] = 0
    ste_out = Image.fromarray(arr, "RGBA")
    draw = ImageDraw.Draw(ste_out)
    draw.text((168, 6), "ルーア", font=f_serif_st, fill=(46, 38, 30, 255))
    draw.text((296, 26), "R U A H", font=f_serif_st_en, fill=(46, 38, 30, 255))
    emit("data/campaign/ステータス/キャラ文字/st_e09.tga", ste_out)

    # ------------------------------------------------------------------
    # 6. ca_b09.tga (640x640): Camp Character Sheet standing portrait
    # ------------------------------------------------------------------
    cab_out = Image.new("RGBA", (640, 640), (0, 0, 0, 0))
    sc_b = min(560.0 / ruah_tight.width, 590.0 / ruah_tight.height)
    bw, bh = int(ruah_tight.width * sc_b), int(ruah_tight.height * sc_b)
    ruah_cab = ruah_tight.resize((bw, bh), Image.Resampling.LANCZOS)
    bx, by = (640 - bw) // 2, 620 - bh
    # Soft drop shadow matching vanilla ca_b03.tga
    shad = Image.new("RGBA", (640, 640), (0, 0, 0, 0))
    s_alpha = ruah_cab.split()[3].point(lambda v: int(v * 0.45))
    shad_fg = Image.new("RGBA", (bw, bh), (28, 22, 32, 255))
    shad_fg.putalpha(s_alpha)
    shad.alpha_composite(shad_fg, (bx + 10, by + 10))
    shad = shad.filter(ImageFilter.GaussianBlur(radius=6))
    cab_out.alpha_composite(shad)
    cab_out.alpha_composite(ruah_cab, (bx, by))
    emit("data/campaign/キャラクターシート/キャラクター/ca_b09.tga", cab_out)

    # ------------------------------------------------------------------
    # 7. ca_c09.tga (400x560): Camp Character Sheet bio & class card
    # ------------------------------------------------------------------
    cac_out = Image.new("RGBA", (400, 560), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cac_out)
    serif_path = r"C:\Windows\Fonts\msmincho.ttc"
    if not os.path.exists(serif_path):
        serif_path = r"C:\Windows\Fonts\msgothic.ttc"
    fc_name = ImageFont.truetype(serif_path, 40)
    fc_en = ImageFont.truetype(serif_path, 18)
    fc_cls_l = ImageFont.truetype(serif_path, 26)
    fc_cls = ImageFont.truetype(serif_path, 36)
    fc_cls_en = ImageFont.truetype(serif_path, 13)
    fc_hdr = ImageFont.truetype(serif_path, 24)
    fc_sym = ImageFont.truetype(serif_path, 28)
    fc_body = ImageFont.truetype(serif_path, 17)

    blue = (84, 108, 168, 255)
    pink = (218, 128, 148, 255)
    # Name + horizontal bar matching ca_c03.tga
    cd.text((112, 26), "ル ー ア", font=fc_name, fill=blue)
    cd.text((110, 24), "ル ー ア", font=fc_name, fill=pink)
    cd.rectangle((18, 70, 322, 72), fill=pink)
    cd.rectangle((18, 72, 322, 74), fill=blue)
    cd.text((126, 78), "R   U   A   H", font=fc_en, fill=pink)

    # CLASS section
    cd.text((76, 124), "CLASS", font=fc_cls_l, fill=blue)
    cd.text((196, 114), "魔導騎士", font=fc_cls, fill=blue)
    cd.text((198, 152), "M A G I C  K N I G H T", font=fc_cls_en, fill=blue)

    # 攻撃 / 魔法 / 回復 ratings
    for cx, lbl, sym in [(86, "攻撃", "○"), (186, "魔法", "○"), (286, "回復", "○")]:
        cd.text((cx, 178), lbl, font=fc_hdr, fill=blue)
        cd.text((cx + 10, 208), sym, font=fc_sym, fill=blue)

    # Bio body text
    bio_lines = [
        "記憶を失いローゼンベルグ騎士養成",
        "学校へ転入してきた謎の少女。",
        "ハヤウェイに守られたことを機に、",
        "自らも戦う決意を固める。",
        "攻防・魔法・回復のバランスに優れ、",
        "専用スキル『ウーリー・ゼカルヤー』",
        "による強力な光属性魔法や自己回復で",
        "前線から後衛まで幅広く活躍する。",
    ]
    for idx_l, ln in enumerate(bio_lines):
        cd.text((54, 254 + idx_l * 24), ln, font=fc_body, fill=blue)

    emit("data/campaign/キャラクターシート/説明/ca_c09.tga", cac_out)

    return results


def _recolor_fel_body_to_ruah(im: Image.Image) -> Image.Image:
    """Recolor Fel's body texture (ph2chr03.tga) to Ruah's ash-blonde/crimson/pink/blue palette."""
    rgba = np.array(im.convert("RGBA"), dtype=np.float32)
    r, g, b, a = rgba[:, :, 0] / 255.0, rgba[:, :, 1] / 255.0, rgba[:, :, 2] / 255.0, rgba[:, :, 3]
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    sat = np.where(cmax > 1e-5, delta / np.maximum(cmax, 1e-5), 0.0)
    val = cmax

    # Compute hue in [0, 360)
    hue = np.zeros_like(r)
    nz = delta > 1e-5
    mr = nz & (cmax == r)
    mg = nz & (cmax == g) & ~mr
    mb = nz & ~mr & ~mg
    hue[mr] = (60.0 * ((g[mr] - b[mr]) / delta[mr])) % 360.0
    hue[mg] = 60.0 * ((b[mg] - r[mg]) / delta[mg]) + 120.0
    hue[mb] = 60.0 * ((r[mb] - g[mb]) / delta[mb]) + 240.0

    out = rgba.copy()
    h, w = rgba.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]

    # UV-island-aware recoloring on 256x256 ph2chr03.tga (no threshold seams!):
    # 1. Left-half burgundy dress islands (xx < 158, yy >= 88): smooth crimson-red (#C83E4D)
    mask_dress = (xx < 158) & (yy >= 88) & ((hue >= 295.0) | (hue <= 10.0)) & (sat > 0.14)
    out[:, :, 0] = np.where(mask_dress, np.clip(val * 260.0, 0, 255), out[:, :, 0])
    out[:, :, 1] = np.where(mask_dress, np.clip(val * 92.0, 0, 255), out[:, :, 1])
    out[:, :, 2] = np.where(mask_dress, np.clip(val * 110.0, 0, 255), out[:, :, 2])

    # 2. Right-half pink hair & twintail ribbons (xx >= 158, yy >= 84): warm ash-blonde (#C9AE93)
    #    (Leave the crimson bow/ornament heart at yy < 84 untouched red!)
    mask_hair = (xx >= 158) & (yy >= 84) & ((hue >= 295.0) | (hue <= 10.0)) & (sat > 0.14)
    out[:, :, 0] = np.where(mask_hair, np.clip(val * 218.0, 0, 255), out[:, :, 0])
    out[:, :, 1] = np.where(mask_hair, np.clip(val * 188.0, 0, 255), out[:, :, 1])
    out[:, :, 2] = np.where(mask_hair, np.clip(val * 160.0, 0, 255), out[:, :, 2])

    out[:, :, 3] = a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def _recolor_fel_face_to_ruah(im: Image.Image) -> Image.Image:
    """Recolor Fel's face texture (ph2chr03_face.tga): green eyes -> Ruah's deep purple, pink hair/brows -> ash-blonde."""
    rgba = np.array(im.convert("RGBA"), dtype=np.float32)
    r, g, b, a = rgba[:, :, 0] / 255.0, rgba[:, :, 1] / 255.0, rgba[:, :, 2] / 255.0, rgba[:, :, 3]
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    sat = np.where(cmax > 1e-5, delta / np.maximum(cmax, 1e-5), 0.0)
    val = cmax

    hue = np.zeros_like(r)
    nz = delta > 1e-5
    mr = nz & (cmax == r)
    mg = nz & (cmax == g) & ~mr
    mb = nz & ~mr & ~mg
    hue[mr] = (60.0 * ((g[mr] - b[mr]) / delta[mr])) % 360.0
    hue[mg] = 60.0 * ((b[mg] - r[mg]) / delta[mg]) + 120.0
    hue[mb] = 60.0 * ((r[mb] - g[mb]) / delta[mb]) + 240.0

    out = rgba.copy()
    # 1. Green irises (hue 80..170, sat > 0.25) -> Ruah's violet-purple eyes (#7B4E80)
    mask_eye = (hue >= 80.0) & (hue <= 170.0) & (sat > 0.25)
    out[:, :, 0] = np.where(mask_eye, np.clip(val * 175.0, 0, 255), out[:, :, 0])
    out[:, :, 1] = np.where(mask_eye, np.clip(val * 105.0, 0, 255), out[:, :, 1])
    out[:, :, 2] = np.where(mask_eye, np.clip(val * 185.0, 0, 255), out[:, :, 2])

    # 2. Pink eyebrows & top hair tabs (hue 285..345, sat > 0.18, y < 60) -> ash-blonde
    yy = np.arange(rgba.shape[0])[:, None]
    mask_brow = (yy < 60) & (hue >= 285.0) & (hue <= 345.0) & (sat > 0.18)
    out[:, :, 0] = np.where(mask_brow, np.clip(val * 205.0, 0, 255), out[:, :, 0])
    out[:, :, 1] = np.where(mask_brow, np.clip(val * 175.0, 0, 255), out[:, :, 1])
    out[:, :, 2] = np.where(mask_brow, np.clip(val * 148.0, 0, 255), out[:, :, 2])

    out[:, :, 3] = a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def generate_ruah_3d_model(read_pc_b, preview_dir: str | None = None) -> list[tuple[str, bytes]]:
    """
    Build Ruah's playable 3D battle model at data/char/character/ruah/ph2chr09.*
    by cloning Fel (ph2chr03 — twintails + ribbons + 243 animations), recoloring textures
    to Ruah's palette, and remapping all Fel voice IDs in .def to Ruah's voices.
    """
    fel_dmo = read_pc_b("data/char/character/fel/ph2chr03.dmo")
    fel_cmn = read_pc_b("data/char/character/fel/ph2chr03.cmn")
    fel_def = read_pc_b("data/char/character/fel/ph2chr03.def").decode("cp932", "replace")
    fel_tga = Image.open(io.BytesIO(read_pc_b("data/char/character/fel/ph2chr03.tga")))
    fel_face = Image.open(io.BytesIO(read_pc_b("data/char/character/fel/ph2chr03_face.tga")))

    # Same-length replacement keeps all DirectX .dmo offsets/structure intact!
    ruah_dmo = fel_dmo.replace(b"ph2chr03.tga", b"ph2chr09.tga").replace(b"ph2chr03_face.tga", b"ph2chr09_face.tga")

    # Remap Fel voice calls in .def -> Ruah voice groups & SE IDs:
    #   EVENT_RANDOM_SOUND:X:00031: -> 00090 (Ruah attacks)
    #   EVENT_RANDOM_SOUND:X:00032: -> 00091 (Ruah defense/backstep)
    #   EVENT_RANDOM_SOUND:X:01003: -> 01009 (Ruah damage)
    #   EVENT_SOUND:X:006xx..007xx: -> Ruah attack/skill voices (02100..02115)
    def _remap_def_line(line: str) -> str:
        line = re.sub(r"(EVENT_RANDOM_SOUND:\d+:)0*31(:)", r"\g<1>00090\2", line)
        line = re.sub(r"(EVENT_RANDOM_SOUND:\d+:)0*32(:)", r"\g<1>00091\2", line)
        line = re.sub(r"(EVENT_RANDOM_SOUND:\d+:)0*1003(:)", r"\g<1>01009\2", line)

        def _repl_se(m):
            sid = int(m.group(2))
            if 600 <= sid <= 799:
                # Map Fel's direct voice IDs deterministically to Ruah's attack/skill shouts (2100..2115)
                new_id = RUAH_SE_BASE + (sid % 16)
                return f"{m.group(1)}{new_id:05d}{m.group(3)}"
            return m.group(0)

        line = re.sub(r"(EVENT_SOUND:\d+:)(\d+)(:)", _repl_se, line)
        return line

    ruah_def = "\r\n".join(_remap_def_line(l) for l in fel_def.splitlines()) + "\r\n"

    ruah_body_im = _recolor_fel_body_to_ruah(fel_tga)
    ruah_face_im = _recolor_fel_face_to_ruah(fel_face)

    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        ruah_body_im.save(os.path.join(preview_dir, "ph2chr09.png"))
        ruah_face_im.save(os.path.join(preview_dir, "ph2chr09_face.png"))

    # Match original TGA format (32bpp bottom-up)
    body_tga = encode_tga(ruah_body_im, bpp=32, top_down=False)
    face_tga = encode_tga(ruah_face_im, bpp=32, top_down=False)

    return [
        ("data/char/character/ruah/ph2chr09.dmo", ruah_dmo),
        ("data/char/character/ruah/ph2chr09.cmn", fel_cmn),
        ("data/char/character/ruah/ph2chr09.def", ruah_def.encode("cp932", "replace")),
        ("data/char/character/ruah/ph2chr09.tga", body_tga),
        ("data/char/character/ruah/ph2chr09_face.tga", face_tga),
    ]


def convert_ruah_battle_voices(iso: common.IsoReader) -> list[tuple[str, bytes]]:
    """
    Extract & transcode all 104 PS2 Ruah battle voices (b_rua_0000.adx..b_rua_0103.adx)
    from PA_SE.DAT to 44100 Hz mono OGG Vorbis (cached in staged/se_ruah_v2/).

    Note: PA_SE.DAT has 2,767 FLK entries: [0..1017] are stereo ADV SEs, [1018..2765] are the
    1,748 mono battle SEs/voices matching the 1,748 non-empty lines of PA_SE.DAT[2766].
    """
    cache_dir = os.path.join(common.WORK_DIR, "staged", "se_ruah_v2")
    os.makedirs(cache_dir, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH (required for battle voice transcoding)")

    _, entries = iso.get_flk_table("PA_SE.DAT")
    raw_list = iso.read_flk_entry("PA_SE.DAT", len(entries) - 1)
    if raw_list[:4] == b"ZZZ\x00":
        raw_list = common.decompress_zzz(raw_list)
    non_empty = [l.strip() for l in raw_list.decode("cp932", "replace").splitlines() if l.strip()]
    battle_se_offset = (len(entries) - 1) - len(non_empty)
    assert battle_se_offset == 1018, f"Unexpected PA_SE.DAT battle SE offset: {battle_se_offset}"

    rua_entries = [
        (battle_se_offset + k, n)
        for k, n in enumerate(non_empty)
        if n.lower().startswith("b_rua_")
    ]
    assert len(rua_entries) == 104, f"Expected 104 Ruah battle voices, found {len(rua_entries)}"
    assert rua_entries[0][0] == 2662 and rua_entries[-1][0] == 2765

    # Extract uncached ADX payloads sequentially from ISO, then transcode in parallel
    to_convert = []
    out_names = []
    for idx, nm in rua_entries:
        stem = os.path.splitext(nm)[0].upper()  # B_RUA_0000
        ogg_path = os.path.join(cache_dir, stem + ".ogg")
        out_names.append((stem, ogg_path))
        if not os.path.exists(ogg_path):
            raw_adx = iso.read_flk_entry("PA_SE.DAT", idx)
            to_convert.append((stem, raw_adx, ogg_path))

    if to_convert:
        print(f"Transcoding {len(to_convert)} Ruah battle voices (44100 Hz mono OGG) ...")

        def _conv(item):
            stem, raw_adx, ogg_path = item
            tmp_adx = ogg_path + ".adx"
            with open(tmp_adx, "wb") as f:
                f.write(raw_adx)
            try:
                cmd = [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", tmp_adx,
                    "-ar", "44100", "-ac", "1",
                    "-c:a", "libvorbis", "-q:a", "4",
                    ogg_path,
                ]
                subprocess.run(cmd, check=True)
            finally:
                if os.path.exists(tmp_adx):
                    os.remove(tmp_adx)

        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
            list(ex.map(_conv, to_convert))

    files = []
    for stem, ogg_path in out_names:
        with open(ogg_path, "rb") as f:
            files.append((f"data/se/{stem}.ogg", f.read()))
    return files


def build_ruah_common_se(orig_common_se: str) -> bytes:
    """Append Ruah's 104 battle voice IDs (02100..02203) to data/se/common.se."""
    lines = ["", "// ルーアボイス (Prism Ark Awake)"]
    for i in range(104):
        sid = RUAH_SE_BASE + i
        lines.append(f"    {sid:05d}        data/se/B_RUA_{i:04d}.ogg        (5.0 0 0.0 1)")
    return (orig_common_se.rstrip("\r\n") + "\r\n" + "\r\n".join(lines) + "\r\n").encode("cp932", "replace")


def build_ruah_random_se(orig_random_se: str) -> bytes:
    """Append all Ruah (ch = 9) battle voice groups to data/se/random.se."""
    b = RUAH_SE_BASE
    # Map B_RUA_0000..0103 following Pajama Soft's standard battle voice numbering (matching B_TER)
    lines = [
        "",
        "// ===== ルーア (ch=9) バトルボイス =====",
        f"00090,  {b+0},{b+1},{b+2},{b+3},{b+4},{b+5},{b+6},{b+7},{b+8},{b+9}",
        f"00091,  {b+34},{b+36}",
        f"01009,  {b+27},{b+28},{b+29},{b+30},{b+31}",
        # Victory (10009), KO (10109), Pinch (10209), Self-heal (10309), Start (10409), Level-up (10509)
        f"10009,  {b+49},{b+50},{b+51},{b+52},{b+56},{b+57},{b+58},{b+59},{b+62},{b+63},{b+64},{b+65}",
        f"10109,  {b+32},{b+33}",
        f"10209,  {b+26}",
        f"10309,  {b+3},{b+9},{b+45}",
        f"10409,  {b+45},{b+46},{b+47},{b+48}",
        f"10509,  {b+44}",
    ]
    # Ruah covers allies 0..8 (11900..11908)
    for tgt in range(9):
        lines.append(f"{11900 + tgt},  {b+37},{b+38},{b+39},{b+40}")
    # Allies 0..8 cover Ruah (11009..11809) using each ally's standard cover voices
    ally_cover = {
        0: "79, 87",
        1: "250",
        2: "456, 457, 458, 459",
        3: "678",
        4: "855, 856, 857, 858",
        5: "1048, 1049, 1050, 1052",
        6: "1278",
        7: "1436",
        8: "1027, 1051",
    }
    for act, vids in ally_cover.items():
        lines.append(f"{11000 + act * 100 + 9},  {vids}")

    # Ruah is covered by allies 0..8 (12900..12908)
    for cov in range(9):
        lines.append(f"{12900 + cov},  {b+41},{b+42},{b+43}")
    # Allies 0..8 are covered by Ruah (12009..12809)
    ally_covered = {
        0: "63, 64, 65",
        1: "251, 252",
        2: "461, 462",
        3: "662, 680",
        4: "860, 861",
        5: "1043",
        6: "1279, 1280, 1281",
        7: "1420",
        8: "1053, 1054, 1055",
    }
    for act, vids in ally_covered.items():
        lines.append(f"{12000 + act * 100 + 9},  {vids}")

    # Allies 0..8 heal Ruah (13900..13908)
    for hl in range(9):
        lines.append(f"{13900 + hl},  {b+21},{b+22},{b+23},{b+24}")
    # Ruah heals allies 0..8 (13009..13809)
    ally_healed = {
        0: "63, 64, 65",
        1: "228, 230",
        2: "440, 441",
        3: "662, 663, 665",
        4: "839, 840, 841, 842",
        5: "1043",
        6: "1262, 1263, 1264",
        7: "1420, 1423",
        8: "1028, 1029, 1030, 1031, 1032",
    }
    for tgt, vids in ally_healed.items():
        lines.append(f"{13000 + tgt * 100 + 9},  {vids}")

    return (orig_random_se.rstrip("\r\n") + "\r\n" + "\r\n".join(lines) + "\r\n").encode("cp932", "replace")


def build_ruah_ch_sheet(orig_ch_sheet: str) -> bytes:
    """Append PS2 CHD[8] [ルーア] growth curve as slot 8 of ch_sheet.txt."""
    return (orig_ch_sheet.rstrip("\r\n") + RUAH_CH_SHEET_BLOCK).encode("cp932", "replace")
