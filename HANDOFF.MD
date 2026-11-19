# Handoff Guide — *Prism Ark - Awake* (PS2 ↔ PC Porting Repository)

This repository contains two related projects built from retail *Prism Ark* (`P_ARK201.exe`) and *Prism Ark - Awake* (`SLPM-66846`, PS2):
1. **Part A (`src/pc_port/`, active)**: Non-destructive PC port mod (`pc_ruah_mod/`, `P_ARK201_Ruah.exe`) bringing the PS2-exclusive **Ruah (`ルーア`) Route**, **Playable Ally Ruah (`ch = 9`)**, **14 PS2 battles**, **Ruah's official PS2 3D battle model/animations/voices**, and **Omake Gallery/Music/Movie additions** into the original PC game without modifying any vanilla PC archive or executable.
2. **Part B (`src/port_cgs.py`)**: PS2 ISO patcher (`Prism_Ark_Awake_PC_CG.xdelta`) porting uncensored PC event CGs back into `PA_CG.DAT` inside `Prism Ark - Awake (Japan).iso`.

---

# Part A — Non-Destructive PC Port Mod (`src/pc_port/` → `pc_ruah_mod/`)

## A.1 Pipeline & File Layout (`src/pc_port/`)

Build order & responsibilities:
- `src/pc_port/common.py` — Shared ISO (`IsoReader`), `ZZZ\0` / `TIM2` / `PTL\0` decoders, `EPA` encoder/decoder, `GAMEDAT PAC2` writer, `PRSM` encryptor/writer, `textdata.bin` cryptor, and `zzz_helper.dll` loader.
- `src/pc_port/port_audio.py` — Extracts PS2 `PA_BGM`, `PA_SE`, and `PA_VOI` (`ADX` → `44100 Hz` OGG Vorbis via `ffmpeg`) and delegates movie conversion to `awake_movies.py`. `--movies-only` converts the selected movies without rebuilding audio.
- `src/pc_port/awake_movies.py` — Converts `PA_MOV.DAT[13]` (Awake OP1) to `exp/POP23.DAT`, `[14]` (Awake OP2) to `exp/POP24.DAT`, and `[16]` (Ruah ED2) to `exp/POP22.DAT`. All three use `800×600` MPEG-1 video and 44.1kHz stereo MP2 audio. Hooks startup at `scenario.dat+0x1C8` and the title screen at `+0x4EC`, `+0x770`, and `+0x74C`; local variables `0x100003D9` and `0x100003DA` hold the wait counter and next movie index.
- `src/pc_port/port_graphics.py` — Extracts/upscales (`640×480` → `800×600`, `640×450` → `800×600` etc.) PS2 CGs, `PA08_*` Ruah sprites,Prism #225, `0.75s` UI plates, and camp/battle loading assets (`TIM2`/`PTL`/`PAG`) to PC `.epa` / `.anm`.
- `src/pc_port/omake_assets.py` — Builds expanded Omake plates (`sys_oc_base04/07/08/09c.EPA`, `sys_ov_base01.EPA`, `sys_m_base4.EPA`, `sys_m_files05.EPA`) and 24 `graphic.bin` thumbnail/button entries. Awake replay buttons use footer group 5, slots 2–3, so the existing enable/cleanup code handles them without increasing the movie grid beyond 20 slots.
- `src/pc_port/port_scripts.py` — Decompiles/translates PS2 `PA_FILE.DAT` event scripts & choice opcodes to PC `scenario.dat`, `textdata.bin`, `filename.dat`, `graphic.bin`, `BGM.ini`, hooking the 15 Master Dispatcher entry points + 10 Omake hooks, and packs `ruah_mod.dat`.
- `src/pc_port/ps2_model_conv.py` — Converts Ruah's official PS2 `PA_BTL.DAT[67]` (`00_LUAH_ph2chr09.def` inner `FLK`: `MDP` skeletal mesh, 3 `TIM2` textures, `DEF`) and 611-entry motion bank `PA_BTL.DAT[108..719]` (59 unique `MOT\x00` clips) into PC `data/char/character/ruah/ph2chr09.{dmo,def,cmn,tga,_face.tga,_hair.tga}`.
- `src/pc_port/ruah_battle_assets.py` — Generates `ch_sheet.txt` (`[ルーア]`), `animelist.txt` (`20000..20002`), 8 battle/camp UI `.tga`s (`bt_v09`, `bt_a09`, `cut_09`, `bte_09a`, `bte_09b`, `st_e09`, `ca_b09`, `ca_c09`), 104 battle voice `.ogg`s (`B_RUA_0000..0103.ogg` at `44100 Hz` mono), `common.se`, and `random.se`.
- `src/pc_port/port_battles.py` — Decompiles PS2 `FED`/`MCD`/`MPD` (`PA_FILE.DAT[318..320]`) for all 14 Ruah battles (`62, 808, 809, 810, 1810, 811, 1811, 2811, 3811, 812, 1812, 813, 1813, 2813`), embeds official PS2 loading screens (`PA_FILE.DAT[525, 497, 474, 475]`), `prism.txt` (`PR = 225`, `5000..5008`), `prismlist.txt`, and writes `pc_ruah_mod/battle1.dat`.
- `src/pc_port/patch_exe.py` — Appends a `16 KB` RWX `.ruah` PE section (`VA 0x0087A000`) to a copy of UPX-packed `P_ARK201.exe`, writes `pc_ruah_mod/P_ARK201_Ruah.exe` (`647,168` bytes), and applies 62 runtime byte patches + trampolines (`_ruah_init` at `0x0087A000` after UPX decompression at `0x008778B3` before `OEP 0x004EA43A`).
- `src/pc_port/build_mod.py` — Master rebuild + `archive.ini` generator + install helper.
- `src/pc_port/make_test_saves.py` — Builds isolated battle & Ruah-route test saves (`save005..save008.sav` + `thumb005..thumb008.gra`) with per-save EXP floor `30000` (`LV 40`) in `var[0x100003DC]` (`0x3E44` in save -> `0x0057593C` in battle RAM).
- `src/pc_port/verify_mod.py` — 7-suite offline verifier covering non-destructive isolation, `archive.ini` VFS mount order, EPAs/ANMs/OGGs/`graphic.bin`, all `196,685` ported `scenario.dat` instructions + `0x43fda1` linear scan, codecs and durations for `exp/POP22.DAT` through `exp/POP24.DAT`, `battle1.dat` (`PRSM` decrypt + battle script/3D model/voice checks), and `P_ARK201_Ruah.exe` boot simulation (`62` patches).

