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

/* ---- 4D RGBA Variance-Minimizing Median-Cut + Floyd-Steinberg Quantizer ---- */

typedef struct {
    uint8_t r, g, b, a;
    uint32_t count;
} ColorEntry;

typedef struct {
    int start, len;
    double score;
    int split_axis;
} ColorBox;

static void box_stats(const ColorEntry *arr, int start, int len, ColorBox *b) {
    double sw = 0, sr = 0, sg = 0, sb = 0, sa = 0;
    double sr2 = 0, sg2 = 0, sb2 = 0, sa2 = 0;
    for (int i = 0; i < len; i++) {
        const ColorEntry *e = &arr[start + i];
        double w = (double)e->count;
        double r = e->r, g = e->g, bl = e->b, a = e->a;
        sw += w;
        sr += w * r; sg += w * g; sb += w * bl; sa += w * a;
        sr2 += w * r * r; sg2 += w * g * g; sb2 += w * bl * bl; sa2 += w * a * a;
    }
    if (sw <= 0 || len <= 1) {
        b->score = 0.0;
        b->split_axis = 0;
        return;
    }
    double er = sr2 - (sr * sr) / sw;
    double eg = sg2 - (sg * sg) / sw;
    double eb = sb2 - (sb * sb) / sw;
    double ea = (sa2 - (sa * sa) / sw) * 2.0;
    if (er < 0) er = 0;
    if (eg < 0) eg = 0;
    if (eb < 0) eb = 0;
    if (ea < 0) ea = 0;
    b->score = er + eg + eb + ea;
    int ax = 0; double mx = er;
    if (eg > mx) { mx = eg; ax = 1; }
    if (eb > mx) { mx = eb; ax = 2; }
    if (ea > mx) { mx = ea; ax = 3; }
    b->split_axis = ax;
}

static int split_box(ColorEntry *arr, ColorEntry *tmp, ColorBox *boxes, int idx, int *n_boxes) {
    ColorBox cur = boxes[idx];
    if (cur.len <= 1 || cur.score <= 0.0) return 0;
    int ax = cur.split_axis;

    /* Counting sort by channel 0..255 */
    int counts[256] = {0};
    for (int i = 0; i < cur.len; i++) {
        uint8_t v = (ax == 0) ? arr[cur.start + i].r :
                    (ax == 1) ? arr[cur.start + i].g :
                    (ax == 2) ? arr[cur.start + i].b : arr[cur.start + i].a;
        counts[v]++;
    }
    int offs[256], acc = 0;
    for (int v = 0; v < 256; v++) { offs[v] = acc; acc += counts[v]; }
    for (int i = 0; i < cur.len; i++) {
        ColorEntry e = arr[cur.start + i];
        uint8_t v = (ax == 0) ? e.r : (ax == 1) ? e.g : (ax == 2) ? e.b : e.a;
        tmp[offs[v]++] = e;
    }
    memcpy(arr + cur.start, tmp, (size_t)cur.len * sizeof(ColorEntry));

    /* Find split minimizing 1D weighted SSE along chosen axis */
    double tot_w = 0, tot_wv = 0, tot_wv2 = 0;
    for (int i = 0; i < cur.len; i++) {
        double w = (double)arr[cur.start + i].count;
        double v = (ax == 0) ? arr[cur.start + i].r :
                   (ax == 1) ? arr[cur.start + i].g :
                   (ax == 2) ? arr[cur.start + i].b : arr[cur.start + i].a;
        tot_w += w;
        tot_wv += w * v;
        tot_wv2 += w * v * v;
    }
    double lw = 0, lwv = 0, lwv2 = 0;
    double best_sse = 1e30;
    int best_k = cur.len / 2;
    for (int i = 0; i < cur.len - 1; i++) {
        double w = (double)arr[cur.start + i].count;
        double v = (ax == 0) ? arr[cur.start + i].r :
                   (ax == 1) ? arr[cur.start + i].g :
                   (ax == 2) ? arr[cur.start + i].b : arr[cur.start + i].a;
        lw += w; lwv += w * v; lwv2 += w * v * v;
        double rw = tot_w - lw;
        if (lw <= 0 || rw <= 0) continue;
        double rwv = tot_wv - lwv, rwv2 = tot_wv2 - lwv2;
        double lsse = lwv2 - (lwv * lwv) / lw;
        double rsse = rwv2 - (rwv * rwv) / rw;
        if (lsse + rsse < best_sse) {
            best_sse = lsse + rsse;
            best_k = i + 1;
        }
    }
    if (best_k <= 0) best_k = 1;
    if (best_k >= cur.len) best_k = cur.len - 1;

    boxes[idx].start = cur.start;
    boxes[idx].len = best_k;
    box_stats(arr, boxes[idx].start, boxes[idx].len, &boxes[idx]);

    int nb = *n_boxes;
    boxes[nb].start = cur.start + best_k;
    boxes[nb].len = cur.len - best_k;
    box_stats(arr, boxes[nb].start, boxes[nb].len, &boxes[nb]);
    (*n_boxes)++;
    return 1;
}

