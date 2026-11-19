import ctypes
import glob
import os
import shutil
import struct
import subprocess
import sys
import numpy as np
from PIL import Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _resolve_default_iso() -> str:
    env_iso = os.environ.get("PRISM_ARK_ISO")
    if env_iso:
        return env_iso
    default_iso = os.path.join(REPO_ROOT, "Prism Ark - Awake (Japan).iso")
    if os.path.exists(default_iso):
        return default_iso
    isos = sorted(glob.glob(os.path.join(REPO_ROOT, "*.iso")))
    return isos[0] if isos else default_iso


ISO_PATH = _resolve_default_iso()
PC_DIR = os.environ.get("PRISM_ARK_PC_DIR") or r"d:\Video_Game\Visual Novel\pajama\p_ark201"
WORK_DIR = os.environ.get("PRISM_ARK_WORK_DIR") or os.path.join(REPO_ROOT, "_ps2_extract")
MOD_OUT_DIR = os.environ.get("PRISM_ARK_OUT_DIR") or os.path.join(REPO_ROOT, "pc_ruah_mod")
_DLL_EXT = ".dll" if sys.platform == "win32" else ".so"
DLL_PATH = os.path.join(REPO_ROOT, "src", f"zzz_helper{_DLL_EXT}")

IDX_SWIZZLE = np.array([(i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1) for i in range(256)], dtype=np.uint8)

# 100% verified 1-based filename-taking opcodes & operand slot indices (0-based within args[])
NFD_SLOTS = {
    0x01010009: [0, 1, 5, 6, 7],
    0x04000004: [1],
    0x05000003: [0],
    0x05000504: [0],
    0x05010004: [0],
    0x05020003: [0],
    0x05030002: [0],
    0x80000307: [0],  # 0 = no voice
    0x80010102: [0],
    0x80010204: [1],
    0x80010604: [0],
    0x80020002: [0],
    0x80020302: [0],
}

# 100% verified scenario IP-taking opcodes & operand slot indices
IP_SLOTS = {
    0x01000202: [0],  # JMP
    0x01000302: [0],  # CALL
    0x01000703: [1],  # JZ
    0x01010203: [1],  # ADD_CHOICE target
}

# 100% verified textdata.bin offset-taking opcodes & operand slot indices (0 = null/empty)
TF_SLOTS = {
    0x01000d02: [0],     # SET_CHAPTER_TITLE
    0x01010203: [0],     # ADD_CHOICE text
    0x80000307: [1, 2],  # SPEAK speaker, message
    0x80000406: [1, 2],  # SPEAK_NOVOICE speaker, message
}

def _find_gcc() -> str | None:
    g = shutil.which("gcc")
    if g:
        return g
    for cand in (r"C:\msys64\ucrt64\bin\gcc.exe", r"C:\msys64\mingw64\bin\gcc.exe", r"C:\mingw64\bin\gcc.exe"):
        if os.path.exists(cand):
            return cand
    return None


def ensure_dll() -> str:
    """Compile src/zzz_helper.c into shared library if missing or stale."""
    c_src = os.path.join(REPO_ROOT, "src", "zzz_helper.c")
    need_build = not os.path.exists(DLL_PATH) or (
        os.path.exists(c_src) and os.path.getmtime(c_src) > os.path.getmtime(DLL_PATH)
    )
    if need_build:
        gcc = _find_gcc()
        if not gcc:
            raise RuntimeError(f"Missing {DLL_PATH} and no gcc found to compile {c_src}")
        print(f"Building {os.path.basename(DLL_PATH)} from zzz_helper.c ...")
        subprocess.run([gcc, "-O3", "-shared", c_src, "-o", DLL_PATH], check=True)
    return DLL_PATH


_dll = None
def get_dll():
    global _dll
    if _dll is None:
        _dll = ctypes.CDLL(ensure_dll())
        _dll.decompress_zzz.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _dll.decompress_zzz.restype = ctypes.c_int
        _dll.decode_epa.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _dll.decode_epa.restype = ctypes.c_int
        _dll.encode_epa.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        _dll.encode_epa.restype = ctypes.c_int
    return _dll


