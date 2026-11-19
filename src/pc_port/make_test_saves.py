import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

OUT_DIR = os.path.join(common.MOD_OUT_DIR, "test_saves")


def make_save(
    template_sav: bytes,
    template_thumb: bytes,
    slot: int,
    msg_id: int,
    ret_ip: int,
    title: str,
    route: int,
    party_exp: int | None = None,
    local_vars: dict[int, int] | None = None,
):
    buf = bytearray(template_sav)
    # 1. Chapter title at 0x2db4 (0x100 bytes, CP932 null-terminated)
    tb = title.encode("cp932")
    assert len(tb) < 0x100
    buf[0x2db4 : 0x2db4 + 0x100] = tb + b"\x00" * (0x100 - len(tb))

    # 2. Local variable 0x10000000 (heroine route: 0=common, 8=Ruah) at 0x2ed4
    struct.pack_into("<I", buf, 0x2ed4, route)
    if local_vars:
        for var_id, val in local_vars.items():
            idx = var_id & 0xFFFF
            struct.pack_into("<I", buf, 0x2ed4 + idx * 4, val)

    # 2b. Optional per-save party EXP floor (applied by P_ARK201_Ruah.exe tramp_exp_snap to all 9 allies)
    #     Stored in unused local var[0x100003dc] -> save offset 0x2ed4 + 0x3dc*4 = 0x3e44 (battle RAM 0x57593c)
    if party_exp is not None:
        struct.pack_into("<I", buf, 0x3e44, party_exp)

    # 2c. Clear stale Ch.1 sprite handle variables var[0x100003e0..0x100003ef] from save000.sav
    buf[0x3e54 : 0x3e94] = b"\x00" * 64

    # 3. Current resume msg_id ([0x7624f0] -> looked up by 0x43fda1) at 0x43b8
    struct.pack_into("<I", buf, 0x43b8, msg_id)

    # 4. Call stack (depth=1 at 0x44ac, return_ip at 0x44b0, param=0 at 0x44b4)
    struct.pack_into("<III", buf, 0x44ac, 1, ret_ip, 0)

    sav_path = os.path.join(OUT_DIR, f"save{slot:03d}.sav")
    th_path = os.path.join(OUT_DIR, f"thumb{slot:03d}.gra")
    with open(sav_path, "wb") as f:
        f.write(buf)
    with open(th_path, "wb") as f:
        f.write(template_thumb)
    exp_s = f", party_exp={party_exp}" if party_exp is not None else ""
    print(f"  Created save{slot:03d}.sav (Slot {slot+1}): msg_id={msg_id}, ret=0x{ret_ip:06x}, route={route}{exp_s}, title={title!r}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    src_sav = os.path.join(common.PC_DIR, "save", "save000.sav")
    src_th = os.path.join(common.PC_DIR, "save", "thumb000.gra")
    template_sav = open(src_sav, "rb").read()
    template_thumb = open(src_th, "rb").read()

    # Verify all 4 target msg_ids exist uniquely in staged scenario.dat
    sf = open(os.path.join(common.WORK_DIR, "staged", "scenario.dat"), "rb").read()
    # 30,000 EXP -> Level 40 for all 9 party slots (0..8 incl. Hayaway & Ruah)
    # Affection thresholds at Ch.8 (0x6734ac..0x673810):
    #   0x1..0x7 = Pricilla(7), Kagura(7), Fel(7), Karin(10), Theresa(6), Ritte(8), Filia(8)
    #   0xC      = Ruah (>= 7 at Ch.8, > 8 for True Epilogue)
    ch8_affection = {
        0x10000001: 10,
        0x10000002: 10,
        0x10000003: 10,
        0x10000004: 10,
        0x10000005: 10,
        0x10000006: 10,
        0x10000007: 10,
        0x1000000C: 10,
    }
    ruah_affection = {0x1000000C: 10}
    targets = [
        (5, 67567, 0x001f5c, "乙女あり、遠方より来たる？",       0, None, None),
        (6, 93588, 0x0024b4, "運命の選択",                       0, 30000, ch8_affection),
        (7, 93888, 0x0026ac, "ひみつのレッスン",                  8, 30000, ruah_affection),
        (8, 95173, 0x0026ac, "ひみつのレッスン（ルーア参戦直前）", 8, 30000, ruah_affection),
    ]
    for slot, mid, ret_ip, title, route, party_exp, local_vars in targets:
        # Simulate 0x43fda1 scan from offset 0x20!
        pos = 32
        found = None
        while pos + 4 <= len(sf):
            w = struct.unpack_from("<I", sf, pos)[0]
            nw = w & 0xFF
            if nw == 0:
                pos += 4
                continue
            if (w == 0x80000307 and struct.unpack_from("<I", sf, pos + 16)[0] == mid) or \
               (w == 0x01030d02 and struct.unpack_from("<I", sf, pos + 4)[0] == mid):
                found = pos
                break
            pos += nw * 4
        assert found is not None and found >= 0x435000, f"msg_id {mid} resolved to unexpected offset {found}"
        make_save(
            template_sav, template_thumb, slot, mid, ret_ip, title, route,
            party_exp=party_exp, local_vars=local_vars,
        )

    print(f"\nTest saves written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