For an existing staged build, opening work requires `port_scripts.py` → `port_graphics.py` → `port_audio.py --movies-only` → `build_mod.py --verify --install`. Set `PRISM_ARK_ISO` and `PRISM_ARK_PC_DIR` for the individual converters. The README has the commands; a clean checkout requires the full `build_mod.py --all` pipeline first.

### Output Package (`pc_ruah_mod/`)
- `P_ARK201_Ruah.exe` (`647,168` B) — Patched launcher; original `P_ARK201.exe` is untouched.
- `archive.ini` — Prepends `ruah_mod.dat` and `ruah_voice.dat` before vanilla `archive*.dat` / `bgm.dat` / `se.dat` / `voice*.dat`.
- `ruah_mod.dat` (`299,593,237` B, `1,465` entries), `ruah_voice.dat` (`287,065,100` B, `9,156` entries), `battle1.dat` (`30,286,479` B, `186` entries, mounted automatically by `P_ARK201.exe`).
- Movies: `exp/POP22.DAT` (Ruah ED2, `160,178,176` B), `exp/POP23.DAT` (Awake OP1, `115,877,888` B), `exp/POP24.DAT` (Awake OP2, `94,109,696` B).
- `test_saves/save005..save008.sav` & `thumb005..thumb008.gra`.

## A.2 Reverse-Engineered PC Engine & Mod Internals

- **Sys Crash Guards (`patch_exe.py`)**:
  - `tramp_free_script_objs` (`0x00447730`) & `tramp_move_sprite_guard` (`0x00463290`): Guards `0x04000102(-1)` systemic layer handle dereferences (`0x0045EC66`) and invalid sprite handle crashes (`0x004632BE`) across PS2 scripts.
  - `tramp_exp_snap` (`0x0040E3D0`): Enforces per-save EXP floor from unused local `var[0x100003DC]` (`save+0x3E44`, battle RAM `0x0057593C`) without altering character stat base `0x35DC`.
- **Playable Ally Ruah (`ch = 9`) & Enemy Boss (`ch = 171`)**:
  - `P_ARK201_Ruah.exe` enables `ch = 9` in camp UI, character sheet (`ca_b09.tga` / `ca_c09.tga`), status (`st_e09.tga`), battle (`bt_v09`, `bt_a09`, `cut_09`, `bte_09a`, `bte_09b`), and damage/attack voice dispatch (`00090`, `00091`, `01009`, `02100..02203`).
  - Enemy boss Ruah (`3811`, `1812`) remaps to `ch = 171` while sharing Ruah's `ph2chr09.dmo` model template.
- **PC `.dmo` Binary Format (verified against `0x0048CB10` in `P_ARK201.exe`)**:
  - Header (`28` B): `<4sfIfIII` -> `b"DMO "`, `version = 1.01`, `u1 = 1`, `fps = 60.0`, `n_mesh`, `n_xfiles`, `n_bone`.
  - Followed by `n_mesh + n_bone` node records (`0x14C` = `332` bytes each): `char[256] name`, `i32 parent`, `3f pos`, `3f rot`, `3f scl`, `3f piv`, `3f off2`, `i32 x_sz`, `i32 n_mot`, `i32 ntype`.
  - If `ntype == 0` and `x_sz > 0`, standard ASCII DirectX `.X` file (`xof 0303txt 0032`) follows immediately (parsed by `D3DXLoadSkinMeshFromXof` at `0x49AE80`). Textures inside `TextureFilename` are loaded relative to `.dmo`'s directory (`data\char\character\ruah\`).
  - Followed per node by `n_mot` motion tracks: `0x12C` header (`char[256] clip_name`, `i32 n_frames`, `u32 flags`, `0x24` padding) + `n_frames * ((12 if flags&1) + (12 if flags&2) + (12 if flags&4))` bytes (`pos XYZ`, `rot RX RY RZ` in radians for `Rz(rz)·Rx(rx)·Ry(ry)·T(pos)`).
