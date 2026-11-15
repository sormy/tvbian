/*
 * VP9's frame headers as the stateless controls take them: the uncompressed header read with
 * the state earlier frames left, and the compressed header's probability deltas through the
 * boolean decoder (VP9 bitstream specification 6.2, 6.3 and 9.2).
 */
#include <errno.h>
#include <string.h>

#include "bitstream.h"
#include "vp9_header.h"

enum {
    FRAME_MARKER = 2,
    SYNC_CODE = 0x498342,
    KEY_FRAME = 0,
    COLOR_SPACE_RGB = 7,
    REFS_PER_FRAME = 3,
    MAX_SEGMENTS = 8,
    SEG_FEATURES = 4,
    SEG_TREE_PROBS = 7,
    SEG_PRED_PROBS = 3,
    PROB_NOT_CODED = 255,
    MIN_TILE_WIDTH_B64 = 4,
    MAX_TILE_WIDTH_B64 = 64,
    RESET_CURRENT = 2,
    TX_MODE_ALLOW_32X32 = 3,
    TX_MODE_SELECT = 4,
    BOOL_HALF = 128,
    DIFF_UPDATE_PROB = 252,
    INV_MAP_STEP = 13,
    INV_MAP_FIRST = 7,
    INV_MAP_SPREAD = 20,
    MAX_PROB = 255,
};

static const int8_t default_ref_deltas[4] = { 1, 0, -1, -1 };
static const uint8_t feature_bits[SEG_FEATURES] = { 8, 6, 2, 0 };
static const bool feature_signed[SEG_FEATURES] = { true, true, false, false };
/* read_interpolation_filter's literal to the filter type */
static const uint8_t filter_of_literal[4] = { 1, 0, 2, 3 };
static const uint8_t biggest_tx_size[5] = { 0, 1, 2, 3, 3 };

static int signed_bits(struct bit_reader *br, unsigned count)
{
    int value = br_bits(br, count);
    return br_bits(br, 1) ? -value : value;
}

#define COLOR_FLAGS                                                                                \
    (V4L2_VP9_FRAME_FLAG_X_SUBSAMPLING | V4L2_VP9_FRAME_FLAG_Y_SUBSAMPLING |                       \
     V4L2_VP9_FRAME_FLAG_COLOR_RANGE_FULL_SWING)

static void color_config(struct bit_reader *br, struct v4l2_ctrl_vp9_frame *f)
{
    bool four_four_four = f->profile == 1 || f->profile == 3;
    f->bit_depth = f->profile >= 2 ? (br_bits(br, 1) ? 12 : 10) : 8;
    if (br_bits(br, 3) != COLOR_SPACE_RGB) {
        if (br_bits(br, 1))
            f->flags |= V4L2_VP9_FRAME_FLAG_COLOR_RANGE_FULL_SWING;
        if (!four_four_four) {
            f->flags |= V4L2_VP9_FRAME_FLAG_X_SUBSAMPLING | V4L2_VP9_FRAME_FLAG_Y_SUBSAMPLING;
            return;
        }
        if (br_bits(br, 1))
            f->flags |= V4L2_VP9_FRAME_FLAG_X_SUBSAMPLING;
        if (br_bits(br, 1))
            f->flags |= V4L2_VP9_FRAME_FLAG_Y_SUBSAMPLING;
        br_bits(br, 1);
        return;
    }
    f->flags |= V4L2_VP9_FRAME_FLAG_COLOR_RANGE_FULL_SWING;
    if (four_four_four)
        br_bits(br, 1);
}

static void frame_size(struct bit_reader *br, struct v4l2_ctrl_vp9_frame *f)
{
    f->frame_width_minus_1 = br_bits(br, 16);
    f->frame_height_minus_1 = br_bits(br, 16);
}

static void render_size(struct bit_reader *br, struct v4l2_ctrl_vp9_frame *f)
{
    bool different = br_bits(br, 1);
    f->render_width_minus_1 = different ? br_bits(br, 16) : f->frame_width_minus_1;
    f->render_height_minus_1 = different ? br_bits(br, 16) : f->frame_height_minus_1;
}

