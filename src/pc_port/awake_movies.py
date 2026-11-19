import os
import struct
import subprocess
import time


# (PS2 PA_MOV index, PC filename, replay choice, button name, screen position)
OPENINGS = (
    (13, "POP23.DAT", 21, "SYS_OV_AWAKE_OP1", (111, 518)),
    (14, "POP24.DAT", 22, "SYS_OV_AWAKE_OP2", (443, 518)),
)
MOD_MOVIES = ("POP22.DAT",) + tuple(movie[1] for movie in OPENINGS)
TITLE_IDLE_SECONDS = 30
TITLE_IDLE_MOVIES = ("POP24.DAT", "POP00.DAT", "POP07.DAT", "POP23.DAT")
# Unused in the vanilla and ported scenario; keep clear of the EXP floor at 0x3DC.
TITLE_IDLE_VAR = 0x100003D9
TITLE_NEXT_DEMO_VAR = 0x100003DA


def patch_startup_movie(scenario: bytearray, filename_id: int):
    """Play Awake OP1 after the publisher logo, then resume the title script."""
    hook = 0x1C8
    displaced = struct.pack("<2I", 0x01000502, 1000)
    assert scenario[hook:hook + 8] == displaced, "Unexpected PC startup script"
    entry = len(scenario)
    scenario.extend(displaced)
    scenario.extend(struct.pack("<3I", 0x02000103, 0x30000000, 0))
    scenario.extend(struct.pack("<3I", 0x02000103, TITLE_NEXT_DEMO_VAR, 0x30000000))
    scenario.extend(struct.pack("<2I", 0x05000102, 0))  # Stop the logo BGM.
    scenario.extend(struct.pack("<2I", 0x05030002, filename_id))
    scenario.extend(struct.pack("<2I", 0x01000202, hook + 8))
    struct.pack_into("<2I", scenario, hook, 0x01000202, entry)


def patch_title_idle_movies(scenario: bytearray, movie_ids: tuple[int, ...]):
    """Rotate Awake OP2, PC OP1, PC OP2, and Awake OP1 during title waits."""
    assert len(movie_ids) == len(TITLE_IDLE_MOVIES)

    def emit(ops):
        entry = len(scenario)
        for op, args in ops:
            scenario.extend(struct.pack(f"<{len(args) + 1}I", op, *args))
        return entry

    # Menu selection also resets the timer. Cancelling the exit prompt returns
    # directly to the existing buttons rather than recreating them.
    menu_hook = 0x74C
    assert struct.unpack_from("<I", scenario, menu_hook)[0] == 0x778
    menu_ip = emit([
        (0x02000103, [0x30000000, 0]),
        (0x02000103, [TITLE_IDLE_VAR, 0x30000000]),
        (0x01000202, [0x778]),
    ])
    struct.pack_into("<I", scenario, menu_hook, menu_ip)

    # Reset the timer whenever title buttons are recreated, including after menus.
    group_hook = 0x4EC
    assert scenario[group_hook:group_hook + 8] == struct.pack("<2I", 0x01020002, 3)
    reset_ip = emit([
        (0x02000103, [0x30000000, 0]),
        (0x02000103, [TITLE_IDLE_VAR, 0x30000000]),
        (0x01020002, [3]),
        (0x01000202, [group_hook + 8]),
    ])
    struct.pack_into("<2I", scenario, group_hook, 0x01000202, reset_ip)

    # The vanilla target-0 rendering wait enters native state 8 and ignores
    # its nominal 1000 ms duration. Use the real timed wait (state 2) instead;
    # it still processes button callbacks and yields early for menu clicks.
    wait_hook = 0x758
    assert scenario[wait_hook:wait_hook + 16] == struct.pack("<4I", 0x80010004, 0, 1000, 0)
    struct.pack_into("<4I", scenario, wait_hook, 0x01000502, 1000, 0x01000202, 0x768)

    # Each uninterrupted title-loop pass now waits one real second.
    loop_hook = 0x770
    assert scenario[loop_hook:loop_hook + 8] == struct.pack("<2I", 0x01000202, 0x714)
    tick_ip = emit([
        (0x02000103, [0x30000000, TITLE_IDLE_VAR]),
        (0x02000203, [0x30000000, 1]),
        (0x02000103, [TITLE_IDLE_VAR, 0x30000000]),
        (0x02000103, [0x30000001, TITLE_IDLE_SECONDS]),
        (0x02010003, [0x30000001, 0x30000000]),
        (0x01000703, [0x30000001, 0x714]),
        # A menu click arriving at the end of the wait takes priority over a demo.
        (0x02000103, [0x30000000, 0x20000226]),
        (0x01000703, [0x30000000, 0]),
        (0x01000202, [0x714]),
    ])
    demo_ip = len(scenario)
    struct.pack_into("<I", scenario, tick_ip + 6 * 12 + 12 + 8, demo_ip)
    emit([
        (0x01000302, [0x101C]),  # Existing title-button/sprite cleanup.
        (0x05000102, [500]),
        (0x80010102, [1]),  # BLACK, unchanged vanilla filename ID.
        (0x80010004, [1, 500, 1]),
        (0x05000102, [0]),
        (0x02000103, [0x30000000, TITLE_NEXT_DEMO_VAR]),
    ])
    for index, movie_id in enumerate(movie_ids[:-1]):
        next_branch = len(scenario) + 19 * 4
        emit([
            (0x02000103, [0x30000001, index]),
            (0x02010003, [0x30000001, 0x30000000]),
            (0x01000703, [0x30000001, next_branch]),
            (0x02000103, [0x30000001, index + 1]),
            (0x02000103, [TITLE_NEXT_DEMO_VAR, 0x30000001]),
            (0x05030002, [movie_id]),
            (0x01000202, [0x4B8]),
        ])
    emit([
        (0x02000103, [0x30000001, 0]),
        (0x02000103, [TITLE_NEXT_DEMO_VAR, 0x30000001]),
        (0x05030002, [movie_ids[-1]]),
        (0x01000202, [0x4B8]),
    ])
    struct.pack_into("<2I", scenario, loop_hook, 0x01000202, tick_ip)


