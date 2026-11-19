"""
Non-destructive P_ARK201.exe patcher for Playable Ally Ruah (ch = 9).

Appends a small RWX `.ruah` PE section (VA 0x0087A000) to a copy of the original
UPX-packed P_ARK201.exe and redirects the UPX stub's final `jmp OEP` (0x008778B3)
to `_ruah_init` in `.ruah`. At launch, UPX unpacks the original game image cleanly
into RWX memory (`0x00401000..0x007DF000`), resolves all imports normally, and then
`_ruah_init` applies verified byte patches & trampolines in RAM before jumping to
the original entry point (`0x004EA43A`).

Original `P_ARK201.exe` is never modified; output is written to `pc_ruah_mod/P_ARK201_Ruah.exe`.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

RUAH_SEC_RVA = 0x47A000
RUAH_SEC_VA = 0x00400000 + RUAH_SEC_RVA  # 0x0087A000
RUAH_SEC_SIZE = 0x4000                   # 16 KB RWX section
IMAGE_BASE = 0x00400000
TEXT_BASE = 0x00401000
OEP_VA = 0x004EA43A
UPX_JMP_OEP_VA = 0x008778B3
UPX_JMP_OEP_FOFF = 0x98CB3

# Ruah's self-heal SE ID registered in data/se/common.se (B_RUA_0020.ogg = 2120)
RUAH_SELF_HEAL_SE = 2120


def unpack_exact_exe(raw_exe: bytes) -> bytes:
    """Decompress UPX NRV2E + apply UPX's exact 0x1B E8/E9 unfilter for verification."""
    pos_upx = raw_exe.find(b"UPX!")
    assert pos_upx != -1, "Expected UPX-packed P_ARK201.exe"
    _, _, _, _, _, _, _, u_len, c_len, _, _, _, _, _ = struct.unpack_from(
        "<4sBBBBIIIIIBBBB", raw_exe, pos_upx
    )
    dec = bytearray(common._nrv2e_decompress_le32(raw_exe[0x400 : 0x400 + c_len]))
    assert len(dec) == u_len, f"NRV2E size mismatch: {len(dec)} != {u_len}"

    # Exact UPX E8/E9 0x1B unfilter (0x008777FA..0x0087782E)
    edi = 0
    ecx = 0x4865
    al = (dec[edi] - 0xE8) & 0xFF
    edi += 1
    while ecx > 0:
        if al <= 1 and dec[edi] == 0x1B:
            val = struct.unpack_from("<I", dec, edi)[0]
            bl = dec[edi + 4]
            ax = (val & 0xFFFF) >> 8
            eax = (val & 0xFFFF0000) | ax
            eax = ((eax << 16) | (eax >> 16)) & 0xFFFFFFFF
            lo = eax & 0xFF
            hi = (eax >> 8) & 0xFF
            eax = (eax & 0xFFFF0000) | (lo << 8) | hi
            eax = (eax - edi) & 0xFFFFFFFF
            struct.pack_into("<I", dec, edi, eax)
            edi += 5
            ecx -= 1
            al = (bl - 0xE8) & 0xFF
        else:
            al = (dec[edi] - 0xE8) & 0xFF
            edi += 1
    return bytes(dec)


def rel32(src_va: int, dst_va: int, insn_len: int = 5) -> bytes:
    return struct.pack("<i", dst_va - (src_va + insn_len))


def jmp_rel32(src_va: int, dst_va: int) -> bytes:
    return b"\xE9" + rel32(src_va, dst_va, 5)


def call_rel32(src_va: int, dst_va: int) -> bytes:
    return b"\xE8" + rel32(src_va, dst_va, 5)