static void loop_filter_params(struct bit_reader *br, struct vp9_persistent *st,
                               struct v4l2_vp9_loop_filter *lf)
{
    lf->level = br_bits(br, 6);
    lf->sharpness = br_bits(br, 3);
    if (br_bits(br, 1)) {
        lf->flags |= V4L2_VP9_LOOP_FILTER_FLAG_DELTA_ENABLED;
        if (br_bits(br, 1)) {
            lf->flags |= V4L2_VP9_LOOP_FILTER_FLAG_DELTA_UPDATE;
            for (unsigned i = 0; i < 4; i++)
                if (br_bits(br, 1))
                    st->ref_deltas[i] = signed_bits(br, 6);
            for (unsigned i = 0; i < 2; i++)
                if (br_bits(br, 1))
                    st->mode_deltas[i] = signed_bits(br, 6);
        }
    }
    memcpy(lf->ref_deltas, st->ref_deltas, sizeof(lf->ref_deltas));
    memcpy(lf->mode_deltas, st->mode_deltas, sizeof(lf->mode_deltas));
}

static int8_t delta_q(struct bit_reader *br)
{
    return br_bits(br, 1) ? signed_bits(br, 4) : 0;
}

static uint8_t read_prob(struct bit_reader *br)
{
    return br_bits(br, 1) ? br_bits(br, 8) : PROB_NOT_CODED;
}

static void segmentation_params(struct bit_reader *br, struct vp9_persistent *st,
                                struct v4l2_vp9_segmentation *seg)
{
    if (br_bits(br, 1)) {
        seg->flags |= V4L2_VP9_SEGMENTATION_FLAG_ENABLED;
        if (br_bits(br, 1)) {
            seg->flags |= V4L2_VP9_SEGMENTATION_FLAG_UPDATE_MAP;
            for (unsigned i = 0; i < SEG_TREE_PROBS; i++)
                seg->tree_probs[i] = read_prob(br);
            bool temporal = br_bits(br, 1);
            if (temporal)
                seg->flags |= V4L2_VP9_SEGMENTATION_FLAG_TEMPORAL_UPDATE;
            for (unsigned i = 0; i < SEG_PRED_PROBS; i++)
                seg->pred_probs[i] = temporal ? read_prob(br) : PROB_NOT_CODED;
        }
        if (br_bits(br, 1)) {
            seg->flags |= V4L2_VP9_SEGMENTATION_FLAG_UPDATE_DATA;
            st->abs_or_delta_update = br_bits(br, 1);
            for (unsigned i = 0; i < MAX_SEGMENTS; i++) {
                st->feature_enabled[i] = 0;
                for (unsigned j = 0; j < SEG_FEATURES; j++) {
                    int value = 0;
                    if (br_bits(br, 1)) {
                        st->feature_enabled[i] |= V4L2_VP9_SEGMENT_FEATURE_ENABLED(j);
                        value = br_bits(br, feature_bits[j]);
                        if (feature_signed[j] && br_bits(br, 1))
                            value = -value;
                    }
                    st->feature_data[i][j] = value;
                }
            }
        }
    }
    if (st->abs_or_delta_update)
        seg->flags |= V4L2_VP9_SEGMENTATION_FLAG_ABS_OR_DELTA_UPDATE;
    memcpy(seg->feature_data, st->feature_data, sizeof(seg->feature_data));
    memcpy(seg->feature_enabled, st->feature_enabled, sizeof(seg->feature_enabled));
}

static void tile_info(struct bit_reader *br, struct v4l2_ctrl_vp9_frame *f)
{
    unsigned sb64_cols = ((f->frame_width_minus_1 + 8) / 8 + 7) / 8;
    unsigned min_log2 = 0, max_log2 = 1;
    while ((unsigned)MAX_TILE_WIDTH_B64 << min_log2 < sb64_cols)
        min_log2++;
    while ((sb64_cols >> max_log2) >= MIN_TILE_WIDTH_B64)
        max_log2++;
    f->tile_cols_log2 = min_log2;
    while (f->tile_cols_log2 < max_log2 - 1 && br_bits(br, 1))
        f->tile_cols_log2++;
    f->tile_rows_log2 = br_bits(br, 1);
    if (f->tile_rows_log2)
        f->tile_rows_log2 += br_bits(br, 1);
}

/* what a key frame, an intra-only frame or an error-resilient one starts from */
/* the deltas and segment features back to their defaults; the colour config is not of them */
static void setup_past_independence(struct vp9_persistent *st)
{
    *st = (struct vp9_persistent){ .bit_depth = st->bit_depth, .color_flags = st->color_flags };
    memcpy(st->ref_deltas, default_ref_deltas, sizeof(st->ref_deltas));
}

