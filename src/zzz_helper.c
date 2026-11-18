#include <stdint.h>
#include <string.h>
#include <stdlib.h>

static inline uint32_t rd32(const uint8_t *p) {
    uint32_t v;
    memcpy(&v, p, 4);
    return v;
}

static inline void wr32(uint8_t *p, uint32_t v) {
    memcpy(p, &v, 4);
}

__declspec(dllexport) int decompress_zzz(const uint8_t *data, int data_len, uint8_t *out, int max_out) {
    if (data_len < 48) return -1;
    if (data[0] != 'Z' || data[1] != 'Z' || data[2] != 'Z' || data[4] != 1) return -2;
    uint32_t out_len = rd32(data + 8);
    if ((int)out_len > max_out) return -3;

    uint32_t flag_off = rd32(data + 16);
    uint32_t flag_sz  = rd32(data + 20);
    uint32_t nib_off  = rd32(data + 24);
    uint32_t lit_off  = rd32(data + 32);
    uint32_t op_off   = rd32(data + 40);

    const uint8_t *a3 = data + flag_off;
    const uint8_t *a3_end = a3 + flag_sz;
    const uint8_t *v0 = data + nib_off;
    const uint8_t *t0 = data + lit_off;
    const uint8_t *a0 = data + op_off;

    uint8_t *a1 = out;
    uint8_t *s1 = out + out_len;
    int s2 = 0;
    int a2 = 0;
    uint32_t v1 = 0;

    while (a1 < s1) {
        if (a2 == 0) {
            if (a3 >= a3_end) break;
            v1 = *a3++;
            a2 = 8;
        }
        if ((v1 & 1) == 0) {
            *a1++ = *t0++;
        } else {
            uint8_t t2 = *a0;
            uint8_t top = t2 & 0xc0;
            if (top == 0x40) {
                int cnt = ((t2 & 0x30) >> 4) + 3;
                int dist = ((t2 & 0x0f) << 8) | a0[1];
                a0 += 2;
                const uint8_t *src = a1 - dist;
                for (int i = 0; i < cnt; i++) *a1++ = *src++;
            } else if (top == 0x00) {
                if (t2 & 0x20) {
                    int cnt = (t2 & 0x1f) + 3;
                    int dist = a0[1];
                    a0 += 2;
                    const uint8_t *src = a1 - dist;
                    for (int i = 0; i < cnt; i++) *a1++ = *src++;
                } else if (t2 & 0x10) {
                    int cnt = (t2 & 0x0f) << 2;
                    a0 += 1;
                    memcpy(a1, t0, cnt);
                    a1 += cnt;
                    t0 += cnt;
                } else {
                    int dist = ((t2 & 0x0f) << 8) | a0[1];
                    a0 += 2;
                    uint8_t b = *v0;
                    int n;
                    if (s2 == 0) { s2 = 1; n = b & 0xf; }
                    else { v0++; s2 = 0; n = b >> 4; }
                    int cnt = n + 7;
                    const uint8_t *src = a1 - dist;
                    for (int i = 0; i < cnt; i++) *a1++ = *src++;
                }
            } else if (top == 0x80) {
                int cnt = ((t2 >> 4) & 3) + 3;
                int dist = (t2 & 0x0f) + 3;
                a0 += 1;
                const uint8_t *src = a1 - dist;
                for (int i = 0; i < cnt; i++) *a1++ = *src++;
            } else {
                uint8_t sub = t2 & 0x30;
                if (sub == 0x00) {
                    int n = t2 & 0x0f;
                    uint8_t val = a0[1];
                    int cnt;
                    if (n == 0) { cnt = a0[2] + 2; a0 += 3; }
                    else { cnt = n + 2; a0 += 2; }
                    memset(a1, val, cnt);
                    a1 += cnt;
                } else if (sub == 0x10) {
                    int dist = ((t2 & 0x0f) << 8) | a0[1];
                    uint8_t delta = a0[2];
                    a0 += 3;
                    uint8_t b = *v0;
                    int n;
                    if (s2 == 0) { s2 = 1; n = b & 0xf; }
                    else { v0++; s2 = 0; n = b >> 4; }
                    int cnt = n + 6;
                    const uint8_t *src = a1 - dist;
                    for (int i = 0; i < cnt; i++) *a1++ = (uint8_t)(*src++ + delta);
                } else if (sub == 0x20) {
                    int cnt = (t2 & 0x0f) + 3;
                    uint8_t b1 = a0[1];
                    a0 += 2;
                    *a1++ = b1;
                    uint8_t hi = b1 & 0xf0;
                    for (int i = 0; i < cnt; i++) {
                        uint8_t b = *v0;
                        int n;
                        if (s2 == 0) { s2 = 1; n = b & 0xf; }
                        else { v0++; s2 = 0; n = b >> 4; }
                        *a1++ = hi | n;
                    }
                }
            }
        }
        v1 >>= 1;
        a2--;
    }
    return (int)(a1 - out);
}