def build_ruah_section_and_patches(exact_unp: bytes):
    """
    Build the 16 KB `.ruah` section contents and list of `(va, expected_old, new_bytes)` patches.
    Every patch verifies `expected_old` against `exact_unp` before being emitted.
    """
    sec = bytearray(RUAH_SEC_SIZE)
    cursor = 0x200  # Reserve 0x000..0x1FF for `_ruah_init` boot patcher

    def alloc_data(data: bytes, align: int = 4) -> int:
        nonlocal cursor
        cursor = (cursor + align - 1) & ~(align - 1)
        va = RUAH_SEC_VA + cursor
        sec[cursor : cursor + len(data)] = data
        cursor += len(data)
        return va

    def alloc_zeros(size: int, align: int = 4) -> int:
        return alloc_data(b"\x00" * size, align=align)

    def read_unp(va: int, n: int) -> bytes:
        off = va - TEXT_BASE
        return exact_unp[off : off + n]

    # ------------------------------------------------------------------
    # 1. Allocate extended data tables & strings in `.ruah`
    # ------------------------------------------------------------------
    # Battle HUD bottom face portraits (bt_v%02d.tga): 10 slots
    g_btv_indices = alloc_data(struct.pack("<10I", 7, 0, 1, 2, 3, 4, 5, 6, 8, 9))
    g_btv_handles = alloc_zeros(10 * 4)

    # Battle party roster / turn-order priority table: 10 slots
    g_roster_order = alloc_data(struct.pack("<10I", 0, 1, 2, 3, 4, 6, 5, 7, 8, 9))

    # Victory banners & level-up cut-ins (bte_XXa, bte_XXb, cut_XX): 10 x 3 pointers & handles
    s_bte09a = alloc_data("data/manabe/戦闘終了画像/bte_09a.tga\x00".encode("cp932"))
    s_bte09b = alloc_data("data/manabe/戦闘終了画像/bte_09b.tga\x00".encode("cp932"))
    s_cut09 = alloc_data("data/manabe/戦闘終了画像/cut_09.tga\x00".encode("cp932"))
    orig_cut_paths = read_unp(0x5365A0, 9 * 12)
    g_cut_paths = alloc_data(orig_cut_paths + struct.pack("<3I", s_bte09a, s_bte09b, s_cut09))
    g_cut_handles = alloc_zeros(10 * 12)

    # Camp Status banner (st_e09.tga) & Character Sheet (ca_b09.tga / ca_c09.tga) — lazy-loaded CSprite*
    s_ste09 = alloc_data("data/campaign/ステータス/キャラ文字/st_e09.tga\x00".encode("cp932"))
    s_cab09 = alloc_data("data/campaign/キャラクターシート/キャラクター/ca_b09.tga\x00".encode("cp932"))
    s_cac09 = alloc_data("data/campaign/キャラクターシート/説明/ca_c09.tga\x00".encode("cp932"))
    g_ste09_tex = alloc_zeros(4)
    g_ste09_spr = alloc_zeros(4)
    g_ste_override = alloc_zeros(4)
    g_cab09_tex = alloc_zeros(4)
    g_cab09_spr = alloc_zeros(4)
    g_cab_override = alloc_zeros(4)
    g_cab_old_override = alloc_zeros(4)
    g_cac09_tex = alloc_zeros(4)
    g_cac09_spr = alloc_zeros(4)
    g_cac_override = alloc_zeros(4)
    g_ste09_handle = g_ste09_spr  # alias for info dict

    # Self-heal voice SE ID table (0x553498 had 9 dwords -> expand to 10)
    orig_self_heal = read_unp(0x553498, 9 * 4)
    g_self_heal_se = alloc_data(orig_self_heal + struct.pack("<I", RUAH_SELF_HEAL_SE))

    # ------------------------------------------------------------------
    # 2. Emit clean x86 trampolines in `.ruah`
    # ------------------------------------------------------------------
    def alloc_code(builder_fn) -> int:
        nonlocal cursor
        cursor = (cursor + 15) & ~15
        va = RUAH_SEC_VA + cursor
        code = builder_fn(va)
        sec[cursor : cursor + len(code)] = code
        cursor += len(code)
        return va

    # Trampoline A: Battle start EXP/level snapshot (hook at 0x40E3D0..0x40E3E9)
    # ebx = 0..8; map ebx==8 -> ch=9 (Ruah), else ch=ebx; pass ch to BOTH 0x40D340 and 0x40D360!
    def build_tramp_exp_snap(va: int) -> bytes:
        out = bytearray()
        # mov eax, ebx; cmp eax, 8; jne +5; mov eax, 9
        out += b"\x89\xD8"                  # mov eax, ebx
        out += b"\x83\xF8\x08"              # cmp eax, 8
        out += b"\x75\x05"                  # jne +5
        out += b"\xB8\x09\x00\x00\x00"      # mov eax, 9
        # push eax (save ch on stack temporarily in edx? no, edx is caller-saved; keep ch in [esp]!)
        # Actually push eax twice? Wait: original stack cleanup at 0x40E401 does `add esp, 0x1c`
        # counting: push ebx (4) + push eax (4) + push edi (4) + push eax (4) + push eax (4) + push edi (4) + push 0x515fd4 (4) = 0x1c!
        # So we MUST push exact same 3 dwords before returning to 0x40E3E9:
        #   push ch; call 0x40d340; mov edi, eax; mov eax, [edi*4 + 0x576074];
        #   mov [esi-4], eax; push eax; mov eax, [esp+4] (saved ch!); push eax; call 0x40d360; jmp 0x40e3e9
        out += b"\x50"                      # push eax (ch)  [esp] = ch
        out += call_rel32(va + len(out), 0x40D340)  # eax = map_ch_to_sheet(ch)
        out += b"\x8B\xF8"                  # mov edi, eax
        out += b"\x8B\x04\xBD" + struct.pack("<I", 0x576074)  # mov eax, [edi*4 + 0x576074]
        # Per-save EXP floor from unused local var[0x100003DC] (battle RAM 0x57593C, save offset 0x3E44):
        # 0 on normal saves; 30000 (LV 40) on high-level test saves (Slots 7-9).
        out += b"\x8B\x0D" + struct.pack("<I", 0x57593C)      # mov ecx, [0x57593C]
        out += b"\x3B\xC1"                                    # cmp eax, ecx
        out += b"\x7D\x02"                                    # jge +2
        out += b"\x8B\xC1"                                    # mov eax, ecx
        out += b"\x89\x46\xFC"                                # mov [esi - 4], eax
        out += b"\x50"                      # push eax (exp)  [esp+4] = ch
        out += b"\x8B\x44\x24\x04"          # mov eax, [esp + 4] (ch)
        out += b"\x50"                      # push eax (ch)
        out += call_rel32(va + len(out), 0x40D360)  # eax = calc_level(ch, exp)
        out += jmp_rel32(va + len(out), 0x40E3E9)
        return bytes(out)

    tramp_exp_snap = alloc_code(build_tramp_exp_snap)

    # Helper: cdecl CSprite* load_sprite(const char* path, CTexture** p_tex, CSprite** p_spr)
    # Exact vanilla sequence (0x404CB3..0x404CE3): 0x4215F0 -> GetHeight(0x48DE20) -> GetWidth(0x484F30) -> CreateSprite(0x4A2E60)
    def build_helper_load_sprite(va: int) -> bytes:
        out = bytearray()
        # push esi; push edi
        # [esp+12]=path, [esp+16]=p_tex, [esp+20]=p_spr
        out += b"\x56\x57"                  # push esi; push edi
        out += b"\x8B\x7C\x24\x14"          # mov edi, [esp+20] (p_spr)
        out += b"\x8B\x07"                  # mov eax, [edi]
        out += b"\x85\xC0"                  # test eax, eax
        j_done1 = len(out); out += b"\x75\x00"  # jne .ret
        out += b"\x8B\x74\x24\x10"          # mov esi, [esp+16] (p_tex)
        out += b"\x8B\x44\x24\x0C"          # mov eax, [esp+12] (path)
        out += b"\x56\x50"                  # push esi (p_tex); push eax (path)
        out += call_rel32(va + len(out), 0x4215F0)
        out += b"\x83\xC4\x08"              # add esp, 8
        out += b"\x8B\x0E"                  # mov ecx, [esi] (CTexture*)
        out += b"\x85\xC9"                  # test ecx, ecx
        j_fail = len(out); out += b"\x74\x00"   # je .fail
        out += b"\x57"                      # push edi (p_spr -> arg5 of CreateSprite)
        out += call_rel32(va + len(out), 0x48DE20)  # eax = tex->GetHeight()
        out += b"\x8B\x0E\x50"              # mov ecx, [esi]; push eax (arg4 = h)
        out += call_rel32(va + len(out), 0x484F30)  # eax = tex->GetWidth()
        out += b"\x8B\x0E\x50\x6A\x00\x6A\x00"      # mov ecx, [esi]; push eax (w); push 0; push 0
        out += call_rel32(va + len(out), 0x4A2E60)  # tex->CreateSprite(0,0,w,h,p_spr), callee-cleans 20B
        out += b"\x8B\x07"                  # mov eax, [edi] (CSprite*)
        j_done2 = len(out); out += b"\xEB\x00"
        off_fail = len(out)
        out[j_fail + 1] = off_fail - (j_fail + 2)
        out += b"\x33\xC0"                  # xor eax, eax
        off_ret = len(out)
        out[j_done1 + 1] = off_ret - (j_done1 + 2)
        out[j_done2 + 1] = off_ret - (j_done2 + 2)
        out += b"\x5F\x5E\xC3"              # pop edi; pop esi; ret
        return bytes(out)

    helper_load_sprite = alloc_code(build_helper_load_sprite)

    # Trampoline B: bt_v%02d.tga loader index fetch (hook at 0x40E980..0x40E985)
    # Also resets lazy-loaded Camp CSprite/CTexture handles when esi==0 (fresh battle init)!
    def build_tramp_btv_idx(va: int) -> bytes:
        out = bytearray()
        out += b"\x85\xF6"                  # test esi, esi
        j_skip = len(out); out += b"\x75\x00"
        for gva in (g_ste09_tex, g_ste09_spr, g_cab09_tex, g_cab09_spr, g_cac09_tex, g_cac09_spr):
            out += b"\xC7\x05" + struct.pack("<II", gva, 0)
        off_skip = len(out)
        out[j_skip + 1] = off_skip - (j_skip + 2)
        out += b"\x8B\x8E" + struct.pack("<I", g_btv_indices)       # mov ecx, [esi + g_btv_indices]
        out += b"\x51"                                      # push ecx
        out += jmp_rel32(va + len(out), 0x40E985)
        return bytes(out)

    tramp_btv_idx = alloc_code(build_tramp_btv_idx)

    # Trampoline C: Battle party roster priority comparison (hook at 0x417C56..0x417C5D)
    def build_tramp_roster_cmp(va: int) -> bytes:
        out = bytearray()
        # movzx ebx, word ptr [ecx]; cmp ebx, [edi*4 + g_roster_order]; jmp 0x417c5d
        out += b"\x0F\xB7\x19"
        out += b"\x3B\x1C\xBD" + struct.pack("<I", g_roster_order)
        out += jmp_rel32(va + len(out), 0x417C5D)
        return bytes(out)

    tramp_roster_cmp = alloc_code(build_tramp_roster_cmp)

    # Trampoline D: Level-up cut-in X/Y offset fetch (hook at 0x41569E..0x4156B9)
    # Preserves battle.ini cutin_xofs/cutin_yofs for ch=0..8, uses (xofs=150, yofs=0) for ch=9 (Ruah)
    def build_tramp_cut_ofs(va: int) -> bytes:
        out = bytearray()
        # Compare ebx == 9
        out += b"\x83\xFB\x09"              # cmp ebx, 9
        j_ruah_pos = len(out)
        out += b"\x74\x00"                  # je .ruah (patched below)
        # Vanilla 0..8:
        out += b"\x8B\x04\x9D" + struct.pack("<I", 0x530164)  # mov eax, [ebx*4 + 0x530164] (yofs)
        out += b"\x68\x00\x00\x80\x3F"      # push 1.0f
        out += b"\x68\x00\x00\x80\x3F"      # push 1.0f
        out += b"\x50"                      # push yofs
        out += b"\x8B\x04\x9D" + struct.pack("<I", 0x530140)  # mov eax, [ebx*4 + 0x530140] (xofs)
        out += b"\x03\xC6"                  # add eax, esi
        out += jmp_rel32(va + len(out), 0x4156B9)
        # .ruah (ch == 9): yofs = -40 (frame upper body nicely), xofs = 150
        ruah_off = len(out)
        out[j_ruah_pos + 1] = ruah_off - (j_ruah_pos + 2)
        out += b"\x68\x00\x00\x80\x3F"      # push 1.0f
        out += b"\x68\x00\x00\x80\x3F"      # push 1.0f
        out += b"\x6A\xD8"                  # push -40 (yofs)
        out += b"\x8D\x86\x96\x00\x00\x00"  # lea eax, [esi + 150] (xofs + esi)
        out += jmp_rel32(va + len(out), 0x4156B9)
        return bytes(out)

    tramp_cut_ofs = alloc_code(build_tramp_cut_ofs)

    # Trampoline E1 & E2: In-battle Status screen st_e09.tga CSprite* banner (hooks at 0x40A022 & 0x40A0A1)
    def build_tramp_ste_check(va: int) -> bytes:
        out = bytearray()
        out += b"\xC7\x05" + struct.pack("<II", g_ste_override, 0)
        out += b"\x83\xFF\x08"              # cmp edi, 8
        j_check9 = len(out); out += b"\x7F\x00"
        # Vanilla 0..8: mov eax, [ebp + edi*4 + 0x13c]; add edi, 6; jmp 0x40a035
        out += b"\x8B\x84\xBD\x3C\x01\x00\x00"
        out += b"\x83\xC7\x06"
        out += jmp_rel32(va + len(out), 0x40A035)
        off_check9 = len(out)
        out[j_check9 + 1] = off_check9 - (j_check9 + 2)
        out += b"\x83\xFF\x09"              # cmp edi, 9
        j_skip = len(out); out += b"\x75\x00"
        out += b"\x68" + struct.pack("<I", g_ste09_spr)
        out += b"\x68" + struct.pack("<I", g_ste09_tex)
        out += b"\x68" + struct.pack("<I", s_ste09)
        out += call_rel32(va + len(out), helper_load_sprite)
        out += b"\x83\xC4\x0C"              # add esp, 12
        out += b"\xA3" + struct.pack("<I", g_ste_override)
        out += b"\xBF\x0D\x00\x00\x00"      # mov edi, 13 (st_e06 coord slot = 800x64 banner)
        out += jmp_rel32(va + len(out), 0x40A035)
        off_skip = len(out)
        out[j_skip + 1] = off_skip - (j_skip + 2)
        out += jmp_rel32(va + len(out), 0x40A0AF)
        return bytes(out)

    tramp_ste_check = alloc_code(build_tramp_ste_check)

    def build_tramp_ste_get(va: int) -> bytes:
        out = bytearray()
        out += b"\xA1" + struct.pack("<I", g_ste_override)
        out += b"\x85\xC0"
        out += b"\x75\x07"
        out += b"\x8B\x84\xBD\x24\x01\x00\x00"
        out += jmp_rel32(va + len(out), 0x40A0A8)
        return bytes(out)

    tramp_ste_get = alloc_code(build_tramp_ste_get)

    # Trampolines F1..F6: Camp Character Sheet (ca_b09.tga portrait + ca_c09.tga bio card)
    def build_tramp_cab_check(va: int) -> bytes:
        out = bytearray()
        out += b"\xC7\x05" + struct.pack("<II", g_cab_override, 0)
        out += b"\x83\xFB\x09"              # cmp ebx, 9
        j_ruah = len(out); out += b"\x74\x00"
        out += b"\x8B\x84\x9F\xB8\x00\x00\x00\x43"  # mov eax, [edi+ebx*4+0xb8]; inc ebx
        out += jmp_rel32(va + len(out), 0x4048CA)
        off_r = len(out)
        out[j_ruah + 1] = off_r - (j_ruah + 2)
        out += b"\x68" + struct.pack("<I", g_cab09_spr)
        out += b"\x68" + struct.pack("<I", g_cab09_tex)
        out += b"\x68" + struct.pack("<I", s_cab09)
        out += call_rel32(va + len(out), helper_load_sprite)
        out += b"\x83\xC4\x0C"
        out += b"\xA3" + struct.pack("<I", g_cab_override)
        out += b"\xBB\x04\x00\x00\x00"      # mov ebx, 4 (ca_b03 640x640 portrait rect)
        out += jmp_rel32(va + len(out), 0x4048CA)
        return bytes(out)

    tramp_cab_check = alloc_code(build_tramp_cab_check)

    def build_tramp_cab_get(va: int) -> bytes:
        out = bytearray()
        out += b"\x8B\x15" + struct.pack("<I", g_cab_override)
        out += b"\x85\xD2"
        out += b"\x75\x07"
        out += b"\x8B\x94\x9F\xB4\x00\x00\x00"
        out += jmp_rel32(va + len(out), 0x40495B)
        return bytes(out)

    tramp_cab_get = alloc_code(build_tramp_cab_get)

    def build_tramp_cab_old_check(va: int) -> bytes:
        out = bytearray()
        out += b"\x50"                      # push eax (save slide timer 0x164(%edi)!)
        out += b"\xC7\x05" + struct.pack("<II", g_cab_old_override, 0)
        out += b"\x8B\x9F\x60\x01\x00\x00"  # mov ebx, [edi+0x160]
        out += b"\x83\xFB\x09"              # cmp ebx, 9
        j_ruah = len(out); out += b"\x74\x00"
        out += b"\x43"                      # inc ebx
        out += b"\x8B\x84\x9F\xB4\x00\x00\x00"  # mov eax, [edi+ebx*4+0xb4]
        j_done = len(out); out += b"\xEB\x00"
        off_r = len(out)
        out[j_ruah + 1] = off_r - (j_ruah + 2)
        out += b"\x68" + struct.pack("<I", g_cab09_spr)
        out += b"\x68" + struct.pack("<I", g_cab09_tex)
        out += b"\x68" + struct.pack("<I", s_cab09)
        out += call_rel32(va + len(out), helper_load_sprite)
        out += b"\x83\xC4\x0C"
        out += b"\xA3" + struct.pack("<I", g_cab_old_override)
        out += b"\xBB\x04\x00\x00\x00"      # mov ebx, 4
        off_d = len(out)
        out[j_done + 1] = off_d - (j_done + 2)
        out += b"\x5A"                      # pop edx (restore slide timer)
        out += b"\x33\xC9\x85\xD2"          # xor ecx, ecx; test edx, edx (sets flags for 0x40498B setle cl!)
        out += jmp_rel32(va + len(out), 0x40498B)
        return bytes(out)

    tramp_cab_old_check = alloc_code(build_tramp_cab_old_check)

    def build_tramp_cab_old_get(va: int) -> bytes:
        out = bytearray()
        out += b"\x8B\x15" + struct.pack("<I", g_cab_old_override)
        out += b"\x85\xD2"
        out += b"\x75\x07"
        out += b"\x8B\x94\x9F\xB4\x00\x00\x00"
        out += jmp_rel32(va + len(out), 0x404A34)
        return bytes(out)

    tramp_cab_old_get = alloc_code(build_tramp_cab_old_get)

    def build_tramp_cac_check(va: int) -> bytes:
        out = bytearray()
        out += b"\xC7\x05" + struct.pack("<II", g_cac_override, 0)
        out += b"\x83\xFB\x09"              # cmp ebx, 9
        j_ruah = len(out); out += b"\x74\x00"
        out += b"\x8B\x84\x9F\xDC\x00\x00\x00\x83\xC3\x0A"  # mov eax, [edi+ebx*4+0xdc]; add ebx, 10
        out += jmp_rel32(va + len(out), 0x404A54)
        off_r = len(out)
        out[j_ruah + 1] = off_r - (j_ruah + 2)
        out += b"\x68" + struct.pack("<I", g_cac09_spr)
        out += b"\x68" + struct.pack("<I", g_cac09_tex)
        out += b"\x68" + struct.pack("<I", s_cac09)
        out += call_rel32(va + len(out), helper_load_sprite)
        out += b"\x83\xC4\x0C"
        out += b"\xA3" + struct.pack("<I", g_cac_override)
        out += b"\xBB\x0D\x00\x00\x00"      # mov ebx, 13 (ca_c03 400x560 bio rect)
        out += jmp_rel32(va + len(out), 0x404A54)
        return bytes(out)

    tramp_cac_check = alloc_code(build_tramp_cac_check)

    def build_tramp_cac_get(va: int) -> bytes:
        out = bytearray()
        out += b"\xA1" + struct.pack("<I", g_cac_override)
        out += b"\x85\xC0"
        out += b"\x75\x07"
        out += b"\x8B\x84\x9F\xB4\x00\x00\x00"
        out += jmp_rel32(va + len(out), 0x404AC7)
        return bytes(out)

    tramp_cac_get = alloc_code(build_tramp_cac_get)

    # 2h. Fix 0x04000102(-1) at 0x447730: only destroy script-owned objects (id > 0 and layer < 0x0A)
    #     instead of calling 0x460EC0 which wipes system UI overlays (SYS_ADV_WINDOW, SYS_ADV_WIN_BTN1..7).
    def build_tramp_free_script_objs(va: int) -> bytes:
        out = bytearray()
        out += b"\x53\x56\x57\x55"                  # push ebx; push esi; push edi; push ebp
        out += b"\xA1" + struct.pack("<I", 0x66D220) # mov eax, [0x66D220]
        out += b"\x85\xC0"                          # test eax, eax
        jz_done1 = len(out); out += b"\x0F\x84\x00\x00\x00\x00"  # jz .done
        out += b"\x8B\x35" + struct.pack("<I", 0x66CA18)         # mov esi, [0x66CA18]
        out += b"\x85\xF6"                          # test esi, esi
        jz_done2 = len(out); out += b"\x0F\x84\x00\x00\x00\x00"  # jz .done
        out += b"\x4E"                              # dec esi

        off_loop = len(out)
        # Defensive clamp in case 0x460C20 shrinks count by >1:
        out += b"\x3B\x35" + struct.pack("<I", 0x66CA18)         # cmp esi, [0x66CA18]
        jb_ok = len(out); out += b"\x72\x00"                     # jb .in_bounds
        out += b"\x8B\x35" + struct.pack("<I", 0x66CA18)         # mov esi, [0x66CA18]
        jmp_next0 = len(out); out += b"\xEB\x00"                 # jmp .next

        off_in_bounds = len(out)
        out[jb_ok + 1] = off_in_bounds - (jb_ok + 2)
        out += b"\x8B\x3C\xB5" + struct.pack("<I", 0x66CA20)     # mov edi, [esi*4 + 0x66CA20]
        out += b"\x85\xFF"                          # test edi, edi
        jz_next1 = len(out); out += b"\x74\x00"     # jz .next
        out += b"\x83\x7F\x04\x00"                  # cmp dword ptr [edi+4], 0
        jle_next2 = len(out); out += b"\x7E\x00"    # jle .next (skips id==0 & auto handles >=0x80000000)
        out += b"\x83\x7F\x18\x0A"                  # cmp dword ptr [edi+0x18], 0x0A
        jae_next3 = len(out); out += b"\x73\x00"    # jae .next (skips system UI layers >= 10)
        out += b"\x57"                              # push edi
        out += call_rel32(va + len(out), 0x460C20)  # call 0x460C20 (cdecl: free CGraphic* and remove)
        out += b"\x83\xC4\x04"                      # add esp, 4
        # After 4 pushes (+16), original [esp+0xE8C] (flags ptr) is at [esp+0xE9C]
        out += b"\x8B\x94\x24" + struct.pack("<I", 0xE9C)        # mov edx, [esp+0xE9C]
        out += b"\xF6\x02\x01"                      # test byte ptr [edx], 1
        jz_next4 = len(out); out += b"\x74\x00"     # jz .next
        out += b"\x8B\x0D" + struct.pack("<I", 0x7638C8)         # mov ecx, [0x7638C8]
        out += b"\x85\xC9"                          # test ecx, ecx
        jz_next5 = len(out); out += b"\x74\x00"     # jz .next
        out += b"\x57"                              # push edi
        out += call_rel32(va + len(out), 0x463590)  # call 0x463590 (__thiscall ret 4)

        off_next = len(out)
        for jp in (jmp_next0, jz_next1, jle_next2, jae_next3, jz_next4, jz_next5):
            rel = off_next - (jp + 2)
            assert -128 <= rel <= 127
            out[jp + 1] = rel & 0xFF
        out += b"\x4E"                              # dec esi
        jns_loop = len(out); out += b"\x0F\x89\x00\x00\x00\x00"  # jns .loop
        struct.pack_into("<i", out, jns_loop + 2, off_loop - (jns_loop + 6))

        off_done = len(out)
        for jp in (jz_done1, jz_done2):
            struct.pack_into("<i", out, jp + 2, off_done - (jp + 6))
        out += b"\x5D\x5F\x5E\x5B"                  # pop ebp; pop edi; pop esi; pop ebx
        out += jmp_rel32(va + len(out), 0x447AE4)   # jmp 0x447AE4
        return bytes(out)

    tramp_free_script_objs = alloc_code(build_tramp_free_script_objs)

    # 2i. Null-pointer guard at 0x463290 (arg2 CGraphic* -> edi): prevents crash at 0x4632BE [edi+0x7328]
    def build_tramp_move_sprite_guard(va: int) -> bytes:
        out = bytearray()
        out += b"\x83\x7C\x24\x08\x00"              # cmp dword ptr [esp+0x08], 0
        out += b"\x75\x05"                          # jne .ok (+5)
        out += b"\x33\xC0"                          # xor eax, eax
        out += b"\xC2\x18\x00"                      # ret 0x18
        out += b"\x51"                              # push ecx
        out += b"\x8B\x44\x24\x1C"                  # mov eax, dword ptr [esp+0x1C]
        out += jmp_rel32(va + len(out), 0x463295)   # jmp 0x463295
        return bytes(out)

    tramp_move_sprite_guard = alloc_code(build_tramp_move_sprite_guard)

    # ------------------------------------------------------------------
    # 3. Inline code replacements (map_ch_to_sheet & cover voice dispatcher)
    # ------------------------------------------------------------------
    # map_ch_to_sheet(ch) at 0x40D340..0x40D35F (32 bytes available; uses 28 bytes):
    #   ch < 0 || ch > 9 -> -1
    #   ch == 8 (Teresa) -> 5
    #   ch == 9 (Ruah)   -> 8
    #   ch == 0..7       -> ch
    map_ch_code = bytes([
        0x8B, 0x44, 0x24, 0x04,       # mov eax, [esp+4]
        0x85, 0xC0,                   # test eax, eax
        0x7C, 0x13,                   # jl .neg (+19 -> offset 27)
        0x83, 0xF8, 0x08,             # cmp eax, 8
        0x7C, 0x12,                   # jl .ret (+18 -> offset 31)
        0x74, 0x07,                   # je .teresa (+7 -> offset 22)
        0x83, 0xF8, 0x09,             # cmp eax, 9
        0x75, 0x07,                   # jne .neg (+7 -> offset 27)
        0x48,                         # dec eax  (9 -> 8)
        0xC3,                         # ret
        # offset 22 (.teresa):
        0xB8, 0x05, 0x00, 0x00, 0x00, # mov eax, 5
        0xC3,                         # ret (Wait: offset 27! Let's compute exact!)
    ])
    # Recompute exact jump displacements cleanly:
    # 00: 8B 44 24 04  mov eax, [esp+4]   (4)
    # 04: 85 C0        test eax, eax      (2)
    # 06: 7C 14        jl .neg (28)       (2) -> 28 - 8 = 20 = 0x14
    # 08: 83 F8 08     cmp eax, 8         (3)
    # 0B: 7C 14        jl .ret (31)       (2) -> 31 - 13 = 18 = 0x12
    # 0D: 74 07        je .teresa (22)    (2) -> 22 - 15 = 7
    # 0F: 83 F8 09     cmp eax, 9         (3)
    # 12: 75 08        jne .neg (28)      (2) -> 28 - 20 = 8
    # 14: 48           dec eax            (1)
    # 15: C3           ret                (1)
    # 16 (22): B8 05 00 00 00 mov eax, 5  (5)
    # 1B (27): C3      ret                (1)
    # 1C (28): 83 C8 FF or eax, -1        (3)
    # 1F (31): C3      ret                (1)
    map_ch_code = bytes([
        0x8B, 0x44, 0x24, 0x04,
        0x85, 0xC0,
        0x7C, 0x14,
        0x83, 0xF8, 0x08,
        0x7C, 0x12,
        0x74, 0x07,
        0x83, 0xF8, 0x09,
        0x75, 0x08,
        0x48,
        0xC3,
        0xB8, 0x05, 0x00, 0x00, 0x00,
        0xC3,
        0x83, 0xC8, 0xFF,
        0xC3,
    ])
    assert len(map_ch_code) == 32

    # Cover / Covered battle voice dispatcher at 0x40D3D0 (originally 0x269 bytes -> 58 bytes universal formula!)
    # Input: eax = partner ch, ecx = actor ch, edx = 0 (coverer: 11000+ecx*100+eax) or !=0 (covered: 12000+ecx*100+eax)
    def build_cover_voice(va: int) -> bytes:
        out = bytearray()
        # Bounds check: 0 <= eax <= 9 and 0 <= ecx <= 9
        out += b"\x83\xF8\x09"              # cmp eax, 9
        j1 = len(out); out += b"\x77\x00"   # ja .ret (unsigned handles <0 and >9!)
        out += b"\x83\xF9\x09"              # cmp ecx, 9
        j2 = len(out); out += b"\x77\x00"   # ja .ret
        # test edx, edx; jne .covered
        out += b"\x85\xD2"                  # test edx, edx
        j_cov = len(out); out += b"\x75\x00"
        # Coverer (edx == 0): skip if eax == ecx, or (ecx == 5 && eax == 4)
        out += b"\x3B\xC1"                  # cmp eax, ecx
        j3 = len(out); out += b"\x74\x00"   # je .ret
        out += b"\x83\xF9\x05"              # cmp ecx, 5
        out += b"\x75\x05"                  # jne +5
        out += b"\x83\xF8\x04"              # cmp eax, 4
        j4 = len(out); out += b"\x74\x00"   # je .ret
        # eax = 11000 + ecx * 100 + eax
        out += b"\x6B\xC9\x64"              # imul ecx, ecx, 100
        out += b"\x8D\x84\x08" + struct.pack("<I", 11000)  # lea eax, [eax + ecx + 11000]
        j_play = len(out); out += b"\xEB\x00"
        # .covered (edx != 0): eax = 12000 + ecx * 100 + eax
        off_cov = len(out)
        out[j_cov + 1] = off_cov - (j_cov + 2)
        out += b"\x6B\xC9\x64"              # imul ecx, ecx, 100
        out += b"\x8D\x84\x08" + struct.pack("<I", 12000)  # lea eax, [eax + ecx + 12000]
        # .play: push 0x7f; push eax; call 0x424890; add esp, 8; ret
        off_play = len(out)
        out[j_play + 1] = off_play - (j_play + 2)
        out += b"\x6A\x7F"                  # push 0x7f
        out += b"\x50"                      # push eax
        out += call_rel32(va + len(out), 0x424890)
        out += b"\x83\xC4\x08"              # add esp, 8
        off_ret = len(out)
        for jp in (j1, j2, j3, j4):
            out[jp + 1] = off_ret - (jp + 2)
        out += b"\xC3"                      # ret
        return bytes(out)

    cover_voice_code = build_cover_voice(0x40D3D0)

    # ------------------------------------------------------------------
    # 4. Complete list of verified in-memory patches (VA, old_bytes, new_bytes)
    # ------------------------------------------------------------------
    patches = [
        # --- Group 1: Core Character Sheet & EXP/Level Persistence ---
        # 1a. map_ch_to_sheet(ch): 0..7->0..7, 8->5 (Teresa), 9->8 (Ruah)
        (0x40D340, read_unp(0x40D340, 32), map_ch_code),

        # 1b. Battle start EXP/level snapshot: hook loop body + extend loop bound to 9 slots (0..8)
        (0x40E3D0, bytes.fromhex("53e86aefffff8bf88b04bd7460570050578946fce877efffff"),
         jmp_rel32(0x40E3D0, tramp_exp_snap) + b"\x90" * 20),
        (0x40E408, bytes.fromhex("81fe94695700"), bytes.fromhex("81fea4695700")),  # cmp esi, 0x5769A4

        # 1c. Battle end EXP writeback: cmp ax, 8 -> cmp ax, 9
        (0x40FBC4, bytes.fromhex("663d0800"), bytes.fromhex("663d0900")),

        # --- Group 2: Battle Party Roster, HUD, Status & Victory Cut-ins ---
        # 2a. Battle party roster priority list: use 10-slot g_roster_order & loop edi <= 9
        (0x417C56, bytes.fromhex("0fb7193b5cbc14"),
         jmp_rel32(0x417C56, tramp_roster_cmp) + b"\x90\x90"),
        (0x417C90, bytes.fromhex("83ff08"), bytes.fromhex("83ff09")),

        # 2b. Battle unit HUD slot assignment: cmp dx, 8 -> cmp dx, 9
        (0x41CBAA, bytes.fromhex("6683fa08"), bytes.fromhex("6683fa09")),

        # 2c. Battle status card bt_a%02d.tga: cmp eax, 8 -> cmp eax, 9
        (0x431419, bytes.fromhex("83f808"), bytes.fromhex("83f809")),

        # 2d. Battle bottom face portrait bt_v%02d.tga: 10-slot index & handle table
        (0x40E980, bytes.fromhex("8b4c341451"), jmp_rel32(0x40E980, tramp_btv_idx)),
        (0x40E994, bytes.fromhex("8d86fcf45900"), b"\x8D\x86" + struct.pack("<I", g_btv_handles)),
        (0x40E9AB, bytes.fromhex("83fe20"), bytes.fromhex("83fe24")),  # 10 * 4 - 4 = 0x24
        (0x430E93, bytes.fromhex("83ff08"), bytes.fromhex("83ff09")),
        (0x430EC6, bytes.fromhex("8b04bdfcf45900"), b"\x8B\x04\xBD" + struct.pack("<I", g_btv_handles)),

        # 2e. Victory banner (bte_XXa/b) & level-up cut-in (cut_XX): 10-slot tables
        (0x40F160, bytes.fromhex("8b96a0655300"), b"\x8B\x96" + struct.pack("<I", g_cut_paths)),
        (0x40F166, bytes.fromhex("8d8e50f55900"), b"\x8D\x8E" + struct.pack("<I", g_cut_handles)),
        (0x40F17C, bytes.fromhex("83fe6c"), bytes.fromhex("83fe78")),  # 10 * 12 = 0x78
        (0x40FD92, bytes.fromhex("6683bc0e1803000008"), bytes.fromhex("6683bc0e1803000009")),
        (0x4101E9, bytes.fromhex("83ff08"), bytes.fromhex("83ff09")),
        (0x41029B, bytes.fromhex("8b0c8d50f55900"), b"\x8B\x0C\x8D" + struct.pack("<I", g_cut_handles)),
        (0x412EF4, bytes.fromhex("83f808"), bytes.fromhex("83f809")),
        (0x412F7B, bytes.fromhex("83fa08"), bytes.fromhex("83fa09")),
        (0x415495, bytes.fromhex("83fb08"), bytes.fromhex("83fb09")),
        (0x41569E, bytes.fromhex("8b049d64015300680000803f680000803f508b049d4001530003c6"),
         jmp_rel32(0x41569E, tramp_cut_ofs) + b"\x90" * 22),
        (0x4156BD, bytes.fromhex("8b048558f55900"), b"\x8B\x04\x85" + struct.pack("<I", g_cut_handles + 8)),

        # 2f. In-battle Status screen: st_e09.tga CSprite* banner + allow ch=9 in [ecx+0x1874]
        (0x40A022, bytes.fromhex("83ff080f8f840000008b84bd3c01000083c706"),
         jmp_rel32(0x40A022, tramp_ste_check) + b"\x90" * 14),
        (0x40A0A1, bytes.fromhex("8b84bd24010000"),
         jmp_rel32(0x40A0A1, tramp_ste_get) + b"\x90\x90"),
        (0x40A484, bytes.fromhex("663d0800"), bytes.fromhex("663d0900")),

        # 2g. Camp Character Sheet (CHR.STATUS): cycle 0..9 (mod 10) + ca_b09.tga & ca_c09.tga CSprite*
        (0x409DC8, bytes.fromhex("b909000000"), bytes.fromhex("b90a000000")),
        (0x409E0F, bytes.fromhex("83ff09"), bytes.fromhex("83ff0a")),
        (0x409E66, bytes.fromhex("83c008"), bytes.fromhex("83c009")),
        (0x409E6A, bytes.fromhex("b909000000"), bytes.fromhex("b90a000000")),
        (0x409EAF, bytes.fromhex("83ff09"), bytes.fromhex("83ff0a")),
        (0x4048C2, bytes.fromhex("8b849fb800000043"),
         jmp_rel32(0x4048C2, tramp_cab_check) + b"\x90" * 3),
        (0x404954, bytes.fromhex("8b949fb4000000"),
         jmp_rel32(0x404954, tramp_cab_get) + b"\x90\x90"),
        (0x404979, bytes.fromhex("8b9f6001000033c94385c08b849fb4000000"),
         jmp_rel32(0x404979, tramp_cab_old_check) + b"\x90" * 13),
        (0x404A2D, bytes.fromhex("8b949fb4000000"),
         jmp_rel32(0x404A2D, tramp_cab_old_get) + b"\x90\x90"),
        (0x404A4A, bytes.fromhex("8b849fdc00000083c30a"),
         jmp_rel32(0x404A4A, tramp_cac_check) + b"\x90" * 5),
        (0x404AC0, bytes.fromhex("8b849fb4000000"),
         jmp_rel32(0x404AC0, tramp_cac_get) + b"\x90\x90"),

        # --- Group 3: 3D Model Flags, Costume, Retire, Doppelganger & Battle Voices ---
        # 3a. Costume suffix (_H/_B), RETIRE_3, 3D model X-scale flip, effect flag
        (0x40EC0D, bytes.fromhex("6683bc371803000008"), bytes.fromhex("6683bc371803000009")),
        (0x41180E, bytes.fromhex("6683bc071803000008"), bytes.fromhex("6683bc071803000009")),
        (0x4148C8, bytes.fromhex("6683b81803000008"), bytes.fromhex("6683b81803000009")),
        (0x43BF6B, bytes.fromhex("6683bc071803000008"), bytes.fromhex("6683bc071803000009")),

        # 3b. Enemy doppelganger target highlight (8 identical checks)
        (0x43567C, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),
        (0x43570C, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),
        (0x435B0C, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),
        (0x435B9C, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),
        (0x435FEC, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),
        (0x43607C, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),
        (0x4364EC, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),
        (0x43657C, bytes.fromhex("6683bc011803000008"), bytes.fromhex("6683bc011803000009")),

        # 3c. Battle voices: victory (10000+ch), KO (10100+ch), pinch (10200+ch), start (10400+ch)
        (0x40F538, bytes.fromhex("83f808"), bytes.fromhex("83f809")),
        (0x4118A0, bytes.fromhex("83f808"), bytes.fromhex("83f809")),
        (0x4128E8, bytes.fromhex("83f808"), bytes.fromhex("83f809")),
        (0x412D38, bytes.fromhex("83f808"), bytes.fromhex("83f809")),

        # 3d. Cover / Covered voice dispatcher (11000 + actor*100 + target, 12000 + actor*100 + target)
        (0x40D3D0, read_unp(0x40D3D0, len(cover_voice_code)), cover_voice_code),

        # 3e. Heal reaction voices (13000 + target*100 + healer) & self-heal replacement table
        (0x43468F, bytes.fromhex("83fd08"), bytes.fromhex("83fd09")),
        (0x434698, bytes.fromhex("83ff08"), bytes.fromhex("83ff09")),
        (0x4346C5, bytes.fromhex("83fb08"), bytes.fromhex("83fb09")),
        (0x43488F, bytes.fromhex("83f808"), bytes.fromhex("83f809")),
        (0x43489C, bytes.fromhex("3b0c8598345500"), b"\x3B\x0C\x85" + struct.pack("<I", g_self_heal_se)),

        # --- Group 4: Script Engine Safety & PS2 Port Compatibility ---
        # 4a. 0x04000102(-1): free only script-owned objects (id > 0 & layer < 0x0A), keeping UI panels intact
        (0x447730, bytes.fromhex("e88b970100"), jmp_rel32(0x447730, tramp_free_script_objs)),
        # 4b. Null-pointer guard on sprite move/manipulate entry (0x463290)
        (0x463290, bytes.fromhex("518b44241c"), jmp_rel32(0x463290, tramp_move_sprite_guard)),
    ]

    # Verify EVERY expected_old matches exact unpacked game image!
    for va, old_b, new_b in patches:
        assert len(old_b) == len(new_b), f"Length mismatch at 0x{va:06x}: {len(old_b)} vs {len(new_b)}"
        actual = read_unp(va, len(old_b))
        assert actual == old_b, (
            f"Pre-patch byte mismatch at VA 0x{va:06x}!\n"
            f"  expected: {old_b.hex()}\n"
            f"  actual  : {actual.hex()}"
        )

    # ------------------------------------------------------------------
    # 5. Pack patch table into `.ruah` and emit `_ruah_init` at 0x0087A000
    # ------------------------------------------------------------------
    tbl = bytearray()
    for va, _, new_b in patches:
        tbl += struct.pack("<II", va, len(new_b))
        tbl += new_b
    tbl += struct.pack("<II", 0, 0)  # terminator
    patch_tbl_va = alloc_data(bytes(tbl), align=4)

    # Emit `_ruah_init` at RUAH_SEC_VA (offset 0x000 in `.ruah`):
    #   pushad; pushfd; cld
    #   mov esi, patch_tbl_va
    # .loop:
    #   lodsd                ; eax = dst_va
    #   test eax, eax
    #   jz .done
    #   mov edi, eax
    #   lodsd                ; eax = len
    #   mov ecx, eax
    #   rep movsb
    #   jmp .loop
    # .done:
    #   popfd; popad
    #   jmp OEP_VA (0x004EA43A)
    init = bytearray()
    init += b"\x60\x9C\xFC"                             # pushad; pushfd; cld
    init += b"\xBE" + struct.pack("<I", patch_tbl_va)   # mov esi, patch_tbl_va
    loop_off = len(init)
    init += b"\xAD"                                     # lodsd (eax = dst_va)
    init += b"\x85\xC0"                                 # test eax, eax
    j_done = len(init)
    init += b"\x74\x00"                                 # jz .done
    init += b"\x8B\xF8"                                 # mov edi, eax
    init += b"\xAD"                                     # lodsd (eax = len)
    init += b"\x8B\xC8"                                 # mov ecx, eax
    init += b"\xF3\xA4"                                 # rep movsb
    init += b"\xEB" + struct.pack("<b", loop_off - (len(init) + 2))
    done_off = len(init)
    init[j_done + 1] = done_off - (j_done + 2)
    init += b"\x9D\x61"                                 # popfd; popad
    init += jmp_rel32(RUAH_SEC_VA + len(init), OEP_VA)  # jmp 0x004EA43A
    assert len(init) <= 0x200
    sec[0 : len(init)] = init

    assert cursor <= RUAH_SEC_SIZE, f".ruah section overflow: 0x{cursor:x} > 0x{RUAH_SEC_SIZE:x}"
    info = {
        "used_bytes": cursor,
        "patch_count": len(patches),
        "patch_tbl_va": patch_tbl_va,
        "tramps": {
            "init": RUAH_SEC_VA,
            "exp_snap": tramp_exp_snap,
            "btv_idx": tramp_btv_idx,
            "roster_cmp": tramp_roster_cmp,
            "cut_ofs": tramp_cut_ofs,
            "ste_check": tramp_ste_check,
            "ste_get": tramp_ste_get,
            "free_script_objs": tramp_free_script_objs,
            "move_sprite_guard": tramp_move_sprite_guard,
            "cover_voice": 0x40D3D0,
        },
        "tables": {
            "g_btv_indices": g_btv_indices,
            "g_btv_handles": g_btv_handles,
            "g_roster_order": g_roster_order,
            "g_cut_paths": g_cut_paths,
            "g_cut_handles": g_cut_handles,
            "g_ste09_handle": g_ste09_handle,
            "g_self_heal_se": g_self_heal_se,
        },
    }
    return bytes(sec), patches, info