int vp9_parse_uncompressed(struct vp9_persistent *st, const uint8_t *data, size_t size,
                           unsigned width, unsigned height, struct v4l2_ctrl_vp9_frame *f)
{
    struct bit_reader br;
    unsigned reset_frame_context = 0;
    bool intra_only = false;

    memset(f, 0, sizeof(*f));
    br_init_unescaped(&br, data, size);
    if (br_bits(&br, 2) != FRAME_MARKER)
        return -EINVAL;
    f->profile = br_bits(&br, 1);
    f->profile |= br_bits(&br, 1) << 1;
    if (f->profile == 3)
        br_bits(&br, 1);
    /* a shown copy of a decoded frame: nothing to decode */
    if (br_bits(&br, 1))
        return -ENOENT;
    bool key_frame = br_bits(&br, 1) == KEY_FRAME;
    bool show_frame = br_bits(&br, 1);
    bool error_resilient = br_bits(&br, 1);
    f->flags |= (key_frame ? V4L2_VP9_FRAME_FLAG_KEY_FRAME : 0) |
                (show_frame ? V4L2_VP9_FRAME_FLAG_SHOW_FRAME : 0) |
                (error_resilient ? V4L2_VP9_FRAME_FLAG_ERROR_RESILIENT : 0);
    if (key_frame) {
        if (br_bits(&br, 24) != SYNC_CODE)
            return -EINVAL;
        color_config(&br, f);
        st->bit_depth = f->bit_depth;
        st->color_flags = f->flags & COLOR_FLAGS;
        frame_size(&br, f);
        render_size(&br, f);
    } else {
        intra_only = !show_frame && br_bits(&br, 1);
        if (!error_resilient)
            reset_frame_context = br_bits(&br, 2);
        if (intra_only) {
            f->flags |= V4L2_VP9_FRAME_FLAG_INTRA_ONLY;
            if (br_bits(&br, 24) != SYNC_CODE)
                return -EINVAL;
            if (f->profile > 0) {
                color_config(&br, f);
            } else {
                f->bit_depth = 8;
                f->flags |= V4L2_VP9_FRAME_FLAG_X_SUBSAMPLING | V4L2_VP9_FRAME_FLAG_Y_SUBSAMPLING;
            }
            st->bit_depth = f->bit_depth;
            st->color_flags = f->flags & COLOR_FLAGS;
            br_bits(&br, 8);
            frame_size(&br, f);
            render_size(&br, f);
        } else {
            /* an inter frame's format is its sequence's, from the last key or intra-only frame */
            f->bit_depth = st->bit_depth;
            f->flags |= st->color_flags;
            br_bits(&br, 8);
            for (unsigned i = 0; i < REFS_PER_FRAME; i++) {
                br_bits(&br, 3);
                f->ref_frame_sign_bias |= br_bits(&br, 1) << i;
            }
            bool found_ref = false;
            for (unsigned i = 0; i < REFS_PER_FRAME && !found_ref; i++)
                found_ref = br_bits(&br, 1);
            if (found_ref) {
                f->frame_width_minus_1 = width - 1;
                f->frame_height_minus_1 = height - 1;
            } else {
                frame_size(&br, f);
            }
            render_size(&br, f);
            if (br_bits(&br, 1))
                f->flags |= V4L2_VP9_FRAME_FLAG_ALLOW_HIGH_PREC_MV;
            f->interpolation_filter = br_bits(&br, 1) ? V4L2_VP9_INTERP_FILTER_SWITCHABLE
                                                      : filter_of_literal[br_bits(&br, 2)];
        }
    }
    if (!error_resilient) {
        if (br_bits(&br, 1))
            f->flags |= V4L2_VP9_FRAME_FLAG_REFRESH_FRAME_CTX;
        if (br_bits(&br, 1))
            f->flags |= V4L2_VP9_FRAME_FLAG_PARALLEL_DEC_MODE;
    } else {
        f->flags |= V4L2_VP9_FRAME_FLAG_PARALLEL_DEC_MODE;
    }
    f->frame_context_idx = br_bits(&br, 2);
    /* the bitstream's 2 and 3 are the control's SPEC and ALL */
    f->reset_frame_context = reset_frame_context >= RESET_CURRENT ? reset_frame_context - 1 : 0;
    if (key_frame || intra_only || error_resilient)
        setup_past_independence(st);
    loop_filter_params(&br, st, &f->lf);
    f->quant.base_q_idx = br_bits(&br, 8);
    f->quant.delta_q_y_dc = delta_q(&br);
    f->quant.delta_q_uv_dc = delta_q(&br);
    f->quant.delta_q_uv_ac = delta_q(&br);
    segmentation_params(&br, st, &f->seg);
    tile_info(&br, f);
    f->compressed_header_size = br_bits(&br, 16);
    f->uncompressed_header_size = (br_position(&br) + 7) / 8;
    if (br.overrun || !f->compressed_header_size ||
        (size_t)f->uncompressed_header_size + f->compressed_header_size > size)
        return -EINVAL;
    return 0;
}

