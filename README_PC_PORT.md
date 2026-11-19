# Prism Ark (PC) — Ruah Route (`Prism Ark - Awake`) Non-Destructive Mod

Ports **Ruah (`ルーア`)** and everything new she brings from the PS2 version (*Prism Ark - Awake*, `SLPM-66846`) to the PC version (*Prism Ark* `P_ARK201.exe`, PJADV engine) as a **100% non-destructive drop-in mod**.

Zero original PC game files are modified or overwritten, and all 7 original PC heroine routes (including all original PC scenes) remain completely intact.

## Output Mod Files (`pc_ruah_mod/`)

Copy the contents of `pc_ruah_mod/` directly into your PC game folder (`d:\Video_Game\Visual Novel\pajama\p_ark201\`):

| File | Size | Purpose |
|---|---:|---|
| `P_ARK201_Ruah.exe` | ~8.7 MB | Non-destructive patched executable (launch this to play!) that expands PC party character capacity from `0..8` (`9` slots) to `0..9` (`10` slots) via a dedicated `.ruah` section (`VA 0x0087A000`), enabling **Playable Ally Ruah (`ch = 9`)** in battle |
| `archive.ini` | 192 B | Loose override read first by `P_ARK201.exe` (`CArchiveManager` first-archive-wins), mounting `ruah_mod.dat` and `ruah_voice.dat` before vanilla `.dat` archives |
| `ruah_mod.dat` | ~263 MB | `GAMEDAT PAC2` containing patched `scenario.dat`, `textdata.bin`, `filename.dat`, `graphic.bin`, `BGM.ini`, 514 converted `.epa` graphics (story CGs, sprites, title cards, expanded Omake UI & thumbnails), 200 byte-exact `.anm` animations, 7 BGM `.ogg` files, and 742 SE `.ogg` files |
| `ruah_voice.dat` | ~201 MB | `GAMEDAT PAC2` containing all 9,156 new `44100 Hz` voice `.ogg` clips (Ruah + cast lines across Ruah's scenes, Mediard, and new Intermission episodes) |
| `battle1.dat` | ~5.3 MB | `PRSM` archive auto-mounted above `battle.dat`, adding all 14 Ruah/Awake battles (with Ruah `ch = 9` playable in all 10 Ruah ally battles), Ruah's `CHD[8]` growth curve in `ch_sheet.txt`, 6 battle HUD/cut-in TGAs (`bt_v09.tga`, `bt_a09.tga`, `st_e09.tga`, `cut_09.tga`, `bte_09a/b.tga`), `ph2chr09.*` 3D battle model, 104 `44100 Hz` battle voices (`B_RUA_0000..0103.ogg`), Prism #225 (`平和の心`), and Ruah's skills (`PR 5000–5008`) |
| `exp/POP22.DAT` | ~160 MB | *Prism Ark - Awake* ED2 movie (Ruah ending credits), deinterlaced and transcoded to PC's native `800×600` MPEG-1 + `44100 Hz` MP2 DirectShow format |

### Uninstall
Simply delete those 6 files (`P_ARK201_Ruah.exe`, `archive.ini`, `ruah_mod.dat`, `ruah_voice.dat`, `battle1.dat`, `exp/POP22.DAT`) from the PC game folder to return to 100% vanilla PC *Prism Ark*.

## What Is Ported

- **Playable Ally Ruah (`ch = 9`) in `P_ARK201_Ruah.exe` + `battle1.dat`**:
  - Unpacks `P_ARK201.exe` (UPX NRV2E) and applies 49 verified binary patches + 6 x86 trampolines in `.ruah` (`VA 0x0087A000`), relocating `CSimGame` (`0x7655C0 -> 0x87B000`) to expand `m_charStat[9] -> m_charStat[10]` without shifting subsequent globals.
  - Hooks character name lookup (`ch == 9 -> "ルーア"`), battle portrait filenames (`bt_v09.tga`, `bt_a09.tga`, `st_e09.tga`), victory cut-in overlay (`cut_09.tga`), 3D character folder (`ruah\ph2chr09`), battle voice prefix (`B_RUA_%04d.ogg`), and `common.se`/`random.se` skill sound routing (`PR 5000–5008`).
  - Ruah (`[ルーア]`, `ch = 9`) fights as a playable party member across all 10 Ruah ally battles (`62, 808, 809, 810, 1810, 811, 1811, 812, 813, 1813` — 26 battle stages total), while Enemy Boss Ruah in `3811` & `1812` fights with her `22,000 LP` boss stats and skills.
- **Expanded Omake (`SPECIAL` Menu — Unlocked & Expanded Across All 4 Sub-Modes)**:
  - **Title Screen `OMAKE` (`SPECIAL`) Button**: Unlocked automatically along with all gallery items.
  - **CG Gallery (`ART GALLERY`)**: Adds **15 new Awake CG sets** (with 2-state normal/hover thumbnails and multi-variation click cycling):
    - **Karin Tab (`Page 4`, Slot 12)**: `PS04_4_00A`
    - **Filia Tab (`Page 7`, Slot 09)**: `PS06_7_00A..D` (4 variations)
    - **Other / Ruah Tab (`Page 8`, Slots 07–17, BGM switched to Ruah's Theme `BGM_CS8`)**: all 11 Ruah Event CG sets (`PS02_8_00A/B`, `PS03_8_00A/B/C+BG`, `PS04_8_00A`, `PS05_8_00A/B`, `PS06_8_00A..C`, `PS10_8_00A`, `PS11_8_00A..C/PS11_8_00`, `PS11_8_01A`, `PS12_8_00A..C`, `PS13_8_00_BG+RUA+HYA`, `PSED_8_00A`)
    - **Mini-CG Page 3 (`Page 9C`, Slots 09–10)**: Ruah's 2 SD Mini-CG sets (`PSMG_8_02A..D` over `PB021_4Y`, `PSMG_8_03A..E` over `PB056`)
  - **Scene Replay (`REPLAY`)**: Expands `SYS_OS_BASE01` with **Slots 12–15** (`SYS_OS_THUMB0801..0804`), replaying 4 self-contained, battle-free Ruah Route episodes (Ch.2 Ruah's Debut, Intermission Ruah's Special Interlude, Ch.10 Ruah's Twilight Scene, and Ruah Route Ending & Epilogue).
  - **Music Mode (`SOUND THEATER`)**: Expands Page 4 (`SYS_M_BASE4` + extended `512×768` title plate `sys_m_files05.EPA`) with **Slots `M14–M19`** playing all 6 new PS2 *Awake* BGM tracks (`ルーアのテーマ`, `覚醒の絆`, `贖罪のラプソディー (Awake)`, `原罪のレクイエム (Awake)`, `Sigh… (Awake ED1)`, `追憶のノクターン (ルーアED)`).
  - **Movie Mode (`MOVIE THEATER`)**: Expands `SYS_OV_BASE` with **Slot 20** (`SYS_OV_B20`) playing **`POP22.DAT` (Ruah Ending Movie / Awake ED2)**.
- **Story & Scripts (`scenario.dat`, `textdata.bin`, `filename.dat`)**:
  - Common Route Chapters 2–8 with Ruah's introduction (`乙女あり、遠方より来たる？`), Mediard (`中立都市メディアード`), and Ch.8 route selection (`運命の選択`, route `8`).
  - Intermission with all 6 interludes, including the 3 PS2-exclusive interludes (`哀と青春のエプロン`, `お花見大会`, `あこがれの人。戦うルーア！`).
  - Complete Ruah Route: Chapters 9–14 (`ひみつのレッスン` through finale) + Epilogue (`旅だちの日に`, `ルーア編 クリア`) + ED2 movie (`POP22.DAT`).
  - All 7 original PC heroine routes (`1..7`) are preserved verbatim.
- **Graphics (`graphic.bin`, `.epa`, `.anm`)**:
  - 409 new `graphic.bin` definitions (`+514` lossless PC `.epa` images, `+200` byte-exact `ANM1` animations): all Ruah standing sprites across 7 PXG packs (with eye-blink animations), all Ruah event CGs (including tall scrolling CGs), Ruah chapter title cards (`TITLE08_8..TITLE13_8A`) and eyecatch (`EYECATCH08K`), animated chibi battle CGs (`PSMG_8_02*` / `PSMG_8_03*`), `PB017A`, `PSED_8_00A`, Prism #225 art, and 28 Omake UI textures/thumbnails.
- **Audio & Movie**:
  - All 6 new PS2 *Awake* BGM tracks (`BGM99` with seamless intro/loop split `BGM99_IN.ogg` + `BGM99_LP.ogg`, `BGM_CS8`, `BGM_OP1`, `BGM_OP2`, `BGM_ED1`, `BGM_ED2`) and 5 looping ambient tracks registered in `BGM.ini`.
  - 742 authentic PS2 SEs (`PS2_SE_XXXX.ogg`) and 9,156 new `44100 Hz` voice clips (`ruah_voice.dat`).
  - Transcoded `exp/POP22.DAT` ending movie.
- **Test Saves (`pc_ruah_mod/test_saves/save005.sav..save008.sav`, Slots 6–9)**:
  - **Slot 6 (`save005.sav`)**: Ch.2 right at Ruah's first encounter (`乙女あり、遠方より来たる？`)
  - **Slot 7 (`save006.sav`)**: Ch.8 right before the Heroine Route Choice (`運命の選択`)
  - **Slot 8 (`save007.sav`)**: Ch.9 start of Ruah Route (`ひみつのレッスン`)
  - **Slot 9 (`save008.sav`)**: Ch.9 one click before Battle `808` (`ひみつのレッスン（ルーア参戦直前）`) to immediately test Playable Ally Ruah in battle

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
