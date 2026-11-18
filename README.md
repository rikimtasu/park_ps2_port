# Prism Ark - Awake (PS2) PC CG Port

xdelta3 patch porting matching CGs (uncensored event CGs, flashback/bust CGs, and censored chibi event CGs) from the PC version of *Prism Ark* into *Prism Ark - Awake* (PS2, `SLPM-66846`).

## Patch File

- **Patch**: `Prism_Ark_Awake_PC_CG.xdelta` (`53,209,517` bytes, created with [xdelta3 v3.2.2](https://github.com/jmacd/xdelta/releases/tag/v3.2.2))
- **Target**: `Prism Ark - Awake (Japan).iso` (`SLPM-66846`, `3,986,259,968` bytes)

### Checksums (SHA-256)

- **Original PS2 ISO**: `bb573076512ed733888ba9b70bbc41061481e786d6b3fc48a07f912e0f53cf2c`
- **Patched PS2 ISO**: `b37aaaf6679d182f0ba5d451b32d9cd5edc1bcaf3f33d856f1a5573303e29188`
- **xdelta Patch**: `ef8f1a056a10b22db89e98bebfa38b14bf4800c9dc186bdb55d19e554ab81312`

## How to Apply

1. Download [xdelta3 v3.2.2](https://github.com/jmacd/xdelta/releases/tag/v3.2.2) (or use any xdelta3-compatible UI such as Delta Patcher).
2. Run:

```bash
xdelta3 -d -s "Prism Ark - Awake (Japan).iso" Prism_Ark_Awake_PC_CG.xdelta "Prism Ark - Awake (Japan) [PC_CG].iso"
```

3. Verify the resulting ISO SHA-256 matches `b37aaaf6679d182f0ba5d451b32d9cd5edc1bcaf3f33d856f1a5573303e29188`.

## Summary of Changes

- Patched **311 `PAG` containers (495 texture layers)** inside `PA_CG.DAT`:
  - Matching event CGs (`PG*`), flashback/bust CGs (`*MEMORY*`, `*BUST*`), and censored chibi event CGs (`PK05_6_03*`, `PK08_3_09*`).
  - Converted PC `.epa` assets using PS2 `0.8 × 0.75` scaling, 256-color quantization with Floyd-Steinberg dithering (including 4D variance-weighted Median-Cut + Floyd-Steinberg RGBA dithering for semi-transparent/animated layers), PS2 GS alpha range (`0x00..0x80`), CSM1 CLUT swizzle, and both `TIM2` and tiled `PTL` texture containers, re-compressed as `ZZZ\0`.
  - Handled PS2-specific framing/rearrangements (`PG04_0_01_kyara1/2`, `PG09_6_00*`, `PG12_3_02L/BKL`, `PG13_0_CAP01..03`, `PGIN_7_03AS`).
  - Preserved PS2-specific assets/UI/filters (`PE_TITLE`, `white.epa`, `black.epa`, `mouse_on_se.epa`, `fl_*.epa`, `pg01_1_00screen.epa`, `PG10_3_00_MAIN`).
- Kept `PA_CG.DAT` at its exact `518,793,216`-byte length at LBA `432995` so ISO9660/UDF structure remains unmodified.
- Build/conversion scripts are included under `src/`.