/* 9.2: the boolean decoder, a bit at a time as the specification reads it */
struct bool_decoder {
    struct bit_reader br;
    unsigned value;
    unsigned range;
    size_t bits_left;
};

static bool read_bool(struct bool_decoder *d, unsigned probability)
{
    unsigned split = 1 + (((d->range - 1) * probability) >> 8);
    bool bit = d->value >= split;
    if (bit) {
        d->range -= split;
        d->value -= split;
    } else {
        d->range = split;
    }
    while (d->range < BOOL_HALF) {
        unsigned next = d->bits_left ? (d->bits_left--, br_bits(&d->br, 1)) : 0;
        d->range <<= 1;
        d->value = (d->value << 1) | next;
    }
    return bit;
}

static unsigned read_literal(struct bool_decoder *d, unsigned count)
{
    unsigned value = 0;
    while (count--)
        value = value << 1 | read_bool(d, BOOL_HALF);
    return value;
}

static bool bool_init(struct bool_decoder *d, const uint8_t *data, size_t size)
{
    if (!size)
        return false;
    br_init_unescaped(&d->br, data, size);
    d->value = br_bits(&d->br, 8);
    d->range = MAX_PROB;
    d->bits_left = 8 * size - 8;
    /* the marker bit */
    return !read_bool(d, BOOL_HALF);
}

/* 9.2.3: what follows the last symbol must be zeros */
static bool padding_is_zero(struct bool_decoder *d)
{
    while (d->bits_left--)
        if (br_bits(&d->br, 1))
            return false;
    return true;
}

/* the delta as the kernel takes it: 6.3.5's inv_map_table entry, from 6.3.6's subexponent */
static uint8_t inv_map(unsigned index)
{
    if (index < INV_MAP_SPREAD)
        return INV_MAP_FIRST + INV_MAP_STEP * index;
    unsigned value = 0;
    for (unsigned rank = INV_MAP_SPREAD - 1; rank < index && value < MAX_PROB - 1;)
        if (++value % INV_MAP_STEP != INV_MAP_FIRST)
            rank++;
    return index < MAX_PROB - 1 ? value : MAX_PROB - 2;
}

static unsigned decode_term_subexp(struct bool_decoder *d)
{
    if (!read_literal(d, 1))
        return read_literal(d, 4);
    if (!read_literal(d, 1))
        return read_literal(d, 4) + 16;
    if (!read_literal(d, 1))
        return read_literal(d, 5) + 32;
    unsigned v = read_literal(d, 7);
    return v < 65 ? v + 64 : (v << 1) - 1 + read_literal(d, 1);
}

static void diff_update(struct bool_decoder *d, uint8_t *probabilities, size_t count)
{
    for (size_t i = 0; i < count; i++)
        probabilities[i] = read_bool(d, DIFF_UPDATE_PROB) ? inv_map(decode_term_subexp(d)) : 0;
}

/* a motion vector probability is sent whole, 7 bits with the low bit set */
static void mv_update(struct bool_decoder *d, uint8_t *probabilities, size_t count)
{
    for (size_t i = 0; i < count; i++)
        probabilities[i] = read_bool(d, DIFF_UPDATE_PROB) ? read_literal(d, 7) << 1 | 1 : 0;
}

static void coef_probs(struct bool_decoder *d, struct v4l2_ctrl_vp9_compressed_hdr *h)
{
    for (unsigned tx = 0; tx <= biggest_tx_size[h->tx_mode]; tx++) {
        if (!read_literal(d, 1))
            continue;
        for (unsigned i = 0; i < 2; i++)
            for (unsigned j = 0; j < 2; j++)
                for (unsigned k = 0; k < 6; k++)
                    for (unsigned l = 0; l < (k ? 6u : 3u); l++)
                        diff_update(d, h->coef[tx][i][j][k][l], 3);
    }
}