def patch_pe_exe(src_exe_path: str, out_exe_path: str):
    with open(src_exe_path, "rb") as f:
        raw = bytearray(f.read())

    # Sanity-check original UPX PE layout
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    nsec = struct.unpack_from("<H", raw, pe + 6)[0]
    ohsz = struct.unpack_from("<H", raw, pe + 20)[0]
    sec_off = pe + 24 + ohsz
    assert nsec == 3, f"Expected 3 sections in P_ARK201.exe, got {nsec}"
    assert raw[UPX_JMP_OEP_FOFF : UPX_JMP_OEP_FOFF + 5] == bytes.fromhex("e9822bc7ff"), (
        f"Unexpected bytes at UPX OEP jump: {raw[UPX_JMP_OEP_FOFF:UPX_JMP_OEP_FOFF+5].hex()}"
    )
    assert raw[sec_off + 3 * 40 : sec_off + 4 * 40] == b"\x00" * 40, "Section header slot 3 not empty"

    exact_unp = unpack_exact_exe(bytes(raw))
    ruah_sec, patches, info = build_ruah_section_and_patches(exact_unp)

    # Append `.ruah` section at file end (0x9A000, already 0x200-aligned)
    raw_ptr = len(raw)
    assert raw_ptr % 0x200 == 0
    raw.extend(ruah_sec)

    # Write 4th section header `.ruah` (RWX: IMAGE_SCN_CNT_CODE | INITIALIZED_DATA | MEM_EXECUTE | READ | WRITE)
    sec_hdr = struct.pack(
        "<8sIIIIIIHHI",
        b".ruah\x00\x00\x00",
        RUAH_SEC_SIZE,   # VirtualSize
        RUAH_SEC_RVA,    # VirtualAddress (0x47A000 -> VA 0x0087A000)
        RUAH_SEC_SIZE,   # SizeOfRawData
        raw_ptr,         # PointerToRawData
        0, 0, 0, 0,
        0xE0000060,      # Characteristics (RWX code + initialized data)
    )
    raw[sec_off + 3 * 40 : sec_off + 4 * 40] = sec_hdr

    # Update NumberOfSections (3 -> 4), SizeOfImage (0x47A000 -> 0x47E000), zero CheckSum
    struct.pack_into("<H", raw, pe + 6, 4)
    struct.pack_into("<I", raw, pe + 24 + 56, RUAH_SEC_RVA + RUAH_SEC_SIZE)
    struct.pack_into("<I", raw, pe + 24 + 64, 0)

    # Redirect UPX stub's final `jmp 0x004EA43A` (0x008778B3) -> `jmp 0x0087A000`
    raw[UPX_JMP_OEP_FOFF : UPX_JMP_OEP_FOFF + 5] = jmp_rel32(UPX_JMP_OEP_VA, RUAH_SEC_VA)

    os.makedirs(os.path.dirname(out_exe_path), exist_ok=True)
    with open(out_exe_path, "wb") as f:
        f.write(raw)

    return exact_unp, ruah_sec, patches, info