typedef struct {
    int r, g, b, a, s;
    uint8_t idx;
} PalLookup;

static int cmp_pal_s(const void *pa, const void *pb) {
    const PalLookup *a = (const PalLookup *)pa, *b = (const PalLookup *)pb;
    return (a->s > b->s) - (a->s < b->s);
}

static inline uint8_t find_nearest_3d(const PalLookup *pal, int n, int r, int g, int b) {
    int s = r + g + b;
    int lo = 0, hi = n - 1;
    while (lo < hi) {
        int mid = (lo + hi) >> 1;
        if (pal[mid].s < s) lo = mid + 1;
        else hi = mid;
    }
    int dr0 = r - pal[lo].r, dg0 = g - pal[lo].g, db0 = b - pal[lo].b;
    int best_d = dr0 * dr0 + dg0 * dg0 + db0 * db0;
    uint8_t best_idx = pal[lo].idx;
    if (best_d == 0) return best_idx;
    int L = lo - 1, R = lo + 1;
    while (L >= 0 || R < n) {
        if (L >= 0) {
            int64_t ds = (int64_t)s - pal[L].s;
            if (ds * ds >= 3LL * best_d) { L = -1; }
            else {
                int dr = r - pal[L].r, dg = g - pal[L].g, db = b - pal[L].b;
                int d = dr * dr + dg * dg + db * db;
                if (d < best_d) { best_d = d; best_idx = pal[L].idx; if (d == 0) return best_idx; }
                L--;
            }
        }
        if (R < n) {
            int64_t ds = (int64_t)pal[R].s - s;
            if (ds * ds >= 3LL * best_d) { R = n; }
            else {
                int dr = r - pal[R].r, dg = g - pal[R].g, db = b - pal[R].b;
                int d = dr * dr + dg * dg + db * db;
                if (d < best_d) { best_d = d; best_idx = pal[R].idx; if (d == 0) return best_idx; }
                R++;
            }
        }
    }
    return best_idx;
}

static inline uint8_t find_nearest_4d(const PalLookup *pal, int n, int r, int g, int b, int a) {
    int s = r + g + b + a;
    int lo = 0, hi = n - 1;
    while (lo < hi) {
        int mid = (lo + hi) >> 1;
        if (pal[mid].s < s) lo = mid + 1;
        else hi = mid;
    }
    int dr0 = r - pal[lo].r, dg0 = g - pal[lo].g, db0 = b - pal[lo].b, da0 = a - pal[lo].a;
    int best_d = dr0 * dr0 + dg0 * dg0 + db0 * db0 + 2 * da0 * da0;
    uint8_t best_idx = pal[lo].idx;
    if (best_d == 0) return best_idx;
    int L = lo - 1, R = lo + 1;
    while (L >= 0 || R < n) {
        if (L >= 0) {
            int64_t ds = (int64_t)s - pal[L].s;
            if (ds * ds >= 4LL * best_d) { L = -1; }
            else {
                int dr = r - pal[L].r, dg = g - pal[L].g, db = b - pal[L].b, da = a - pal[L].a;
                int d = dr * dr + dg * dg + db * db + 2 * da * da;
                if (d < best_d) { best_d = d; best_idx = pal[L].idx; if (d == 0) return best_idx; }
                L--;
            }
        }
        if (R < n) {
            int64_t ds = (int64_t)pal[R].s - s;
            if (ds * ds >= 4LL * best_d) { R = n; }
            else {
                int dr = r - pal[R].r, dg = g - pal[R].g, db = b - pal[R].b, da = a - pal[R].a;
                int d = dr * dr + dg * dg + db * db + 2 * da * da;
                if (d < best_d) { best_d = d; best_idx = pal[R].idx; if (d == 0) return best_idx; }
                R++;
            }
        }
    }
    return best_idx;
}

