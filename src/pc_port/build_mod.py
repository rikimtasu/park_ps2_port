import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

STAGED_DIR = os.path.join(common.WORK_DIR, "staged")
GFX_DIR = os.path.join(STAGED_DIR, "gfx")
BGM_DIR = os.path.join(STAGED_DIR, "audio", "bgm")
SE_DIR = os.path.join(STAGED_DIR, "audio", "se")
VOI_DIR = os.path.join(STAGED_DIR, "audio", "voice")
EXP_DIR = os.path.join(STAGED_DIR, "exp")

MOD_FILES = (
    "archive.ini",
    "ruah_mod.dat",
    "ruah_voice.dat",
    "battle1.dat",
    "P_ARK201_Ruah.exe",
    os.path.join("exp", "POP22.DAT"),
)

ARCHIVE_INI_CONTENT = (
    "file=ruah_mod.dat\r\n"
    "file=ruah_voice.dat\r\n"
    "file=archive.dat\r\n"
    "file=archive1.dat\r\n"
    "file=archive2.dat\r\n"
    "file=bgm.dat\r\n"
    "file=se.dat\r\n"
    "file=voice.dat\r\n"
    "file=voice1.dat\r\n"
    "file=voice2.dat\r\n"
)


def preflight_check(need_iso: bool):
    """Verify inputs and external tools exist before starting a long rebuild."""
    if need_iso and not os.path.exists(common.ISO_PATH):
        raise FileNotFoundError(
            f"PS2 ISO not found: {common.ISO_PATH}\n"
            "Pass --iso <path_to_prism_ark_awake.iso> or set PRISM_ARK_ISO."
        )
    req_pc = ("P_ARK201.exe", "archive.dat", "archive1.dat", "archive2.dat", "battle.dat")
    missing_pc = [f for f in req_pc if not os.path.exists(os.path.join(common.PC_DIR, f))]
    if missing_pc:
        raise FileNotFoundError(
            f"PC Prism Ark folder incomplete ({common.PC_DIR}), missing: {missing_pc}\n"
            "Pass --pc-dir <path_to_p_ark201> or set PRISM_ARK_PC_DIR."
        )
    if need_iso:
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise RuntimeError(f"Required tool `{tool}` not found on PATH.")
    # Ensure C helper shared lib and unpacked PRSM lookup table are ready
    common.ensure_dll()
    common.load_prsm_tables()


def pack_mod(out_dir: str):
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "exp"), exist_ok=True)

    with open(os.path.join(STAGED_DIR, "gfx_manifest.json"), "r", encoding="utf-8") as f:
        gfx_man = json.load(f)
    with open(os.path.join(STAGED_DIR, "audio_manifest.json"), "r", encoding="utf-8") as f:
        aud_man = json.load(f)

    # 1. Build ruah_mod.dat (core data + graphics + BGMs + SEs)
    print(f"=== Packing {out_dir}/ruah_mod.dat ===")
    mod_files = []
    for core_fn in ("scenario.dat", "textdata.bin", "filename.dat", "graphic.bin", "BGM.ini"):
        p = os.path.join(STAGED_DIR, core_fn)
        with open(p, "rb") as f:
            mod_files.append((core_fn, f.read()))
    for fn in gfx_man["epas"] + gfx_man["anms"]:
        with open(os.path.join(GFX_DIR, fn), "rb") as f:
            mod_files.append((fn, f.read()))
    for fn in aud_man["bgm_files"]:
        with open(os.path.join(BGM_DIR, fn), "rb") as f:
            mod_files.append((fn, f.read()))
    for fn in aud_man["se_files"]:
        with open(os.path.join(SE_DIR, fn), "rb") as f:
            mod_files.append((fn, f.read()))

    mod_dat_path = os.path.join(out_dir, "ruah_mod.dat")
    common.write_gamedat_pac2(mod_dat_path, mod_files)
    print(f"  Wrote ruah_mod.dat: {len(mod_files)} files, {os.path.getsize(mod_dat_path):,} bytes ({time.time() - t0:.1f}s)")

    # 2. Build ruah_voice.dat (all new voice .ogg files)
    print(f"=== Packing {out_dir}/ruah_voice.dat ===")
    voi_files = []
    for fn in aud_man["voice_files"]:
        with open(os.path.join(VOI_DIR, fn), "rb") as f:
            voi_files.append((fn, f.read()))
    voi_dat_path = os.path.join(out_dir, "ruah_voice.dat")
    common.write_gamedat_pac2(voi_dat_path, voi_files)
    print(f"  Wrote ruah_voice.dat: {len(voi_files)} files, {os.path.getsize(voi_dat_path):,} bytes ({time.time() - t0:.1f}s)")

    # 3. Copy exp/POP22.DAT
    for mov_fn in aud_man["mov_files"]:
        src = os.path.join(EXP_DIR, mov_fn)
        dst = os.path.join(out_dir, "exp", mov_fn)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copy2(src, dst)
        print(f"  Staged exp/{mov_fn}: {os.path.getsize(dst):,} bytes")

    # 4. Write loose archive.ini
    ini_path = os.path.join(out_dir, "archive.ini")
    with open(ini_path, "wb") as f:
        f.write(ARCHIVE_INI_CONTENT.encode("ascii"))
    print("  Wrote archive.ini")

    # 5. Verify battle1.dat & P_ARK201_Ruah.exe exist
    b1 = os.path.join(out_dir, "battle1.dat")
    assert os.path.exists(b1), "battle1.dat missing! Run with --all or run port_battles.py first."
    print(f"  Verified battle1.dat: {os.path.getsize(b1):,} bytes")

    exe_out = os.path.join(out_dir, "P_ARK201_Ruah.exe")
    if not os.path.exists(exe_out):
        import patch_exe
        patch_exe.patch_pe_exe(os.path.join(common.PC_DIR, "P_ARK201.exe"), exe_out)
    print(f"  Verified P_ARK201_Ruah.exe: {os.path.getsize(exe_out):,} bytes")

    print(f"\n=== Mod Package Ready in {out_dir} ({time.time() - t0:.1f}s) ===")


