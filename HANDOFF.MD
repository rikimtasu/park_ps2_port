# Handoff Guide — *Prism Ark - Awake* (PS2) PC CG Port

This document captures the reverse-engineered formats, build pipeline, current state, and open tasks so other contributors can inspect, test, or extend this port without re-discovering the internals.

---

## 1. Repository Layout

- `Prism_Ark_Awake_PC_CG.xdelta` — `xdelta3` v3.2.2 patch (`53,209,517` bytes) targeting `Prism Ark - Awake (Japan).iso` (`SLPM-66846`).
- `README.md` — End-user patch instructions and SHA-256 verification checksums.
- `src/port_cgs.py` — Main Python (`PIL`, `numpy`, `ctypes`) converter and `PA_CG.DAT` rebuilder.
- `src/zzz_helper.c` — C library implementing PS2 `ZZZ\0` decompression/compression, PC `EPA` (`mode 0/1/2/3`) decompression, and 4D RGBA Median-Cut + Floyd-Steinberg quantization (`quantize_rgba_fs`).

---

## 2. How to Rebuild `PA_CG_NEW.DAT` & the Patched ISO

### Prerequisites
- Python 3.10+ with `pillow` and `numpy`
- C compiler (`gcc` via MSYS2/MinGW-w64 on Windows, or `gcc` on Linux)
- `7z` (for extracting `PA_CG.DAT` from the retail PS2 ISO)
- [xdelta3 v3.2.2](https://github.com/jmacd/xdelta/releases/tag/v3.2.2)

### Steps
1. Compile `src/zzz_helper.c`:
   ```bash
   gcc -O3 -shared -o src/zzz_helper.dll src/zzz_helper.c
   ```
2. Extract `PA_CG.DAT` from the retail PS2 ISO into an extraction folder (e.g. `_ps2_extract/`).
3. Run `src/port_cgs.py` pointing to the PC game folder (containing `archive.dat`, `archive1.dat`, `archive2.dat`) and the extracted `PA_CG.DAT`:
   ```bash
   python src/port_cgs.py --pc-dir "/path/to/pc/p_ark" --ps2-dir "./_ps2_extract" --dll "./src/zzz_helper.dll"
   ```
   This writes `_ps2_extract/PA_CG_NEW.DAT` (`518,793,216` bytes exact, zero-padded from `518,766,592` used bytes).
4. Inject `PA_CG_NEW.DAT` back into a copy of the PS2 ISO at `PA_CG.DAT`'s exact byte offset (**LBA `432995` × `2048` = `0x34db1800`**).
   - Because `PA_CG_NEW.DAT` stays `<= 518,793,216` bytes (`0x1eec2800`), ISO9660 and UDF directory tables do **not** need modification (`PA_VOI.DAT` follows immediately at LBA `686312`).
5. Generate an `xdelta3` v3.2.2 patch:
   ```bash
   xdelta3 -f -9 -e -s "Prism Ark - Awake (Japan).iso" "Prism Ark - Awake (Japan) [PC_CG].iso" Prism_Ark_Awake_PC_CG.xdelta
   ```

---

## 3. Reverse-Engineered Formats

### PS2 `PA_CG.DAT` (`AFS` + `FLK`)
- `0x000..0x800`: `AFS\0` wrapper (`count = 1`, entry `(0x800, 0x1eec3000)`).
- `0x800..0x820`: `FLK\0` header (`<4s7I`: `magic, ver=0x100100, 0, 0, 0x10, fsz=0x1eec2800, count=3810, flags=0`).
- `0x820..`: `3810` `<II` `(offset, size)` pairs.
  - **Important**: All `FLK` offsets are relative to byte `0` of `PA_CG.DAT` (not `0x800`), aligned to `0x800`, starting at `0x8000`.
  - Entries `0..3808` are assets (`3646` `ZZZ\0`, `21` uncompressed `PAG\0`, `142` `PXG\0`).
  - Entry `[3809]` is the newline-delimited asset filename index (currently at `0x1eea3800` in retail, packed sequentially after `[3808]` in `PA_CG_NEW.DAT`).
  - `SLPM_668.46` parses the `FLK` header/table dynamically at runtime.

### PS2 `ZZZ\0` Compression (from `SLPM_668.46` `0x15b628..0x15ba68`)
- 48-byte `v1` header (`magic = 'ZZZ\0'`, `ver = 1`, `out_len` at `+8`, followed by offsets/sizes for flag bits, nibbles, literals, and opcodes).
- `compress_zzz` in `src/zzz_helper.c` implements RLE (`0xc0`) and LZ77 (`0x80`, `0x40`, `0x20`, `0x00`+nibble) compression, achieving ~1.005x–1.011x of original `ZZZ` size.
- `decompress_zzz` also supports quad-literal (`0x10`) and nibble-delta opcodes (`0xc0|0x10`, `0xc0|0x20`), which `compress_zzz` does not currently emit.

### PS2 `PAG\0`, `TIM2`, and `PTL\0`
- `PAG\0` header: `<4s6I` (`magic, ver, cnt, u1, u2, hdr_off=0x64, ftr_off`); entry name at `0x64:0x84`.
- Footer at `ftr_off`: `cnt` records of **44 bytes** (`<32sIIHH`: `epa_name, tpos, unk, pc_w, pc_h`). Skip `tpos == 0` and `mouse_on_se.epa` (`TEX\0`).
- `TIM2`: `clut_type = 3` (RGBA32), `img_type = 5` (8-bit indexed), `hdr_sz = 48`, `clut_sz = 1024`.
- `PTL\0` (tiled textures for large images): `<4sBBBBIIII` (`magic, ttype, cols, rows, n_tiles, tw, th, pw, ph`) followed at `+0x20` by `n_tiles × 20`-byte tile descriptors (`<HHHHHHII`: `tx, ty, aw, ah, bw, bh, px_off, clut_off`).
  - Note: `clut_off` is **not** always `0x80`; target CG entries use both `0x80` and `0x100` (and other `PA_CG.DAT` FX entries use `0x200`). Always write CLUTs to `tpos + clut_off`.
- **CLUT Swizzle (PS2 CSM1)**: `j = (i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)` (self-inverse).
- **PS2 GS Alpha**: `0..0x80` (`(alpha_255 * 128 + 127) // 255`). Inactive 8px padding margins must use `alpha = 0` (index `0` = `[0,0,0,0]`). Two untouched FX entries (`[1014] PC11_MAGIC_MAIN`, `[1015] PC11_MAGIC_MAIN2`) originally contain alpha values up to `253`; all modified layers are verified `<= 0x80`.

### PC Archives (`GAMEDAT PAC2`, `.epa`)
- `archive.dat`, `archive1.dat`, `archive2.dat`: `12B` header + `uint32 count` + `count × 32B` cp932 names + `count × 8B (offset, size)` pairs + `data_base`.
- `.epa` (`EP\x01\x01`): `<4sIII` (`magic, mode, w, h`), planar BGR (`mode = 1`), BGRA (`mode = 2`), or 8-bit indexed (`mode = 0` with `0x300`-byte BGR palette). `mode = 4` (used by `PA*` sprites in `archive2.dat`) is not decoded.
- PS2 scales PC coordinates by **`(0.8, 0.75)`** (`800×600` -> `640×450`, padded to multiples of 8 such as `640×456`). Always scale transparent layers using `(round(pc_w * 0.8), round(pc_h * 0.75))` inside `(bw, bh)` rather than stretching into PS2's active alpha bounding box.

---

## 4. Current Scope & Special Cases Already Handled

`src/port_cgs.py` currently patches **311 `PAG` containers / 495 texture layers**:
- All matching `PG*` event CGs, `*MEMORY*`/`*BUST*` CGs (`EPA` mode `0/1/2`), and censored chibi event CGs (`PK05_6_03*`, `PK08_3_09*`).
- Quantization uses Pillow `MEDIANCUT` + Floyd-Steinberg for purely opaque/padded layers (`alpha` in `{0, 255}`), and C `quantize_rgba_fs` (separate opaque vs semi-transparent variance-weighted Median-Cut + 4D Floyd-Steinberg with PS2 GS `0..128` alpha snapping) for layers with `0 < alpha < 255` (replacing Pillow's `FASTOCTREE` RGBA which ignored dithering and collapsed semi-transparent animation/glow layers to 8–46 colors).
- Special PS2 layout/crop remappings handled in `build_special_image`:
  - `PG04_0_01_kyara1.epa` & `PG04_0_01_kyara2.epa` (`[1209]`, `[1211]`, `[1212]`): PS2 rearranged characters horizontally across `785×450` (Ritte+Bridget moved left in `kyara2`, Filia moved from `kyara2` left segment behind Kagura+Pria in `kyara1`).
  - `PG09_6_00_BACK.EPA`, `PG09_6_00_RITTE.EPA`, `PG09_6_00_MAIN` (`[1235]`, `[1236]`, `[1237]`): Top `800×600` crop of taller PC layers (`1172`/`1402`) and composite for `pg09_6_00.epa`.
  - `PGIN_7_03AS` (`[1350]`): Splits PC `PGIN_7_03L.epa` (`1600×1200`) into left/right `800×1200` halves for `pgin_7_03l1.epa` and `pgin_7_03l2.epa` (`640×900`), plus `pgin_7_03ll.epa` (`640×914`).
  - `PG12_3_02L` & `PG12_3_02BKL` (`[1272]`, `[1274]`): Scaled to `(640, 740)` inside `640×744` so the lower body is not clipped by PS2's original `~0.87x` zoom crop.
  - `PG13_0_CAP01..03` (`[1294]`, `[1297]`): Center-cropped PC `820×620` shake canvas to `800×600` (`640×450`).
  - Preserved untouched: `PG10_3_00_MAIN` (`[1241]`, already uncensored on PS2), `PG01_1_00SHIBUKI.EPA` (`[1168]`, scroll-width water splash overlay), `pg01_1_00screen.epa` (`[1168]`, PC `mode=1` opaque RGB vs PS2 `251`-step alpha screen overlay), `white.epa`, `black.epa`, `mouse_on_se.epa`, `fl_*.epa`.

---

## 5. Known Gaps & Next Things to Work On

1. **In-Game Runtime Verification (PCSX2 / Real Hardware)**
   - **Important**: All validation so far has been structural (`FLK`/`ZZZ`/`PAG`/`TIM2`/`PTL` round-trip verification across all 3,810 entries, ISO LBA byte comparison, `xdelta3 -d` verification) and visual PNG inspection of re-decoded assets. **The patched ISO has not yet been playtested in PCSX2 or on PS2 hardware.**
   - Priority scenes to test in-game:
     - `PG04_0_01_MAIN` (`[1209]`, `[1211]`, `[1212]`) scroll/layer overlap.
     - `PGIN_7_03AS` (`[1350]`) panned close-up sequence.
     - `PG12_3_02L` (`[1274]`) / `PG12_3_02BKL` (`[1272]`) vertical scroll alignment.
     - `PG13_3_00*` (`[1311]`–`[1314]`): Currently uses PC's full uncropped `800×600` (`640×450`) and `1600×1200` (`1280×900`) instead of PS2's `~1.25×` zoomed crop. Verify whether any camera pan script around `[1313] PG13_3_00AL_AS` expects the zoomed crop.
     - `TIM2`/`PTL` GS alpha blending brightness on semi-transparent edges/overlays (`0x80` peak alpha).
2. **`EPA mode 4` Support**
   - `[54] ED_6_MEMORY02` and `[984] PC11_6_MEMORY_PA06_A_A00U` use `pa06a_ua00.epa` / `pa06a_ueyea00.epa` stored as `mode = 4` in PC `archive2.dat`, so they were skipped cleanly. Implementing `mode = 4` decoding in `src/zzz_helper.c` would allow porting those two as well if desired.
3. **Exhaustive Audit of Remaining Categories**
   - `PXG` (`142` `PA*` standing sprites): Spot-checked `_U` variants (`_U` = upper-body zoom, not underwear edits), not exhaustively diffed across all 142 entries.
   - `PK*` remaining non-censored diffs (mostly sound-effect `mozi*` overlays / bounding box trims), `ED_*` ending credit vignettes, `PB*` backgrounds (note some differ purely for night/mood darkening), and `PC*` battle FX were intentionally left alone unless listed above.
4. **Tooling Convenience**
   - Add direct Python ISO patching and LBA lookup to `src/port_cgs.py` (removing manual `7z` extraction + `0x34db1800` injection) and cross-platform build support (`.so` loading on Linux/macOS).
