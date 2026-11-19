# Prism Ark (PC) — Ruah Route (`Prism Ark - Awake`) Non-Destructive Mod

Ports **Ruah (`ルーア`)** and everything new she brings from the PS2 version (*Prism Ark - Awake*, `SLPM-66846`) to the PC version (*Prism Ark* `P_ARK201.exe`, PJADV engine) as a **100% non-destructive drop-in mod**.

Zero original PC game files are modified or overwritten, and all 7 original PC heroine routes (including all original PC scenes) remain completely intact.

## Output Mod Files (`pc_ruah_mod/`)

Copy the contents of `pc_ruah_mod/` directly into your PC game folder (`d:\Video_Game\Visual Novel\pajama\p_ark201\`):

| File | Size | Purpose |
|---|---:|---|
| `archive.ini` | 192 B | Loose override read first by `P_ARK201.exe` (`CArchiveManager` first-archive-wins), mounting `ruah_mod.dat` and `ruah_voice.dat` before vanilla `.dat` archives |
| `ruah_mod.dat` | ~240 MB | `GAMEDAT PAC2` containing patched `scenario.dat`, `textdata.bin`, `filename.dat`, `graphic.bin`, `BGM.ini`, 450 converted `.epa` graphics, 200 byte-exact `.anm` animations, 5 BGM `.ogg` files, and 742 SE `.ogg` files |
| `ruah_voice.dat` | ~235 MB | `GAMEDAT PAC2` containing all 9,156 new voice `.ogg` clips (Ruah + cast lines across Ruah's scenes, Mediard, and new Intermission episodes) |
| `battle1.dat` | ~2.5 MB | `PRSM` archive auto-mounted above `battle.dat` by `P_ARK201.exe`, adding all 14 Ruah/Awake battles, Prism #225 (`平和の心`), Boss Ruah's exclusive skills (`PR 5003–5008`), and `BWP_RUAH01.tga` |
| `exp/POP22.DAT` | ~160 MB | *Prism Ark - Awake* ED2 movie (Ruah ending credits), deinterlaced and transcoded to PC's native `800×600` MPEG-1 + `44100 Hz` MP2 DirectShow format |

### Uninstall
Simply delete those 5 files (`archive.ini`, `ruah_mod.dat`, `ruah_voice.dat`, `battle1.dat`, `exp/POP22.DAT`) from the PC game folder to return to 100% vanilla PC *Prism Ark*.

## What Is Ported

- **Story & Scripts (`scenario.dat`, `textdata.bin`, `filename.dat`)**:
  - Common Route Chapters 2–8 with Ruah's introduction (`乙女あり、遠方より来たる？`), Mediard (`中立都市メディアード`), and Ch.8 route selection (`運命の選択`, route `8`).
  - Intermission with all 6 interludes, including the 3 PS2-exclusive interludes (`哀と青春のエプロン`, `お花見大会`, `あこがれの人。戦うルーア！`).
  - Complete Ruah Route: Chapters 9–14 (`ひみつのレッスン` through finale) + Epilogue (`旅だちの日に`, `ルーア編 クリア`) + ED2 movie (`POP22.DAT`).
  - All 7 original PC heroine routes (`1..7`) are preserved verbatim.
- **Graphics (`graphic.bin`, `.epa`, `.anm`)**:
  - 347 new `graphic.bin` definitions (`+450` lossless PC `.epa` images, `+200` byte-exact `ANM1` animations): all Ruah standing sprites across 7 PXG packs (with eye-blink animations), all Ruah event CGs (including tall scrolling CGs), animated chibi battle CGs (`PSMG_8_02*` / `PSMG_8_03*`), `PB017A`, `PSED_8_00A`, and Prism #225 art.
- **Audio & Movie**:
  - Ruah's theme (`BGM99` with seamless intro/loop split `BGM99_IN.ogg` + `BGM99_LP.ogg`), `BGM_CS8`, `BGM_OP1`, `BGM_OP2`, and 5 looping ambient tracks registered in `BGM.ini`.
  - 742 authentic PS2 SEs (`PS2_SE_XXXX.ogg`) and 9,156 new voice clips (`ruah_voice.dat`).
  - Transcoded `exp/POP22.DAT` ending movie.
- **Battles & Prisms (`battle1.dat`)**:
  - All 14 PS2-exclusive / Ruah-route battles (`62, 808, 809, 810, 1810, 811, 1811, 2811, 3811, 812, 1812, 813, 1813, 2813`) with decompiled `field_*.txt`, `map_*.txt`, and `char_0062.txt`.
  - Prism #225 (`平和の心`: *"ルーアが追い求める、理想の世界。"*) + 3D icon (`prism225.x`, `prism225.tga`, `prism_name_text225.tga`) and Boss Ruah's exclusive battle skills (`PR 5003–5008`).

## Known PC Engine Notes
- **Playable ally Ruah (`ch = 9`)**: Unpatched `P_ARK201.exe` hardcodes playable party character slots `0..8`. To preserve zero-`.exe`-modification compatibility, ally `ch = 9` slots are omitted in party battles (Hayaway and party members fight normally), while **enemy boss `[ルーア]`** in battles `3811` and `1812` is mapped to native enemy slot `ch = 171` (Partiel's angelic model) with Ruah's exact PS2 name, stats (`22,000 LP`), and custom boss skills (`5003–5008`).
- **Omake CG Gallery**: PC's pre-rendered 6-page Omake UI (`SYS_OM_PAGE1..6`) is left untouched to keep all 7 original heroines' galleries intact; Ruah's CGs and ending are viewed in-story.

## Rebuilding & Verifying From Source

### Requirements
- **Python 3.10+** with `pip install -r requirements.txt` (`numpy`, `Pillow`)
- **`ffmpeg` & `ffprobe`** on `PATH`
- **`gcc`** on `PATH` (or MSYS2 `C:\msys64\ucrt64\bin\gcc.exe`) — used automatically to compile `src/zzz_helper.dll` if not already built
- A copy of **`Prism Ark - Awake (Japan).iso`** (PS2) and the **PC *Prism Ark* folder** (containing `P_ARK201.exe`, `archive*.dat`, `battle.dat`, etc.)

### One-Command Rebuild

```powershell
# Rebuild entire mod from PS2 ISO + PC game directory and run the 6-suite verifier:
python src/pc_port/build_mod.py --all --iso "D:\path\to\Prism Ark - Awake (Japan).iso" --pc-dir "D:\path\to\p_ark201" --verify

# Optional flags:
#   --out-dir <dir>     Output directory (default: pc_ruah_mod)
#   --with-test-saves   Also generate Slot 6-8 test saves from save\save000.sav
#   --install           Copy built mod files non-destructively into --pc-dir
```

Or on Windows, run [rebuild_pc_mod.bat](rebuild_pc_mod.bat):

```bat
rebuild_pc_mod.bat "D:\path\to\Prism Ark - Awake (Japan).iso" "D:\path\to\p_ark201"
```

What happens automatically on a clean checkout:
1. Compiles `src/zzz_helper.c` -> `src/zzz_helper.dll` (via `gcc`) if not yet built.
2. Unpacks `P_ARK201.exe` (UPX NRV2E) in pure Python to extract the `battle.dat` PRSM table.
3. Streams scripts, CGs, PXG sprites, voices, BGMs, SEs, battles, and ED2 movie directly from the PS2 ISO (no multi-GB ISO extraction needed) into `pc_ruah_mod/`.
4. Runs `verify_mod.py` across all 6 structural/round-trip verification suites.
