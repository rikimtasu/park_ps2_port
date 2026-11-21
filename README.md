# Prism Ark - Awake (PS2) PC CG Port

xdelta3 patch porting matching CGs (uncensored event CGs, flashback/bust CGs, and censored chibi event CGs) from the PC version of *Prism Ark* into *Prism Ark - Awake* (PS2, `SLPM-66846`).

## Reproducing the Patch

The binary `.xdelta` patch is **not distributed** in this repository. Rebuild it from your own copy of the games:

- **Target**: `Prism Ark - Awake (Japan).iso` (`SLPM-66846`, `3,986,259,968` bytes)
- **Original PS2 ISO SHA-256**: `bb573076512ed733888ba9b70bbc41061481e786d6b3fc48a07f912e0f53cf2c`
- **Expected patched ISO SHA-256**: `b37aaaf6679d182f0ba5d451b32d9cd5edc1bcaf3f33d856f1a5573303e29188`

1. Extract `PA_CG.DAT` from the PS2 ISO and have the PC game's `archive*.dat` files available.
2. Compile `src/zzz_helper.c` into `zzz_helper.dll` (ZZZ compressor/decompressor helper).
3. Run `python src/port_cgs.py --pc-dir <PC archive dir> --ps2-dir <dir with PA_CG.DAT> --dll zzz_helper.dll` to produce `PA_CG_NEW.DAT` (use `--dry-run` to validate only).
4. Write the new `PA_CG.DAT` back into the ISO at LBA `432995` (same size, `518,793,216` bytes).
5. Optionally create a distributable patch with [xdelta3 v3.2.2](https://github.com/jmacd/xdelta/releases/tag/v3.2.2): `xdelta3 -e -s "Prism Ark - Awake (Japan).iso" "<patched>.iso" Prism_Ark_Awake_PC_CG.xdelta`
## Summary of Changes

- Patched **311 `PAG` containers (495 texture layers)** inside `PA_CG.DAT`:
  - Matching event CGs (`PG*`), flashback/bust CGs (`*MEMORY*`, `*BUST*`), and censored chibi event CGs (`PK05_6_03*`, `PK08_3_09*`).
  - Converted PC `.epa` assets using PS2 `0.8 × 0.75` scaling, 256-color quantization with Floyd-Steinberg dithering (including 4D variance-weighted Median-Cut + Floyd-Steinberg RGBA dithering for semi-transparent/animated layers), PS2 GS alpha range (`0x00..0x80`), CSM1 CLUT swizzle, and both `TIM2` and tiled `PTL` texture containers, re-compressed as `ZZZ\0`.
  - Handled PS2-specific framing/rearrangements (`PG04_0_01_kyara1/2`, `PG09_6_00*`, `PG12_3_02L/BKL`, `PG13_0_CAP01..03`, `PGIN_7_03AS`).
  - Preserved PS2-specific assets/UI/filters (`PE_TITLE`, `white.epa`, `black.epa`, `mouse_on_se.epa`, `fl_*.epa`, `pg01_1_00screen.epa`, `PG10_3_00_MAIN`).
- Kept `PA_CG.DAT` at its exact `518,793,216`-byte length at LBA `432995` so ISO9660/UDF structure remains unmodified.
- Build/conversion scripts are included under `src/`.

