/*
 * vp9_header.c's compressed-header parse against headers written here: libvpx's boolean
 * encoder, the syntax of the specification's 6.3, random updates in every branch, and
 * FFmpeg's inv_map_table as the reference for the deltas the kernel takes.
 */
#include <string.h>

#include "../../src/vp9_header.h"
#include "unit.h"

#define ROUNDS 3000
#define HEADER_CAPACITY 8192
#define DIFF_UPDATE_PROB 252
#define HALF 128
#define FLUSH_BITS 32

/* libavcodec/vp9.c */
static const uint8_t inv_map_table[255] = {
    7,   20,  33,  46,  59,  72,  85,  98,  111, 124, 137, 150, 163, 176, 189, 202, 215, 228, 241,
    254, 1,   2,   3,   4,   5,   6,   8,   9,   10,  11,  12,  13,  14,  15,  16,  17,  18,  19,
    21,  22,  23,  24,  25,  26,  27,  28,  29,  30,  31,  32,  34,  35,  36,  37,  38,  39,  40,
    41,  42,  43,  44,  45,  47,  48,  49,  50,  51,  52,  53,  54,  55,  56,  57,  58,  60,  61,
    62,  63,  64,  65,  66,  67,  68,  69,  70,  71,  73,  74,  75,  76,  77,  78,  79,  80,  81,
    82,  83,  84,  86,  87,  88,  89,  90,  91,  92,  93,  94,  95,  96,  97,  99,  100, 101, 102,
    103, 104, 105, 106, 107, 108, 109, 110, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122,
    123, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 138, 139, 140, 141, 142, 143,
    144, 145, 146, 147, 148, 149, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 164,
    165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 177, 178, 179, 180, 181, 182, 183, 184,
    185, 186, 187, 188, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 203, 204, 205,
    206, 207, 208, 209, 210, 211, 212, 213, 214, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225,
    226, 227, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 242, 243, 244, 245, 246,
    247, 248, 249, 250, 251, 252, 253, 253,
};

/* libvpx's vpx_writer */
struct bool_encoder {
    uint8_t data[HEADER_CAPACITY];
    size_t size;
    uint32_t low;
    unsigned range;
    int count;
};

static void encoder_init(struct bool_encoder *e)
{
    memset(e, 0, sizeof(*e));
    e->range = 255;
    e->count = -24;
}

static void write_bool(struct bool_encoder *e, bool bit, unsigned probability)
{
    unsigned split = 1 + (((e->range - 1) * probability) >> 8);
    unsigned range = bit ? e->range - split : split;
    uint32_t low = e->low + (bit ? split : 0);
    int shift = 0;
    while ((range << shift) < HALF)
        shift++;
    range <<= shift;
    e->count += shift;
    if (e->count >= 0) {
        int offset = shift - e->count;
        if ((low << (offset - 1)) & 0x80000000) {
            size_t x = e->size;
            while (x && e->data[x - 1] == 0xff)
                e->data[--x] = 0;
            e->data[x - 1]++;
        }
        e->data[e->size++] = (uint8_t)(low >> (24 - offset));
        low <<= offset;
        shift = e->count;
        low &= 0xffffff;
        e->count -= 8;
    }
    e->low = low << shift;
    e->range = range;
}

static void write_literal(struct bool_encoder *e, unsigned value, unsigned bits)
{
    while (bits--)
        write_bool(e, (value >> bits) & 1, HALF);
}

static void encoder_flush(struct bool_encoder *e)
{
    for (unsigned i = 0; i < FLUSH_BITS; i++)
        write_bool(e, 0, HALF);
}

static uint32_t next_random(uint32_t *state)
{
    *state ^= *state << 13;
    *state ^= *state >> 17;
    *state ^= *state << 5;
    return *state;
}

/* 6.3.6, the encoder's side */
static void write_subexp(struct bool_encoder *e, unsigned value)
{
    if (value < 16) {
        write_literal(e, 0, 1);
        write_literal(e, value, 4);
    } else if (value < 32) {
        write_literal(e, 2, 2);
        write_literal(e, value - 16, 4);
    } else if (value < 64) {
        write_literal(e, 6, 3);
        write_literal(e, value - 32, 5);
    } else if (value < 129) {
        write_literal(e, 7, 3);
        write_literal(e, value - 64, 7);
    } else {
        write_literal(e, 7, 3);
        write_literal(e, (value + 1) >> 1, 7);
        write_literal(e, (value + 1) & 1, 1);
    }
}