def simulate_and_verify(out_exe_path: str, verbose: bool = False):
    """Simulate UPX unpack + `_ruah_init` execution and verify every patched instruction."""
    with open(out_exe_path, "rb") as f:
        raw = f.read()
    pe = struct.unpack_from("<I", raw, 0x3C)[0]
    nsec = struct.unpack_from("<H", raw, pe + 6)[0]
    ohsz = struct.unpack_from("<H", raw, pe + 20)[0]
    sec_off = pe + 24 + ohsz
    assert nsec == 4
    nm, vsz, rva, rsz, rptr, _, _, _, _, flg = struct.unpack_from("<8sIIIIIIHHI", raw, sec_off + 3 * 40)
    assert nm.rstrip(b"\x00") == b".ruah" and rva == RUAH_SEC_RVA and (flg & 0xE0000000) == 0xE0000000
    ruah_sec = raw[rptr : rptr + rsz]

    # Verify UPX stub jump target == 0x0087A000
    jmp_bytes = raw[UPX_JMP_OEP_FOFF : UPX_JMP_OEP_FOFF + 5]
    assert jmp_bytes[0] == 0xE9
    rel = struct.unpack_from("<i", jmp_bytes, 1)[0]
    assert UPX_JMP_OEP_VA + 5 + rel == RUAH_SEC_VA

    # Simulate `_ruah_init` patch loop over exact unpacked memory
    unp = bytearray(unpack_exact_exe(raw))
    assert ruah_sec[0:4] == b"\x60\x9C\xFC\xBE"
    tbl_va = struct.unpack_from("<I", ruah_sec, 4)[0]
    off = tbl_va - RUAH_SEC_VA
    applied = 0
    while True:
        dst_va, ln = struct.unpack_from("<II", ruah_sec, off)
        off += 8
        if dst_va == 0:
            break
        payload = ruah_sec[off : off + ln]
        off += ln
        uoff = dst_va - TEXT_BASE
        assert 0 <= uoff and uoff + ln <= len(unp), f"Patch VA out of range: 0x{dst_va:06x}"
        unp[uoff : uoff + ln] = payload
        applied += 1

    # Verify `_ruah_init` ends with jmp OEP (0x004EA43A)
    e9_pos = ruah_sec.find(b"\x9D\x61\xE9", 0, 0x40)
    assert e9_pos != -1
    oep_rel = struct.unpack_from("<i", ruah_sec, e9_pos + 3)[0]
    assert RUAH_SEC_VA + e9_pos + 2 + 5 + oep_rel == OEP_VA

    if verbose:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            md = Cs(CS_ARCH_X86, CS_MODE_32)
            print("=== Disassembly of _ruah_init (0x0087A000) ===")
            for ins in md.disasm(ruah_sec[:e9_pos + 7], RUAH_SEC_VA):
                print(f"  0x{ins.address:08x}: {ins.mnemonic:7s} {ins.op_str}")
            print("=== Disassembly of patched map_ch_to_sheet (0x40D340) ===")
            for ins in md.disasm(bytes(unp[0x40D340 - TEXT_BASE : 0x40D360 - TEXT_BASE]), 0x40D340):
                print(f"  0x{ins.address:08x}: {ins.mnemonic:7s} {ins.op_str}")
            print("=== Disassembly of patched cover_voice (0x40D3D0) ===")
            for ins in md.disasm(bytes(unp[0x40D3D0 - TEXT_BASE : 0x40D410 - TEXT_BASE]), 0x40D3D0):
                print(f"  0x{ins.address:08x}: {ins.mnemonic:7s} {ins.op_str}")
                if ins.mnemonic == "ret":
                    break
            for name, hook_va in (
                ("tramp_exp_snap", 0x40E3D0),
                ("tramp_free_script_objs", 0x447730),
                ("tramp_move_sprite_guard", 0x463290),
            ):
                rel_j = struct.unpack_from("<i", unp, hook_va - TEXT_BASE + 1)[0]
                t_va = hook_va + 5 + rel_j
                t_off = t_va - RUAH_SEC_VA
                print(f"=== Disassembly of {name} (0x{t_va:08x}, hooked from 0x{hook_va:08x}) ===")
                for ins in md.disasm(ruah_sec[t_off : t_off + 0x90], t_va):
                    print(f"  0x{ins.address:08x}: {ins.mnemonic:7s} {ins.op_str}")
                    if ins.mnemonic == "jmp" and (
                        "0x447ae4" in ins.op_str or name != "tramp_free_script_objs"
                    ):
                        break
        except ImportError:
            pass
    return applied


def main():
    src_exe = os.path.join(common.PC_DIR, "P_ARK201.exe")
    out_exe = os.path.join(common.MOD_OUT_DIR, "P_ARK201_Ruah.exe")
    if not os.path.exists(src_exe):
        raise FileNotFoundError(f"Original P_ARK201.exe not found at {src_exe}")

    _, _, patches, info = patch_pe_exe(src_exe, out_exe)
    applied = simulate_and_verify(out_exe, verbose=("--verbose" in sys.argv))
    print(
        f"Built {out_exe} ({os.path.getsize(out_exe):,} bytes): "
        f"{applied} verified patches, .ruah used {info['used_bytes']}/{RUAH_SEC_SIZE} bytes"
    )


if __name__ == "__main__":
    main()
