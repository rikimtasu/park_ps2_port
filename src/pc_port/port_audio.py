import argparse
import concurrent.futures
import json
import os
import struct
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import awake_movies

STAGED_DIR = os.path.join(common.WORK_DIR, "staged")
AUDIO_DIR = os.path.join(STAGED_DIR, "audio")
VOI_DIR = os.path.join(AUDIO_DIR, "voice")
SE_DIR = os.path.join(AUDIO_DIR, "se")
BGM_DIR = os.path.join(AUDIO_DIR, "bgm")
EXP_DIR = os.path.join(STAGED_DIR, "exp")
MANIFEST_PATH = os.path.join(STAGED_DIR, "needed_assets.json")


def parse_adx_loop(raw: bytes):
    """Return (sr, total_samples, loop_enabled, loop_start, loop_end) for CRI ADX v3/v4."""
    if len(raw) < 0x38 or struct.unpack_from(">H", raw, 0)[0] != 0x8000:
        return (24000, 0, 0, 0, 0)
    enc, blk_sz, bps, ch, sr, total_samples = struct.unpack_from(">BBBBII", raw, 4)
    ver = raw[18]
    if ver == 3:
        le, ls, _, le_s, _ = struct.unpack_from(">IIIII", raw, 0x18)
    elif ver == 4:
        le, ls, _, le_s, _ = struct.unpack_from(">IIIII", raw, 0x24)
    else:
        le, ls, le_s = 0, 0, 0
    return (sr, total_samples, le, ls, le_s)


def convert_adx_bytes_to_ogg(adx_bytes: bytes, out_path: str, quality: int = 5, af: str | None = None, channels: int | None = None):
    """Convert raw ADX bytes in memory to 44100 Hz OGG Vorbis file via ffmpeg stdin pipe."""
    if os.path.exists(out_path) and os.path.getsize(out_path) > 64:
        return True
    tmp_path = out_path + ".tmp"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "adx", "-i", "pipe:0"]
    if af:
        cmd += ["-af", af]
    cmd += ["-ar", "44100"]
    if channels is not None:
        cmd += ["-ac", str(channels)]
    cmd += ["-c:a", "libvorbis", "-q:a", str(quality), "-f", "ogg", tmp_path]
    res = subprocess.run(cmd, input=adx_bytes, capture_output=True)
    if res.returncode != 0:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise RuntimeError(f"ffmpeg failed for {out_path}: {res.stderr.decode('utf-8', 'replace')}")
    os.replace(tmp_path, out_path)
    return True