struct writer {
    struct bool_encoder e;
    uint32_t seed;
};

/* each probability updated or not at random: the delta the parse must give, 0 for none */
static void diff_updates(struct writer *w, uint8_t *expected, size_t count)
{
    for (size_t i = 0; i < count; i++) {
        bool update = next_random(&w->seed) % 3 == 0;
        write_bool(&w->e, update, DIFF_UPDATE_PROB);
        unsigned index = next_random(&w->seed) % 255;
        if (update)
            write_subexp(&w->e, index);
        expected[i] = update ? inv_map_table[index] : 0;
    }
}

static void mv_updates(struct writer *w, uint8_t *expected, size_t count)
{
    for (size_t i = 0; i < count; i++) {
        bool update = next_random(&w->seed) % 3 == 0;
        unsigned value = next_random(&w->seed) % 128;
        write_bool(&w->e, update, DIFF_UPDATE_PROB);
        if (update)
            write_literal(&w->e, value, 7);
        expected[i] = update ? value << 1 | 1 : 0;
    }
}

static void write_mv(struct writer *w, bool high_precision, struct v4l2_vp9_mv_probs *mv)
{
    mv_updates(w, mv->joint, sizeof(mv->joint));
    for (unsigned i = 0; i < 2; i++) {
        mv_updates(w, &mv->sign[i], 1);
        mv_updates(w, mv->classes[i], sizeof(mv->classes[i]));
        mv_updates(w, &mv->class0_bit[i], 1);
        mv_updates(w, mv->bits[i], sizeof(mv->bits[i]));
    }
    for (unsigned i = 0; i < 2; i++) {
        for (unsigned j = 0; j < 2; j++)
            mv_updates(w, mv->class0_fr[i][j], sizeof(mv->class0_fr[i][j]));
        mv_updates(w, mv->fr[i], sizeof(mv->fr[i]));
    }
    for (unsigned i = 0; high_precision && i < 2; i++) {
        mv_updates(w, &mv->class0_hp[i], 1);
        mv_updates(w, &mv->hp[i], 1);
    }
}

/* a random frame's compressed header, and the controls it must parse to */
static void write_header(struct writer *w, struct v4l2_ctrl_vp9_frame *f,
                         struct v4l2_ctrl_vp9_compressed_hdr *h, unsigned *reference_mode)
{
    static const unsigned biggest_tx[5] = { 0, 1, 2, 3, 3 };
    uint32_t r = next_random(&w->seed);
    memset(f, 0, sizeof(*f));
    memset(h, 0, sizeof(*h));
    f->quant.base_q_idx = r % 7 == 0 ? 0 : 1 + r % 200;
    f->flags = (r & 0x100 ? V4L2_VP9_FRAME_FLAG_KEY_FRAME : 0) |
               (r & 0x200 ? V4L2_VP9_FRAME_FLAG_INTRA_ONLY : 0) |
               (r & 0x400 ? V4L2_VP9_FRAME_FLAG_ALLOW_HIGH_PREC_MV : 0);
    f->interpolation_filter = (r >> 12) % 5;
    f->ref_frame_sign_bias = (r >> 16) & 7;
    bool intra = f->flags & (V4L2_VP9_FRAME_FLAG_KEY_FRAME | V4L2_VP9_FRAME_FLAG_INTRA_ONLY);