static unsigned reference_mode(struct bool_decoder *d, const struct v4l2_ctrl_vp9_frame *f)
{
    unsigned last = f->ref_frame_sign_bias & V4L2_VP9_SIGN_BIAS_LAST ? 1 : 0;
    bool golden_differs = !!(f->ref_frame_sign_bias & V4L2_VP9_SIGN_BIAS_GOLDEN) != last;
    bool alt_differs = !!(f->ref_frame_sign_bias & V4L2_VP9_SIGN_BIAS_ALT) != last;
    if (!(golden_differs || alt_differs) || !read_literal(d, 1))
        return V4L2_VP9_REFERENCE_MODE_SINGLE_REFERENCE;
    return read_literal(d, 1) ? V4L2_VP9_REFERENCE_MODE_SELECT
                              : V4L2_VP9_REFERENCE_MODE_COMPOUND_REFERENCE;
}

static void mv_probs(struct bool_decoder *d, const struct v4l2_ctrl_vp9_frame *f,
                     struct v4l2_vp9_mv_probs *mv)
{
    mv_update(d, mv->joint, sizeof(mv->joint));
    for (unsigned i = 0; i < 2; i++) {
        mv_update(d, &mv->sign[i], 1);
        mv_update(d, mv->classes[i], sizeof(mv->classes[i]));
        mv_update(d, &mv->class0_bit[i], 1);
        mv_update(d, mv->bits[i], sizeof(mv->bits[i]));
    }
    for (unsigned i = 0; i < 2; i++) {
        mv_update(d, &mv->class0_fr[i][0][0], sizeof(mv->class0_fr[i]));
        mv_update(d, mv->fr[i], sizeof(mv->fr[i]));
    }
    if (f->flags & V4L2_VP9_FRAME_FLAG_ALLOW_HIGH_PREC_MV) {
        for (unsigned i = 0; i < 2; i++) {
            mv_update(d, &mv->class0_hp[i], 1);
            mv_update(d, &mv->hp[i], 1);
        }
    }
}

int vp9_parse_compressed(const uint8_t *data, size_t size, struct v4l2_ctrl_vp9_frame *f,
                         struct v4l2_ctrl_vp9_compressed_hdr *h)
{
    struct bool_decoder d;
    const struct v4l2_vp9_quantization *q = &f->quant;
    bool lossless = !q->base_q_idx && !q->delta_q_y_dc && !q->delta_q_uv_dc && !q->delta_q_uv_ac;
    bool intra = f->flags & (V4L2_VP9_FRAME_FLAG_KEY_FRAME | V4L2_VP9_FRAME_FLAG_INTRA_ONLY);

    memset(h, 0, sizeof(*h));
    f->reference_mode = V4L2_VP9_REFERENCE_MODE_SINGLE_REFERENCE;
    if (!bool_init(&d, data, size))
        return -EINVAL;
    if (!lossless) {
        h->tx_mode = read_literal(&d, 2);
        if (h->tx_mode == TX_MODE_ALLOW_32X32)
            h->tx_mode += read_literal(&d, 1);
    }
    if (h->tx_mode == TX_MODE_SELECT) {
        diff_update(&d, &h->tx8[0][0], sizeof(h->tx8));
        diff_update(&d, &h->tx16[0][0], sizeof(h->tx16));
        diff_update(&d, &h->tx32[0][0], sizeof(h->tx32));
    }
    coef_probs(&d, h);
    diff_update(&d, h->skip, sizeof(h->skip));
    if (!intra) {
        diff_update(&d, &h->inter_mode[0][0], sizeof(h->inter_mode));
        if (f->interpolation_filter == V4L2_VP9_INTERP_FILTER_SWITCHABLE)
            diff_update(&d, &h->interp_filter[0][0], sizeof(h->interp_filter));
        diff_update(&d, h->is_inter, sizeof(h->is_inter));
        f->reference_mode = reference_mode(&d, f);
        if (f->reference_mode == V4L2_VP9_REFERENCE_MODE_SELECT)
            diff_update(&d, h->comp_mode, sizeof(h->comp_mode));
        if (f->reference_mode != V4L2_VP9_REFERENCE_MODE_COMPOUND_REFERENCE)
            diff_update(&d, &h->single_ref[0][0], sizeof(h->single_ref));
        if (f->reference_mode != V4L2_VP9_REFERENCE_MODE_SINGLE_REFERENCE)
            diff_update(&d, h->comp_ref, sizeof(h->comp_ref));
        diff_update(&d, &h->y_mode[0][0], sizeof(h->y_mode));
        diff_update(&d, &h->partition[0][0], sizeof(h->partition));
        mv_probs(&d, f, &h->mv);
    }
    return !d.br.overrun && padding_is_zero(&d) ? 0 : -EINVAL;
}