def main():
    ap = argparse.ArgumentParser(description="Port PS2 audio and movies to the PC mod.")
    ap.add_argument("--movies-only", action="store_true", help="Transcode movies without rebuilding audio")
    args = ap.parse_args()
    t0 = time.time()
    for d in (VOI_DIR, SE_DIR, BGM_DIR, EXP_DIR):
        os.makedirs(d, exist_ok=True)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        man = json.load(f)

    iso = common.IsoReader()
    if args.movies_only:
        try:
            awake_movies.transcode_movies(iso, man["movs"], EXP_DIR)
        finally:
            iso.close()
        audio_manifest_path = os.path.join(STAGED_DIR, "audio_manifest.json")
        if os.path.exists(audio_manifest_path):
            with open(audio_manifest_path, "r", encoding="utf-8") as f:
                audio_manifest = json.load(f)
            audio_manifest["mov_files"] = sorted(man["movs"].values())
            with open(audio_manifest_path, "w", encoding="utf-8") as f:
                json.dump(audio_manifest, f, indent=2, ensure_ascii=False)
        return
    iso_lock = threading.Lock()
    workers = min(16, max(4, os.cpu_count() or 8))

    # ================================================================
    # 1. Convert 9 BGMs + generate patched BGM.ini
    # ================================================================
    print(f"=== Converting {len(man['bgms'])} BGMs ===")
    pc_bgm_ini = common.read_pc_archive_file("archive.dat", "BGM.ini").decode("cp932", "replace")
    bgm_ini_add = ["\r\n// === Ruah Route (Prism Ark - Awake) Port ===\r\n"]
    bgm_ogg_files = []  # filenames in BGM_DIR (excluding SE_* which live in SE_DIR)

    for k, stem in sorted(man["bgms"].items()):
        if k.startswith("SE_"):
            # Looping ambient SE played on BGM channel — audio lives in SE_DIR as PS2_SE_XXXX.ogg
            bgm_ini_add.append(f"[{stem}]\r\nis_ogg = 1\r\nogg_loop_src ={stem}.ogg\r\n\r\n")
            continue

        raw = iso.read_flk_entry("PA_BGM.DAT", int(k))
        sr, total_s, le, ls, le_s = parse_adx_loop(raw)
        if le and ls > 0 and le_s > ls:
            in_fn = f"{stem}_IN.ogg"
            lp_fn = f"{stem}_LP.ogg"
            convert_adx_bytes_to_ogg(
                raw, os.path.join(BGM_DIR, in_fn), quality=6,
                af=f"atrim=start_sample=0:end_sample={ls},asetpts=PTS-STARTPTS", channels=2
            )
            convert_adx_bytes_to_ogg(
                raw, os.path.join(BGM_DIR, lp_fn), quality=6,
                af=f"atrim=start_sample={ls}:end_sample={le_s},asetpts=PTS-STARTPTS", channels=2
            )
            bgm_ogg_files.extend([in_fn, lp_fn])
            bgm_ini_add.append(
                f"[{stem}]\r\nis_ogg = 1\r\nogg_intro_src={in_fn}\r\nogg_loop_src ={lp_fn}\r\n\r\n"
            )
            print(f"  BGM {stem}: split IN (0..{ls}) + LP ({ls}..{le_s})")
        else:
            fn = f"{stem}.ogg"
            convert_adx_bytes_to_ogg(raw, os.path.join(BGM_DIR, fn), quality=6, channels=2)
            bgm_ogg_files.append(fn)
            bgm_ini_add.append(f"[{stem}]\r\nis_ogg = 1\r\nogg_loop_src ={fn}\r\n\r\n")
            print(f"  BGM {stem}: single loop {fn}")

    new_bgm_ini = pc_bgm_ini + "".join(bgm_ini_add)
    with open(os.path.join(STAGED_DIR, "BGM.ini"), "wb") as f:
        f.write(new_bgm_ini.encode("cp932", "replace"))

    # ================================================================
    # 2. Convert 742 SEs in parallel
    # ================================================================
    print(f"=== Converting {len(man['ses'])} SEs (workers={workers}) ===")
    def do_se(item):
        se_id_s, stem = item
        out_path = os.path.join(SE_DIR, f"{stem}.ogg")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 64:
            return stem
        with iso_lock:
            raw = iso.read_flk_entry("PA_SE.DAT", int(se_id_s))
        convert_adx_bytes_to_ogg(raw, out_path, quality=5, channels=2)
        return stem

    se_items = sorted(man["ses"].items(), key=lambda kv: int(kv[0]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        se_done = 0
        for _ in ex.map(do_se, se_items):
            se_done += 1
            if se_done % 250 == 0 or se_done == len(se_items):
                print(f"  SEs: {se_done}/{len(se_items)} ({time.time() - t0:.1f}s)")

    # ================================================================
    # 3. Convert 9,156 Voices in parallel
    # ================================================================
    print(f"=== Converting {len(man['vois'])} Voices (workers={workers}) ===")
    def do_voi(item):
        voi_id_s, stem = item
        out_path = os.path.join(VOI_DIR, f"{stem}.ogg")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 64:
            return stem
        with iso_lock:
            raw = iso.read_flk_entry("PA_VOI.DAT", int(voi_id_s))
        convert_adx_bytes_to_ogg(raw, out_path, quality=5, channels=1)
        return stem

    voi_items = sorted(man["vois"].items(), key=lambda kv: int(kv[0]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        voi_done = 0
        for _ in ex.map(do_voi, voi_items):
            voi_done += 1
            if voi_done % 1000 == 0 or voi_done == len(voi_items):
                print(f"  Voices: {voi_done}/{len(voi_items)} ({time.time() - t0:.1f}s)")

    # ================================================================
    # 4. Transcode Awake openings and Ruah's ending to PC MPEG-1+MP2
    # ================================================================
    awake_movies.transcode_movies(iso, man["movs"], EXP_DIR)

    iso.close()

    audio_manifest = {
        "bgm_files": sorted(bgm_ogg_files),
        "se_files": sorted(f"{stem}.ogg" for _, stem in se_items),
        "voice_files": sorted(f"{stem}.ogg" for _, stem in voi_items),
        "mov_files": sorted(man["movs"].values()),
    }
    with open(os.path.join(STAGED_DIR, "audio_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(audio_manifest, f, indent=2, ensure_ascii=False)

    print(f"\n=== Audio & Movie Port Complete in {time.time() - t0:.1f}s! ===")
    print(f"  BGMs: {len(bgm_ogg_files)} files + BGM.ini")
    print(f"  SEs: {len(se_items)} files")
    print(f"  Voices: {len(voi_items)} files")
    print(f"  Movies: {list(man['movs'].values())}")


if __name__ == "__main__":
    main()