static inline int clamp255(int v) { return v < 0 ? 0 : (v > 255 ? 255 : v); }
static inline int clamp_err(int v) { return v < -48 ? -48 : (v > 48 ? 48 : v); }

__declspec(dllexport) int quantize_rgba_fs(
    const uint8_t *rgba, int w, int h, int reserve_zero,
    uint8_t *out_idx, uint8_t *out_clut_rgba
) {
    int npix = w * h;
    if (npix <= 0) return -1;

    /* Hash unique non-zero-alpha colors (separating a==255 and 0<a<255) */
    int hcap = 65536;
    while (hcap < npix && hcap < (1 << 21)) hcap <<= 1;
    if (hcap < (1 << 20)) hcap <<= 1;
    uint32_t hmask = (uint32_t)(hcap - 1);
    uint32_t *ht_key = (uint32_t *)malloc((size_t)hcap * sizeof(uint32_t));
    uint32_t *ht_cnt = (uint32_t *)calloc((size_t)hcap, sizeof(uint32_t));
    if (!ht_key || !ht_cnt) { free(ht_key); free(ht_cnt); return -2; }

    int n_opa_u = 0, n_semi_u = 0;
    for (int i = 0; i < npix; i++) {
        uint8_t a = rgba[i * 4 + 3];
        if (a == 0 && reserve_zero) continue;
        uint32_t key = (uint32_t)rgba[i * 4] | ((uint32_t)rgba[i * 4 + 1] << 8) |
                       ((uint32_t)rgba[i * 4 + 2] << 16) | ((uint32_t)a << 24);
        uint32_t hval = (key * 2654435761u) ^ (key >> 16);
        uint32_t slot = hval & hmask;
        for (int probe = 0; probe < 128; probe++) {
            uint32_t cur = (slot + (uint32_t)probe) & hmask;
            if (ht_cnt[cur] == 0) {
                ht_key[cur] = key;
                ht_cnt[cur] = 1;
                if (a == 255) n_opa_u++; else n_semi_u++;
                break;
            }
            if (ht_key[cur] == key) {
                ht_cnt[cur]++;
                break;
            }
        }
    }

    int n_u = n_opa_u + n_semi_u;
    memset(out_clut_rgba, 0, 256 * 4);
    if (n_u == 0) {
        memset(out_idx, 0, (size_t)npix);
        free(ht_key); free(ht_cnt);
        return 0;
    }

    ColorEntry *entries = (ColorEntry *)malloc((size_t)n_u * sizeof(ColorEntry));
    ColorEntry *tmp = (ColorEntry *)malloc((size_t)n_u * sizeof(ColorEntry));
    if (!entries || !tmp) { free(ht_key); free(ht_cnt); free(entries); free(tmp); return -3; }

    int oi = 0, si = n_opa_u;
    for (int slot = 0; slot < hcap; slot++) {
        if (ht_cnt[slot] == 0) continue;
        uint32_t key = ht_key[slot];
        ColorEntry e;
        e.r = (uint8_t)(key & 0xff);
        e.g = (uint8_t)((key >> 8) & 0xff);
        e.b = (uint8_t)((key >> 16) & 0xff);
        e.a = (uint8_t)((key >> 24) & 0xff);
        e.count = ht_cnt[slot];
        if (e.a == 255) entries[oi++] = e;
        else entries[si++] = e;
    }
    free(ht_key); free(ht_cnt);

    int max_pal = reserve_zero ? 255 : 256;
    int start_idx = reserve_zero ? 1 : 0;
    ColorBox boxes[256];
    int n_boxes = 0;
    if (n_opa_u > 0) {
        boxes[n_boxes].start = 0; boxes[n_boxes].len = n_opa_u;
        box_stats(entries, 0, n_opa_u, &boxes[n_boxes]);
        n_boxes++;
    }
    if (n_semi_u > 0) {
        boxes[n_boxes].start = n_opa_u; boxes[n_boxes].len = n_semi_u;
        box_stats(entries, n_opa_u, n_semi_u, &boxes[n_boxes]);
        n_boxes++;
    }

    while (n_boxes < max_pal) {
        int best_b = -1;
        double best_sc = 0.0;
        for (int b = 0; b < n_boxes; b++) {
            if (boxes[b].len > 1 && boxes[b].score > best_sc) {
                best_sc = boxes[b].score;
                best_b = b;
            }
        }
        if (best_b < 0) break;
        if (!split_box(entries, tmp, boxes, best_b, &n_boxes)) break;
    }
    free(tmp);

    PalLookup pal_opa[256], pal_all[256];
    int n_pal_opa = 0, n_pal_all = 0;
    for (int b = 0; b < n_boxes; b++) {
        double sw = 0, sr = 0, sg = 0, sb = 0, sa = 0;
        for (int i = 0; i < boxes[b].len; i++) {
            const ColorEntry *e = &entries[boxes[b].start + i];
            double w = (double)e->count;
            sw += w; sr += w * e->r; sg += w * e->g; sb += w * e->b; sa += w * e->a;
        }
        uint8_t pr = (uint8_t)clamp255((int)(sr / sw + 0.5));
        uint8_t pg = (uint8_t)clamp255((int)(sg / sw + 0.5));
        uint8_t pb = (uint8_t)clamp255((int)(sb / sw + 0.5));
        uint8_t pa = (uint8_t)clamp255((int)(sa / sw + 0.5));
        uint8_t pidx = (uint8_t)(start_idx + b);
        out_clut_rgba[pidx * 4 + 0] = pr;
        out_clut_rgba[pidx * 4 + 1] = pg;
        out_clut_rgba[pidx * 4 + 2] = pb;
        out_clut_rgba[pidx * 4 + 3] = pa;

        /* Snap effective display alpha to PS2 GS 0..128 quantization for dithering accuracy */
        int ps2_a = (pa * 128 + 127) / 255;
        int eff_a = (ps2_a * 255) / 128;
        if (eff_a > 255) eff_a = 255;

        PalLookup pl;
        pl.r = pr; pl.g = pg; pl.b = pb; pl.a = eff_a; pl.idx = pidx;
        pl.s = pr + pg + pb + eff_a;
        pal_all[n_pal_all++] = pl;
        if (pa == 255) {
            pl.s = pr + pg + pb;
            pal_opa[n_pal_opa++] = pl;
        }
    }
    free(entries);

    if (n_pal_opa > 0) qsort(pal_opa, (size_t)n_pal_opa, sizeof(PalLookup), cmp_pal_s);
    if (n_pal_all > 0) qsort(pal_all, (size_t)n_pal_all, sizeof(PalLookup), cmp_pal_s);

    /* 4D Floyd-Steinberg error diffusion (2 row error buffers) */
    int stride = (w + 2) * 4;
    int16_t *err_cur = (int16_t *)calloc((size_t)stride, sizeof(int16_t));
    int16_t *err_nxt = (int16_t *)calloc((size_t)stride, sizeof(int16_t));
    if (!err_cur || !err_nxt) { free(err_cur); free(err_nxt); return -4; }

    for (int y = 0; y < h; y++) {
        memset(err_nxt, 0, (size_t)stride * sizeof(int16_t));
        for (int x = 0; x < w; x++) {
            int p = (y * w + x) * 4;
            uint8_t src_a = rgba[p + 3];
            if (src_a == 0 && reserve_zero) {
                out_idx[y * w + x] = 0;
                continue;
            }
            int epos = (x + 1) * 4;
            int r = clamp255((int)rgba[p + 0] + (err_cur[epos + 0] >> 4));
            int g = clamp255((int)rgba[p + 1] + (err_cur[epos + 1] >> 4));
            int b = clamp255((int)rgba[p + 2] + (err_cur[epos + 2] >> 4));
            int a = (src_a == 255) ? 255 : clamp255((int)src_a + (err_cur[epos + 3] >> 4));
            if (src_a > 0 && a == 0 && reserve_zero) a = 1;

            uint8_t pidx;
            if (src_a == 255 && n_pal_opa > 0) {
                pidx = find_nearest_3d(pal_opa, n_pal_opa, r, g, b);
            } else {
                pidx = find_nearest_4d(pal_all, n_pal_all, r, g, b, a);
            }
            out_idx[y * w + x] = pidx;

            int qr = out_clut_rgba[pidx * 4 + 0];
            int qg = out_clut_rgba[pidx * 4 + 1];
            int qb = out_clut_rgba[pidx * 4 + 2];
            int qa = (out_clut_rgba[pidx * 4 + 3] * 128 + 127) / 255;
            qa = (qa * 255) / 128; if (qa > 255) qa = 255;

            int er = clamp_err(r - qr);
            int eg = clamp_err(g - qg);
            int eb = clamp_err(b - qb);
            int ea = (src_a == 255) ? 0 : clamp_err(a - qa);

            if (x + 1 < w) {
                err_cur[(x + 2) * 4 + 0] += er * 7;
                err_cur[(x + 2) * 4 + 1] += eg * 7;
                err_cur[(x + 2) * 4 + 2] += eb * 7;
                err_cur[(x + 2) * 4 + 3] += ea * 7;
            }
            if (y + 1 < h) {
                if (x > 0) {
                    err_nxt[x * 4 + 0] += er * 3;
                    err_nxt[x * 4 + 1] += eg * 3;
                    err_nxt[x * 4 + 2] += eb * 3;
                    err_nxt[x * 4 + 3] += ea * 3;
                }
                err_nxt[(x + 1) * 4 + 0] += er * 5;
                err_nxt[(x + 1) * 4 + 1] += eg * 5;
                err_nxt[(x + 1) * 4 + 2] += eb * 5;
                err_nxt[(x + 1) * 4 + 3] += ea * 5;
                if (x + 1 < w) {
                    err_nxt[(x + 2) * 4 + 0] += er;
                    err_nxt[(x + 2) * 4 + 1] += eg;
                    err_nxt[(x + 2) * 4 + 2] += eb;
                    err_nxt[(x + 2) * 4 + 3] += ea;
                }
            }
        }
        int16_t *swp = err_cur; err_cur = err_nxt; err_nxt = swp;
    }

    free(err_cur); free(err_nxt);
    return n_boxes;
}