    encoder_init(&w->e);
    write_bool(&w->e, 0, HALF);
    if (f->quant.base_q_idx) {
        h->tx_mode = (r >> 20) % 5;
        write_literal(&w->e, h->tx_mode < 4 ? h->tx_mode : 3, 2);
        if (h->tx_mode >= 3)
            write_literal(&w->e, h->tx_mode == 4, 1);
    }
    if (h->tx_mode == 4) {
        diff_updates(w, &h->tx8[0][0], sizeof(h->tx8));
        diff_updates(w, &h->tx16[0][0], sizeof(h->tx16));
        diff_updates(w, &h->tx32[0][0], sizeof(h->tx32));
    }
    for (unsigned tx = 0; tx <= biggest_tx[h->tx_mode]; tx++) {
        bool update = next_random(&w->seed) & 1;
        write_literal(&w->e, update, 1);
        for (unsigned i = 0; update && i < 2; i++)
            for (unsigned j = 0; j < 2; j++)
                for (unsigned k = 0; k < 6; k++)
                    for (unsigned l = 0; l < (k ? 6u : 3u); l++)
                        diff_updates(w, h->coef[tx][i][j][k][l], 3);
    }
    diff_updates(w, h->skip, sizeof(h->skip));
    *reference_mode = V4L2_VP9_REFERENCE_MODE_SINGLE_REFERENCE;
    if (!intra) {
        diff_updates(w, &h->inter_mode[0][0], sizeof(h->inter_mode));
        if (f->interpolation_filter == V4L2_VP9_INTERP_FILTER_SWITCHABLE)
            diff_updates(w, &h->interp_filter[0][0], sizeof(h->interp_filter));
        diff_updates(w, h->is_inter, sizeof(h->is_inter));
        unsigned bias = f->ref_frame_sign_bias;
        bool compound_allowed = bias != 0 && bias != 7;
        if (compound_allowed) {
            *reference_mode = next_random(&w->seed) % 3;
            write_literal(&w->e, *reference_mode != 0, 1);
            if (*reference_mode)
                write_literal(&w->e, *reference_mode == 2, 1);
        }
        if (*reference_mode == 2)
            diff_updates(w, h->comp_mode, sizeof(h->comp_mode));
        if (*reference_mode != 1)
            diff_updates(w, &h->single_ref[0][0], sizeof(h->single_ref));
        if (*reference_mode != 0)
            diff_updates(w, h->comp_ref, sizeof(h->comp_ref));
        diff_updates(w, &h->y_mode[0][0], sizeof(h->y_mode));
        diff_updates(w, &h->partition[0][0], sizeof(h->partition));
        write_mv(w, f->flags & V4L2_VP9_FRAME_FLAG_ALLOW_HIGH_PREC_MV, &h->mv);
    }
    encoder_flush(&w->e);
}

static void test_round_trips(void)
{
    struct writer w = { .seed = 0x9e3779b9 };
    unsigned modes[3] = { 0 }, tx_modes[5] = { 0 };
    for (unsigned round = 0; round < ROUNDS; round++) {
        struct v4l2_ctrl_vp9_frame frame;
        struct v4l2_ctrl_vp9_compressed_hdr expected, parsed;
        unsigned reference_mode;
        write_header(&w, &frame, &expected, &reference_mode);
        int ret = vp9_parse_compressed(w.e.data, w.e.size, &frame, &parsed);
        CHECK(!ret, "round %u: parse failed %d", round, ret);
        CHECK(!memcmp(&expected, &parsed, sizeof(parsed)), "round %u: deltas differ", round);
        CHECK(frame.reference_mode == reference_mode, "round %u: reference mode %u, wrote %u",
              round, frame.reference_mode, reference_mode);
        modes[reference_mode]++;
        tx_modes[expected.tx_mode]++;
    }
    for (unsigned i = 0; i < 3; i++)
        CHECK(modes[i], "reference mode %u never written", i);
    for (unsigned i = 0; i < 5; i++)
        CHECK(tx_modes[i], "tx mode %u never written", i);
}

static void test_damage(void)
{
    struct writer w = { .seed = 7 };
    struct v4l2_ctrl_vp9_frame frame;
    struct v4l2_ctrl_vp9_compressed_hdr expected, parsed;
    unsigned reference_mode;
    write_header(&w, &frame, &expected, &reference_mode);
    CHECK(vp9_parse_compressed(w.e.data, 0, &frame, &parsed), "empty header accepted");
    /* a set marker bit */
    uint8_t marked[] = { 0xff, 0xff };
    CHECK(vp9_parse_compressed(marked, sizeof(marked), &frame, &parsed), "marker bit accepted");
}

int main(void)
{
    test_round_trips();
    test_damage();
    return unit_report("vp9_header");
}