__declspec(dllexport) int compress_zzz(const uint8_t *in, int in_len, uint8_t *out, int max_out) {
    if (in_len <= 0 || max_out < 48) return -1;

    uint8_t *flags = (uint8_t*)malloc((in_len / 8) + 16);
    uint8_t *nibs  = (uint8_t*)malloc((in_len / 2) + 16);
    uint8_t *lits  = (uint8_t*)malloc(in_len + 16);
    uint8_t *ops   = (uint8_t*)malloc(in_len + 16);
    int *head = (int*)malloc(65536 * sizeof(int));
    int *prev = (int*)malloc(in_len * sizeof(int));
    if (!flags || !nibs || !lits || !ops || !head || !prev) {
        free(flags); free(nibs); free(lits); free(ops); free(head); free(prev);
        return -2;
    }
    memset(head, -1, 65536 * sizeof(int));

    int f_len = 0, n_len = 0, l_len = 0, o_len = 0;
    uint8_t f_cur = 0;
    int f_bit = 0;
    int nib_half = 0;
    uint8_t nib_byte = 0;

    #define PUT_FLAG(bit) do { \
        if (bit) f_cur |= (1 << f_bit); \
        f_bit++; \
        if (f_bit == 8) { flags[f_len++] = f_cur; f_cur = 0; f_bit = 0; } \
    } while(0)

    #define PUT_NIB(n) do { \
        if (nib_half == 0) { nib_byte = (uint8_t)(n); nib_half = 1; } \
        else { nibs[n_len++] = (uint8_t)(nib_byte | ((n) << 4)); nib_half = 0; } \
    } while(0)

    int pos = 0;
    while (pos < in_len) {
        // 1. Check RLE
        int rle_len = 1;
        uint8_t rle_val = in[pos];
        while (pos + rle_len < in_len && rle_len < 257 && in[pos + rle_len] == rle_val) {
            rle_len++;
        }

        // 2. Check LZ match (3-byte hash)
        int best_len = 0, best_dist = 0;
        if (pos + 2 < in_len) {
            uint32_t h = ((uint32_t)in[pos] << 8) ^ ((uint32_t)in[pos+1] << 4) ^ in[pos+2];
            int cur = head[h];
            int chain = 0;
            while (cur >= 0 && (pos - cur) <= 4095 && chain < 32) {
                int dist = pos - cur;
                int max_m = (dist <= 255) ? 34 : 22;
                if (pos + max_m > in_len) max_m = in_len - pos;
                if (in[cur] == in[pos] && in[cur+1] == in[pos+1] && in[cur+2] == in[pos+2]) {
                    int m = 3;
                    while (m < max_m && in[cur + m] == in[pos + m]) m++;
                    if (m > best_len) {
                        best_len = m;
                        best_dist = dist;
                        if (m == max_m) break;
                    }
                }
                cur = prev[cur];
                chain++;
            }
        }

        // Insert hash for positions we advance by
        int adv = 1;
        if (rle_len >= 3 && rle_len >= best_len) {
            PUT_FLAG(1);
            if (rle_len <= 17) {
                ops[o_len++] = (uint8_t)(0xc0 | (rle_len - 2));
                ops[o_len++] = rle_val;
            } else {
                ops[o_len++] = 0xc0;
                ops[o_len++] = rle_val;
                ops[o_len++] = (uint8_t)(rle_len - 2);
            }
            adv = rle_len;
        } else if (best_len >= 3) {
            PUT_FLAG(1);
            if (best_dist >= 3 && best_dist <= 18 && best_len <= 6) {
                ops[o_len++] = (uint8_t)(0x80 | ((best_len - 3) << 4) | (best_dist - 3));
            } else if (best_dist <= 255 && best_len <= 34) {
                ops[o_len++] = (uint8_t)(0x20 | (best_len - 3));
                ops[o_len++] = (uint8_t)best_dist;
            } else if (best_len <= 6) {
                ops[o_len++] = (uint8_t)(0x40 | ((best_len - 3) << 4) | (best_dist >> 8));
                ops[o_len++] = (uint8_t)(best_dist & 0xff);
            } else {
                if (best_len > 22) best_len = 22;
                ops[o_len++] = (uint8_t)(best_dist >> 8);
                ops[o_len++] = (uint8_t)(best_dist & 0xff);
                PUT_NIB(best_len - 7);
            }
            adv = best_len;
        } else {
            PUT_FLAG(0);
            lits[l_len++] = in[pos];
            adv = 1;
        }

        for (int k = 0; k < adv; k++) {
            int p = pos + k;
            if (p + 2 < in_len) {
                uint32_t h = ((uint32_t)in[p] << 8) ^ ((uint32_t)in[p+1] << 4) ^ in[p+2];
                prev[p] = head[h];
                head[h] = p;
            }
        }
        pos += adv;
    }

    if (f_bit > 0) flags[f_len++] = f_cur;
    if (nib_half) nibs[n_len++] = nib_byte;

    uint32_t flag_off = 48;
    uint32_t nib_off  = flag_off + (uint32_t)f_len;
    uint32_t lit_off  = nib_off + (uint32_t)n_len;
    uint32_t op_off   = lit_off + (uint32_t)l_len;
    uint32_t total_sz = op_off + (uint32_t)o_len;

    int ret = -3;
    if ((int)total_sz <= max_out) {
        memset(out, 0, 48);
        out[0] = 'Z'; out[1] = 'Z'; out[2] = 'Z'; out[3] = 0;
        wr32(out + 4, 1);
        wr32(out + 8, (uint32_t)in_len);
        wr32(out + 12, total_sz);
        wr32(out + 16, flag_off);
        wr32(out + 20, (uint32_t)f_len);
        wr32(out + 24, nib_off);
        wr32(out + 28, (uint32_t)n_len);
        wr32(out + 32, lit_off);
        wr32(out + 36, (uint32_t)l_len);
        wr32(out + 40, op_off);
        wr32(out + 44, (uint32_t)o_len);
        memcpy(out + flag_off, flags, f_len);
        memcpy(out + nib_off,  nibs,  n_len);
        memcpy(out + lit_off,  lits,  l_len);
        memcpy(out + op_off,   ops,   o_len);
        ret = (int)total_sz;
    }

    free(flags); free(nibs); free(lits); free(ops); free(head); free(prev);
    return ret;
}