def decompress_zzz(raw: bytes) -> bytes:
    if raw[:4] != b"ZZZ\x00":
        return raw
    out_len = struct.unpack_from("<I", raw, 8)[0]
    buf = ctypes.create_string_buffer(out_len + 256)
    n = get_dll().decompress_zzz(raw, len(raw), buf, len(buf))
    if n != out_len:
        raise RuntimeError(f"decompress_zzz mismatch: got {n}, expected {out_len}")
    return buf.raw[:n]


def encode_epa_image(im: Image.Image, force_rgba: bool = False) -> bytes:
    """Encode PIL Image (RGB or RGBA) to lossless PC EPA (mode 1 RGB or mode 2 RGBA)."""
    rgba = np.ascontiguousarray(im.convert("RGBA"), dtype=np.uint8)
    h, w = rgba.shape[:2]
    has_alpha = force_rgba or bool((rgba[:, :, 3] < 255).any())
    if has_alpha:
        mode = 2
        # Planar B, G, R, A
        planar = np.ascontiguousarray(np.stack([rgba[:, :, 2], rgba[:, :, 1], rgba[:, :, 0], rgba[:, :, 3]], axis=0))
    else:
        mode = 1
        # Planar B, G, R
        planar = np.ascontiguousarray(np.stack([rgba[:, :, 2], rgba[:, :, 1], rgba[:, :, 0]], axis=0))
    raw_bytes = planar.tobytes()
    max_out = len(raw_bytes) + (len(raw_bytes) // 15) + 128
    out_buf = ctypes.create_string_buffer(max_out)
    n = get_dll().encode_epa(raw_bytes, w, h, mode, out_buf, max_out)
    if n <= 0:
        raise RuntimeError(f"encode_epa failed: {n}")
    return out_buf.raw[:n]


def decode_epa_image(raw: bytes) -> Image.Image:
    if raw[:4] != b"EP\x01\x01":
        raise ValueError(f"Bad EPA magic: {raw[:4]!r}")
    mode, w, h = struct.unpack_from("<III", raw, 4)
    m = mode & 0xFF
    bpp = {0: 1, 1: 3, 2: 4}[m]
    target = w * h * bpp
    buf = ctypes.create_string_buffer(target)
    n = get_dll().decode_epa(raw, len(raw), buf, target)
    if n != target:
        raise RuntimeError(f"decode_epa mismatch: {n} != {target}")
    arr = np.frombuffer(buf.raw, dtype=np.uint8)
    if m == 0:
        pal = np.frombuffer(raw[16:16 + 0x300], dtype=np.uint8).reshape(256, 3)[:, ::-1]
        rgba = np.concatenate([pal[arr.reshape(h, w)], np.full((h, w, 1), 255, dtype=np.uint8)], axis=-1)
    elif m == 1:
        ch = arr.reshape(3, h, w)
        rgba = np.stack([ch[2], ch[1], ch[0], np.full((h, w), 255, dtype=np.uint8)], axis=-1)
    else:
        ch = arr.reshape(4, h, w)
        rgba = np.stack([ch[2], ch[1], ch[0], ch[3]], axis=-1)
    return Image.fromarray(rgba, "RGBA")


def decode_tim2_rgba(buf: bytes, tpos: int = 0) -> Image.Image:
    """Decode PS2 TIM2 (8-bit indexed + CSM1 RGBA32 CLUT, GS alpha 0..0x80) to RGBA PIL Image."""
    tag = buf[tpos:tpos + 4]
    if tag == b"TIM2":
        total_sz, clut_sz, img_sz, hdr_sz, clut_colors, pict_fmt, mip, clut_t, img_t, w, h = struct.unpack_from(
            "<IIIHHBBBBHH", buf, tpos + 16
        )
        img_off = tpos + 16 + hdr_sz
        clut_off = img_off + img_sz
        if img_t == 5 and clut_t == 3:
            idx = np.frombuffer(buf, dtype=np.uint8, count=w * h, offset=img_off).reshape(h, w)
            clut = np.frombuffer(buf, dtype=np.uint8, count=1024, offset=clut_off).reshape(256, 4)[IDX_SWIZZLE].copy()
            clut[:, 3] = np.clip((clut[:, 3].astype(np.int32) * 255 + 64) // 128, 0, 255).astype(np.uint8)
            return Image.fromarray(clut[idx], "RGBA")
        elif img_t == 3:
            # Direct RGBA32 TIM2
            rgba = np.frombuffer(buf, dtype=np.uint8, count=w * h * 4, offset=img_off).reshape(h, w, 4).copy()
            rgba[:, :, 3] = np.clip((rgba[:, :, 3].astype(np.int32) * 255 + 64) // 128, 0, 255).astype(np.uint8)
            return Image.fromarray(rgba, "RGBA")
        else:
            raise RuntimeError(f"Unsupported TIM2 format: img_t={img_t} clut_t={clut_t}")
    elif tag == b"PTL\x00":
        _, ttype, cols, rows, n_tiles, tw, th, pw, ph = struct.unpack_from("<4sBBBBIIII", buf, tpos)
        canvas = np.zeros((th, tw, 4), dtype=np.uint8)
        for t in range(n_tiles):
            tx, ty, aw, ah, bw_t, bh_t, px_off, clut_off = struct.unpack_from("<HHHHHHII", buf, tpos + 0x20 + t * 20)
            clut = np.frombuffer(buf, dtype=np.uint8, count=1024, offset=tpos + clut_off).reshape(256, 4)[IDX_SWIZZLE].copy()
            clut[:, 3] = np.clip((clut[:, 3].astype(np.int32) * 255 + 64) // 128, 0, 255).astype(np.uint8)
            tile_idx = np.frombuffer(buf, dtype=np.uint8, count=bw_t * bh_t, offset=tpos + px_off).reshape(bh_t, bw_t)
            canvas[ty:ty + ah, tx:tx + aw] = clut[tile_idx[:ah, :aw]]
        return Image.fromarray(canvas, "RGBA")
    else:
        raise RuntimeError(f"Unsupported texture tag: {tag!r}")


class IsoReader:
    def __init__(self, iso_path: str = ISO_PATH):
        self.iso_path = iso_path
        self.fh = open(iso_path, "rb")
        self.files = self._parse_root()
        self._flk_cache = {}

    def close(self):
        self.fh.close()

    def _parse_root(self):
        res = {}
        self.fh.seek(16 * 2048)
        pvd = self.fh.read(2048)
        root_lba = struct.unpack_from("<I", pvd, 156 + 2)[0]
        root_sz = struct.unpack_from("<I", pvd, 156 + 10)[0]
        self.fh.seek(root_lba * 2048)
        data = self.fh.read(root_sz)
        pos = 0
        while pos < len(data):
            rlen = data[pos]
            if rlen == 0:
                pos = ((pos // 2048) + 1) * 2048
                continue
            lba = struct.unpack_from("<I", data, pos + 2)[0]
            sz = struct.unpack_from("<I", data, pos + 10)[0]
            nlen = data[pos + 32]
            name = data[pos + 33:pos + 33 + nlen].decode("ascii", "replace").split(";")[0]
            if name not in ("\x00", "\x01"):
                res[name.upper()] = (lba * 2048, sz)
            pos += rlen
        return res

    def get_flk_table(self, dat_name: str):
        key = dat_name.upper()
        if key not in self._flk_cache:
            base, _ = self.files[key]
            self.fh.seek(base + 0x800)
            magic, ver, u1, u2, u3, fsz, cnt, flags = struct.unpack("<4s7I", self.fh.read(32))
            assert magic == b"FLK\x00", f"Bad FLK in {dat_name}: {magic!r}"
            entries = [struct.unpack("<II", self.fh.read(8)) for _ in range(cnt)]
            self._flk_cache[key] = (base, entries)
        return self._flk_cache[key]

    def read_flk_entry(self, dat_name: str, idx: int) -> bytes:
        base, entries = self.get_flk_table(dat_name)
        o, s = entries[idx]
        self.fh.seek(base + o)
        return self.fh.read(s)

    def read_flk_names(self, dat_name: str):
        base, entries = self.get_flk_table(dat_name)
        raw = self.read_flk_entry(dat_name, len(entries) - 1)
        lines = [l.strip() for l in raw.decode("cp932", "replace").splitlines()]
        non_empty = [l for l in lines if l]
        if len(non_empty) == len(entries) - 1:
            return non_empty
        return lines


def read_pc_archive_index(arch_path: str):
    with open(arch_path, "rb") as f:
        magic = f.read(12)
        assert magic == b"GAMEDAT PAC2", f"Bad PAC2 magic: {magic!r}"
        cnt = struct.unpack("<I", f.read(4))[0]
        names = [f.read(32).split(b"\x00", 1)[0].decode("cp932", "replace") for _ in range(cnt)]
        pairs = [struct.unpack("<II", f.read(8)) for _ in range(cnt)]
        db = f.tell()
    return names, pairs, db


def read_pc_archive_file(arch_name: str, member: str, pc_dir: str = PC_DIR) -> bytes | None:
    p = os.path.join(pc_dir, arch_name)
    names, pairs, db = read_pc_archive_index(p)
    ml = member.lower()
    with open(p, "rb") as f:
        for n, (o, s) in zip(names, pairs):
            if n.lower() == ml:
                f.seek(db + o)
                return f.read(s)
    return None


def write_gamedat_pac2(out_path: str, file_list: list[tuple[str, bytes]]):
    """Write a GAMEDAT PAC2 archive from [(filename, raw_bytes), ...]."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Deduplicate case-insensitively (last wins if caller duplicated, or preserve order)
    dedup = {}
    ordered = []
    for name, data in file_list:
        k = name.upper()
        if k not in dedup:
            ordered.append(k)
        dedup[k] = (name, data)
    items = [dedup[k] for k in ordered]
    cnt = len(items)
    with open(out_path, "wb") as f:
        f.write(b"GAMEDAT PAC2")
        f.write(struct.pack("<I", cnt))
        for name, _ in items:
            nb = name.encode("cp932")
            if len(nb) > 31:
                raise ValueError(f"PAC2 filename > 31 bytes: {name!r}")
            f.write(nb + b"\x00" * (32 - len(nb)))
        cur_off = 0
        for _, data in items:
            f.write(struct.pack("<II", cur_off, len(data)))
            cur_off += len(data)
        for _, data in items:
            f.write(data)


def crypt_textdata(raw: bytes) -> bytes:
    """XOR-encrypt or decrypt PJADV textdata.bin (self-inverse)."""
    arr = np.frombuffer(raw, dtype=np.uint8).copy()
    keys = ((0xC5 + np.arange(len(arr), dtype=np.uint32) * 0x5C) & 0xFF).astype(np.uint8)
    arr ^= keys
    return arr.tobytes()


# ---- PRSM (battle.dat / battle1.dat) utilities ----

def _nrv2e_decompress_le32(src: bytes) -> bytes:
    """Decompress UPX NRV2E_LE32 stream from P_ARK201.exe."""
    bb = bc = ip = 0

    def getbit() -> int:
        nonlocal bb, bc, ip
        if bc == 0:
            bb = struct.unpack_from("<I", src, ip)[0]
            ip += 4
            bc = 32
        bc -= 1
        return (bb >> bc) & 1

    out = bytearray()
    last_m_off = 1
    while True:
        while getbit():
            out.append(src[ip])
            ip += 1
        m_off = 1
        while True:
            m_off = m_off * 2 + getbit()
            if getbit():
                break
            m_off = (m_off - 1) * 2 + getbit()
        if m_off == 2:
            m_off = last_m_off
            m_len = getbit()
        else:
            m_off = (m_off - 3) * 256 + src[ip]
            ip += 1
            if m_off == 0xFFFFFFFF:
                break
            m_len = (m_off ^ 0xFFFFFFFF) & 1
            m_off = (m_off >> 1) + 1
            last_m_off = m_off
        if m_len:
            m_len = 1 + getbit()
        elif getbit():
            m_len = 3 + getbit()
        else:
            m_len = 1
            while True:
                m_len = m_len * 2 + getbit()
                if getbit():
                    break
            m_len += 3
        m_len += 2 if m_off > 0x500 else 1
        for _ in range(m_len):
            out.append(out[-m_off])
    return bytes(out)


def ensure_unpacked_exe() -> str:
    """Return path to cached unpacked P_ARK201_unpacked.bin, extracting from P_ARK201.exe if needed."""
    unp = os.path.join(WORK_DIR, "P_ARK201_unpacked.bin")
    if os.path.exists(unp):
        return unp
    exe_path = os.path.join(PC_DIR, "P_ARK201.exe")
    if not os.path.exists(exe_path):
        raise FileNotFoundError(f"P_ARK201.exe not found in PC_DIR: {PC_DIR}")
    with open(exe_path, "rb") as f:
        exe = f.read()
    pos_upx = exe.find(b"UPX!")
    if pos_upx == -1:
        # Already unpacked PE; copy directly or slice .text+data starting at RVA 0x1000
        pe = struct.unpack_from("<I", exe, 0x3C)[0]
        oh_sz = struct.unpack_from("<H", exe, pe + 20)[0]
        nsec = struct.unpack_from("<H", exe, pe + 6)[0]
        ro = struct.unpack_from("<I", exe, pe + 24 + oh_sz + 20)[0]
        os.makedirs(WORK_DIR, exist_ok=True)
        with open(unp, "wb") as out_f:
            out_f.write(exe[ro:])
        return unp
    vals = struct.unpack_from("<4sBBBBIIIIIBBBB", exe, pos_upx)
    _, _, _, _, _, _, _, u_len, c_len, _, _, _, _, _ = vals
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    nsec = struct.unpack_from("<H", exe, pe + 6)[0]
    oh_sz = struct.unpack_from("<H", exe, pe + 20)[0]
    sec_off = pe + 24 + oh_sz
    upx1_ro = None
    for i in range(nsec):
        nm, _, _, _, ro = struct.unpack_from("<8sIIII", exe, sec_off + i * 40)
        if nm.rstrip(b"\x00") == b"UPX1":
            upx1_ro = ro
            break
    if upx1_ro is None:
        raise RuntimeError("Could not locate UPX1 section in P_ARK201.exe")
    print("Unpacking P_ARK201.exe (UPX NRV2E) to extract PRSM table ...")
    dec = _nrv2e_decompress_le32(exe[upx1_ro : upx1_ro + c_len])
    assert len(dec) == u_len, f"Unpack length mismatch: {len(dec)} != {u_len}"
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(unp, "wb") as out_f:
        out_f.write(dec)
    return unp


def load_prsm_tables():
    """Load the 6x256 decryption table from unpacked P_ARK201.exe and build inverse encryption table."""
    unp = ensure_unpacked_exe()
    with open(unp, "rb") as f:
        f.seek(0x556A08 - 0x401000)
        dec_tbl = f.read(6 * 256)
    enc_tbl = bytearray(6 * 256)
    for row in range(6):
        for b in range(256):
            enc_tbl[row * 256 + dec_tbl[row * 256 + b]] = b
    return dec_tbl, bytes(enc_tbl)


def prsm_lz_decode(buf: bytes, pos: int = 0, init_mask: int = 8) -> bytes:
    b0 = buf[pos]
    mode = b0 & 0xC0
    shift, mask, win = {0x00: (10, 0x3FF, 0x400), 0x40: (11, 0x7FF, 0x800), 0x80: (12, 0xFFF, 0x1000)}[mode]
    out = bytearray()
    flag = b0
    bit = init_mask
    pos += 1
    while True:
        if bit == 0:
            flag = buf[pos]
            pos += 1
            bit = 0x80
        if flag & bit:
            out.append(buf[pos])
            pos += 1
        else:
            w = buf[pos] | (buf[pos + 1] << 8)
            pos += 2
            if w == 0xFFFF:
                break
            length = (w >> shift) + 2
            dist = win - (w & mask)
            for _ in range(length):
                out.append(out[-dist])
        bit >>= 1
    return bytes(out)


def prsm_lz_encode_store(data: bytes) -> bytes:
    """Encode bytes using PRSM LZSS format (valid literal-only stream ending with 0xFFFF)."""
    # First byte: mode=0x40 (window=0x800), bits 3..0 (init_mask=8 -> 4 slots)
    out = bytearray()
    n = len(data)
    i = 0
    # First group has 4 slots (bits 8, 4, 2, 1)
    first_chunk = data[0:min(4, n)]
    i = len(first_chunk)
    if i < 4:
        # Mark first i bits as 1, next bit as 0 (EOF 0xFFFF)
        flags = 0x40
        for b in range(i):
            flags |= (8 >> b)
        out.append(flags)
        out.extend(first_chunk)
        out.extend(b"\xff\xff")
        return bytes(out)
    out.append(0x40 | 0x0F)
    out.extend(first_chunk)
    while i < n:
        rem = n - i
        if rem >= 8:
            out.append(0xFF)
            out.extend(data[i:i + 8])
            i += 8
        else:
            flags = 0
            for b in range(rem):
                flags |= (0x80 >> b)
            out.append(flags)
            out.extend(data[i:n])
            out.extend(b"\xff\xff")
            return bytes(out)
    # Ended on an exact 8-byte boundary -> emit EOF flag byte + 0xFFFF
    out.append(0x00)
    out.extend(b"\xff\xff")
    return bytes(out)


def write_prsm_archive(out_path: str, file_list: list[tuple[str, bytes]]):
    """Write a PRSM archive (battle1.dat) compatible with P_ARK201.exe."""
    dec_tbl, enc_tbl = load_prsm_tables()
    cnt = len(file_list)
    # P_ARK201.exe (0x4a0622) requires usz > 0 and ALWAYS calls PRSM LZ decode (0x49f720) on payload!
    # Encode both the 132B name record and each file payload with prsm_lz_encode_store.
    enc_names = []
    lz_payloads = []
    for path, data in file_list:
        pb = path.replace("/", "\\").encode("cp932")
        assert len(pb) < 0x7F, f"PRSM path too long: {path}"
        usz = len(data)
        assert usz > 0, f"PRSM empty file unsupported: {path}"
        rec = pb + b"\x00" * (0x7F - len(pb)) + bytes([0]) + struct.pack("<I", usz)
        enc_names.append(prsm_lz_encode_store(rec))
        lz_payloads.append(prsm_lz_encode_store(data))

    # Header layout: 12B magic/cnt/hsz + cnt*12B entries + concatenated enc_names
    names_start = 12 + cnt * 12
    name_offs = []
    cur = names_start
    for en in enc_names:
        name_offs.append(cur)
        cur += len(en)
    hsz = cur

    hdr = bytearray()
    hdr.extend(b"PRSM")
    hdr.extend(struct.pack("<II", cnt, hsz))
    data_off = hsz
    for idx, lz_data in enumerate(lz_payloads):
        hdr.extend(struct.pack("<III", name_offs[idx], data_off, len(lz_data)))
        data_off += len(lz_data)
    for en in enc_names:
        hdr.extend(en)
    assert len(hdr) == hsz

    # Encrypt header bytes [12..hsz] using enc_tbl with index i % 6
    for i in range(12, hsz):
        hdr[i] = enc_tbl[(i % 6) * 256 + hdr[i]]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(hdr)
        for lz_data in lz_payloads:
            # Encrypt LZ payload bytes with key_b = 0, index i % 6
            eb = bytearray(len(lz_data))
            for i, b in enumerate(lz_data):
                eb[i] = enc_tbl[(i % 6) * 256 + b]
            f.write(eb)