- **PS2 `MDP` + `MOT` + `DEF` Format (`PA_BTL.DAT[67]` / `[108..719]`)**:
  - `MDP\x00`: `n_nodes` `0xF0`-byte bone nodes (`+0x28` parent, `+0x40` bind pos) + final `skin_object` pointing to `cmd_all` (`+0xA0`) and `table2` (`+0xA8`: `0x30`-byte chunk descriptors `[vif_o, vif_sz, cmd_o, cmd_sz, p1, p2, p3, p4, u8, cnt2, u10, u11]`).
  - Coordinate conversion PS2 `(px, py, pz)` (cm, Z-up, RH) → DirectX LH bind-pose (100:1 m): `(-px/100, +pz/100, -py/100)`, outward normals `(nz, nx, -ny)`, with double-sided faces matching PC cloth/hair conventions.
  - `MOT\x00`: 60 Hz sparse quaternion (`<I4f`) + position (`<I3f`) keyframes per bone (`M_col = T·R`), conjugated by `Cz = diag(1, 1, -1, 1)` and decomposed to PC `Rz·Rx·Ry` Euler tracks (`<= 3.4e-6` error). Note: PS2 `DEF` event timestamps ran at 30 Hz (`2×` to convert to PC 60 Hz `.def` frame numbers), whereas `MOT` keyframe times and `DEF` `tot_f` are already 60 Hz.

## A.3 Current Verification & Open Testing Items

- **Opening playback**: Launch `P_ARK201_Ruah.exe` to play Awake OP1 after the publisher logo. After 30 seconds at the title screen, the rotation is Awake OP2 → Original PC OP1 (`POP00.DAT`) → Original PC OP2 (`POP07.DAT`) → Awake OP1, then repeats. Each movie returns to the title screen for another 30-second wait. Recreating the title buttons resets the wait; movie index advances before playback, so skipping a movie advances the sequence too. OMAKE → MOVIE THEATER also has Awake OP1 and Awake OP2 replay buttons below the grid.
- **Opening checks**: `python -m unittest discover -s src/pc_port -p "test_*.py" -v` covers the startup hook, rotation order, timer reset, menu-click priority, replay dispatch, and the Ruah DEF line-ending fix. Both converted opening files decode without errors. The Movie Theater buttons have been checked visually in-game; the complete idle rotation still needs a live playtest.
- **Ruah skill freeze**: `build_ruah_def` now normalizes all lines to CRLF. The PC line reader recognizes only CRLF; mixed line endings made comments hide the remaining events, including `EVENT_END`. The user reports that the skill freeze is fixed. `verify_mod.py` rejects non-CRLF Ruah DEF output.

- **Automated Verification (`verify_mod.py`)**: The current local build passes all **7 verification suites (`0` errors)** and **13 source regression tests**, including the opening work.
- **Local test installation**: `d:\Video_Game\Visual Novel\pajama\p_ark201\` contains the updated override archive, both Awake openings, and the corrected `battle1.dat`. Original game files and saves were left unchanged. This is a local test path; use the README's installation instructions for another machine.
- **Pending Live In-Game Playtest**:
  1. Launch `P_ARK201_Ruah.exe` and load battle test saves (`save006` / `save007` / `save008` in slots 7–9) to visually verify Ruah's real PS2 3D model (`ph2chr09.dmo` + `ph2chr09.tga`, `ph2chr09_face.tga`, `ph2chr09_hair.tga`) in Camp UI, Status screen, and active battle.
  2. Test Ruah's custom skills in battle (`PR 5000/5003/5006` → `20000 LUAH_AK_01`, `PR 5001/5004` → `20001 LUAH_SP_01`, `PR 5007` → `20002 LUAH_SP_02`, `PR 5002/5005` → `BOUGYO`, `PR 5008` → `heal2`) and verify weapon trail attachment (`weapon_top`/`weapon_end`) and `B_RUA_*` battle voices.
  3. Verify `ch = 171` (enemy boss Ruah in battles `3811` / `1812`) renders and animates cleanly.

---

# Part B — PS2 CG Decensoring Port (`src/port_cgs.py`)

This workflow patches retail `PA_CG.DAT` inside `Prism Ark - Awake (Japan).iso` (`SLPM-66846`) with uncensored PC event CGs (`Prism_Ark_Awake_PC_CG.xdelta`).

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