__declspec(dllexport) int decode_epa(const uint8_t *data, int data_len, uint8_t *out, int target_len) {
    if (data_len < 16) return -1;
    uint32_t mode = rd32(data + 4);
    uint32_t w = rd32(data + 8);
    int pos = ((mode & 0xff) == 0) ? (16 + 0x300) : 16;
    int offsets[16] = {
        0, 1, (int)w, (int)w+1, 2, (int)w-1, 2*(int)w, 3,
        2*((int)w+1), (int)w+2, 2*(int)w+1, 2*(int)w-1, 2*((int)w-1), (int)w-2, 3*(int)w, 4
    };
    int out_pos = 0;
    while (pos < data_len && out_pos < target_len) {
        uint8_t flag = data[pos++];
        if ((flag & 0xf0) == 0) {
            int cnt = flag;
            if (out_pos + cnt > target_len) cnt = target_len - out_pos;
            memcpy(out + out_pos, data + pos, cnt);
            pos += flag;
            out_pos += cnt;
        } else {
            int idx = flag >> 4;
            int cnt = flag & 0x0f;
            if (cnt & 0x08) {
                cnt = ((cnt & 0x07) << 8) | data[pos++];
            }
            int off = offsets[idx];
            for (int i = 0; i < cnt && out_pos < target_len; i++) {
                out[out_pos] = out[out_pos - off];
                out_pos++;
            }
        }
    }
    return out_pos;
}