def transcode_movies(iso, movies: dict, exp_dir: str):
    """Convert selected PS2 movies to the PC engine's MPEG-1/MP2 format."""
    os.makedirs(exp_dir, exist_ok=True)
    for mov_id_s, pop_name in sorted(movies.items(), key=lambda item: int(item[0])):
        mov_id = int(mov_id_s)
        out_mov = os.path.join(exp_dir, pop_name)
        if os.path.exists(out_mov) and os.path.getsize(out_mov) > 1024 * 1024:
            print(f"=== Movie {pop_name} already transcoded ({os.path.getsize(out_mov):,} bytes) ===")
            continue
        t0 = time.time()
        print(f"=== Transcoding PA_MOV.DAT[{mov_id}] -> {pop_name} ===", flush=True)
        raw_movie = os.path.join(exp_dir, f"_tmp_mov_{mov_id}.pss")
        tmp_out = out_mov + ".tmp"
        try:
            base, entries = iso.get_flk_table("PA_MOV.DAT")
            offset, remaining = entries[mov_id]
            iso.fh.seek(base + offset)
            with open(raw_movie, "wb") as f:
                while remaining:
                    chunk = iso.fh.read(min(remaining, 4 * 1024 * 1024))
                    if not chunk:
                        raise EOFError(f"Truncated PA_MOV.DAT[{mov_id}]")
                    f.write(chunk)
                    remaining -= len(chunk)
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", raw_movie,
                "-map", "0:v:0", "-map", "0:a:0",
                "-vf", "yadif,scale=800:600:flags=lanczos",
                "-c:v", "mpeg1video", "-b:v", "7500k", "-maxrate", "8500k", "-bufsize", "2048k",
                "-r", "30000/1001", "-pix_fmt", "yuv420p",
                "-c:a", "mp2", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                "-f", "mpeg", tmp_out,
            ]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode:
                raise RuntimeError(f"Movie transcode failed: {result.stderr.decode('utf-8', 'replace')}")
            os.replace(tmp_out, out_mov)
            print(f"  Transcoded {pop_name}: {os.path.getsize(out_mov):,} bytes ({time.time() - t0:.1f}s)")
        finally:
            for temporary in (raw_movie, tmp_out):
                if os.path.exists(temporary):
                    os.remove(temporary)