def install_mod(out_dir: str, pc_dir: str, with_test_saves: bool = False):
    print(f"\n=== Installing mod non-destructively into {pc_dir} ===")
    for rel in MOD_FILES:
        src = os.path.join(out_dir, rel)
        dst = os.path.join(pc_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  Installed {rel} ({os.path.getsize(dst):,} bytes)")
    if with_test_saves:
        ts_dir = os.path.join(out_dir, "test_saves")
        if os.path.isdir(ts_dir):
            save_dir = os.path.join(pc_dir, "save")
            os.makedirs(save_dir, exist_ok=True)
            for fn in sorted(os.listdir(ts_dir)):
                shutil.copy2(os.path.join(ts_dir, fn), os.path.join(save_dir, fn))
            print(f"  Installed test saves (Slots 6-9) into {save_dir}")
    print("Install complete! Zero original PC game files were modified.")


def main():
    ap = argparse.ArgumentParser(
        description="Build the non-destructive Ruah Route PC mod from Prism Ark - Awake (PS2 ISO) + PC Prism Ark."
    )
    ap.add_argument("--all", action="store_true", help="Run full rebuild from ISO + PC files (scripts, graphics, audio, battles, pack)")
    ap.add_argument("--iso", help="Path to Prism Ark - Awake (Japan).iso")
    ap.add_argument("--pc-dir", help="Path to PC Prism Ark folder containing P_ARK201.exe and .dat archives")
    ap.add_argument("--out-dir", help="Output mod folder (default: pc_ruah_mod)")
    ap.add_argument("--verify", action="store_true", help="Run verify_mod.py after packing")
    ap.add_argument("--with-test-saves", action="store_true", help="Also generate Slot 6-8 test saves if base save000.sav exists")
    ap.add_argument("--install", action="store_true", help="Copy built mod files non-destructively into --pc-dir")
    args = ap.parse_args()

    env = os.environ.copy()
    if args.iso:
        common.ISO_PATH = os.path.abspath(args.iso)
        env["PRISM_ARK_ISO"] = common.ISO_PATH
    if args.pc_dir:
        common.PC_DIR = os.path.abspath(args.pc_dir)
        env["PRISM_ARK_PC_DIR"] = common.PC_DIR
    if args.out_dir:
        common.MOD_OUT_DIR = os.path.abspath(args.out_dir)
        env["PRISM_ARK_OUT_DIR"] = common.MOD_OUT_DIR

    preflight_check(need_iso=args.all)

    here = os.path.dirname(os.path.abspath(__file__))
    if args.all:
        for script in ("port_scripts.py", "port_graphics.py", "port_audio.py", "port_battles.py", "patch_exe.py"):
            print(f"\n>>> Running {script} ...")
            subprocess.run([sys.executable, os.path.join(here, script)], env=env, check=True)

    pack_mod(common.MOD_OUT_DIR)

    if args.with_test_saves:
        print("\n>>> Running make_test_saves.py ...")
        subprocess.run([sys.executable, os.path.join(here, "make_test_saves.py")], env=env, check=True)

    if args.verify:
        print("\n>>> Running verify_mod.py ...")
        subprocess.run([sys.executable, os.path.join(here, "verify_mod.py")], env=env, check=True)

    if args.install:
        install_mod(common.MOD_OUT_DIR, common.PC_DIR, with_test_saves=args.with_test_saves)


if __name__ == "__main__":
    main()