/* ---- Lossless PC EPA (EP\x01\x01 mode 1=BGR / mode 2=BGRA) Encoder ---- */

__declspec(dllexport) int encode_epa(const uint8_t *planar, int w, int h, int mode, uint8_t *out, int max_out) {
    int bpp = (mode == 1) ? 3 : (mode == 2) ? 4 : (mode == 0) ? 1 : 0;
    if (!bpp || w <= 0 || h <= 0) return -1;
    int total = w * h * bpp;
    if (max_out < 16 + total + (total / 15) + 64) return -2;

    out[0] = 'E'; out[1] = 'P'; out[2] = 1; out[3] = 1;
    wr32(out + 4, (uint32_t)mode);
    wr32(out + 8, (uint32_t)w);
    wr32(out + 12, (uint32_t)h);

    int offsets[16] = {
        0, 1, w, w + 1, 2, w - 1, 2 * w, 3,
        2 * (w + 1), w + 2, 2 * w + 1, 2 * w - 1, 2 * (w - 1), w - 2, 3 * w, 4
    };

    int op = 16;
    int pos = 0;
    int lit_start = 0;
    int lit_len = 0;

    #define FLUSH_LIT() do { \
        while (lit_len > 0) { \
            int chunk = (lit_len > 15) ? 15 : lit_len; \
            out[op++] = (uint8_t)chunk; \
            memcpy(out + op, planar + lit_start, chunk); \
            op += chunk; \
            lit_start += chunk; \
            lit_len -= chunk; \
        } \
    } while(0)

    while (pos < total) {
        int best_idx = 0;
        int best_len = 0;
        int max_m = total - pos;
        if (max_m > 2047) max_m = 2047;

        for (int idx = 1; idx < 16; idx++) {
            int off = offsets[idx];
            if (off <= 0 || off > pos) continue;
            if (planar[pos] != planar[pos - off]) continue;
            if (max_m >= 2 && planar[pos + 1] != planar[pos + 1 - off]) continue;
            int ml = 0;
            while (ml < max_m && planar[pos + ml] == planar[pos + ml - off]) ml++;
            if (ml > best_len) {
                best_len = ml;
                best_idx = idx;
                if (best_len >= 2047) break;
            }
        }

        int min_gain = (best_len >= 8) ? 3 : 2;
        if (best_len >= min_gain) {
            FLUSH_LIT();
            if (best_len < 8) {
                out[op++] = (uint8_t)((best_idx << 4) | best_len);
            } else {
                out[op++] = (uint8_t)((best_idx << 4) | 0x08 | ((best_len >> 8) & 0x07));
                out[op++] = (uint8_t)(best_len & 0xff);
            }
            pos += best_len;
            lit_start = pos;
        } else {
            if (lit_len == 0) lit_start = pos;
            lit_len++;
            pos++;
            if (lit_len == 15) FLUSH_LIT();
        }
    }
    FLUSH_LIT();
    #undef FLUSH_LIT
    return op;
}


