/*
 * MPEG-4 Part 2 and H.263 onto Cedrus's private controls (linux-sunxi 0805, 0806). The engine
 * parses no header: each run of macroblocks goes as its own request, from its first macroblock's
 * bit, so VA's one slice a VOP is split at its video packets' resync markers, or at H.263's GOB
 * start codes, whose headers are read here for where each run starts and its quantiser.
 */
#include <errno.h>
#include <string.h>

#include "request.h"
/* after request.h: it needs videodev2.h's types */
#include "mpeg4-ctrls.h"

enum {
    VOP_I = 0,
    VOP_P = 1,
    VOP_B = 2,
    VOP_S = 3,
    MB_SIZE = 16,
    MAX_RUNS = 512,
    RESYNC_ZEROS = 16,
    GOB_START_ZEROS = 16,
    GOB_NUMBER_BITS = 5,
    GOB_FRAME_ID_BITS = 2,
    GOB_QUANT_BITS = 5,
    GOB_END_OF_SEQUENCE = 31,
    NUM_CONTROLS = 4,
};

/* a run of macroblocks: its first bit and its end in the slice data, where it starts, its QP */
struct run {
    size_t first_bit;
    size_t end_byte;
    unsigned macroblock;
    unsigned quant;
};

struct bit_cursor {
    const uint8_t *data;
    size_t size;
    size_t bit;
};

static unsigned read_bits(struct bit_cursor *c, unsigned count)
{
    unsigned value = 0;
    while (count--) {
        size_t byte = c->bit / 8;
        unsigned bit = byte < c->size ? (c->data[byte] >> (7 - c->bit % 8)) & 1 : 0;
        value = value << 1 | bit;
        c->bit++;
    }
    return value;
}

/* zeros then a one from bit: how many zeros */
static unsigned zeros_at(const uint8_t *data, size_t size, size_t bit)
{
    struct bit_cursor c = { data, size, bit };
    unsigned zeros = 0;
    while (c.bit < size * 8 && !read_bits(&c, 1))
        zeros++;
    return c.bit <= size * 8 ? zeros : 0;
}

static unsigned bits_for(unsigned count)
{
    unsigned bits = 1;
    while (count > 1u << bits)
        bits++;
    return bits;
}

static unsigned resync_zeros(const VAPictureParameterBufferMPEG4 *pp)
{
    unsigned type = pp->vop_fields.bits.vop_coding_type;
    unsigned forward = pp->vop_fcode_forward, backward = pp->vop_fcode_backward;
    if (type == VOP_I)
        return RESYNC_ZEROS;
    if (type == VOP_B) {
        unsigned widest = forward > backward ? forward : backward;
        return (widest > 2 ? widest : 2) + RESYNC_ZEROS - 1;
    }
    return forward + RESYNC_ZEROS - 1;
}

/* video_packet_header() after its resync marker: where the run starts, its QP, past any HEC */
static void read_packet_header(struct bit_cursor *c, const VAPictureParameterBufferMPEG4 *pp,
                               unsigned macroblocks, struct run *run)
{
    unsigned type = pp->vop_fields.bits.vop_coding_type;
    unsigned resolution = pp->vop_time_increment_resolution;
    run->macroblock = read_bits(c, bits_for(macroblocks));
    run->quant = read_bits(c, pp->quant_precision);
    if (read_bits(c, 1)) {
        while (read_bits(c, 1) && c->bit < c->size * 8)
            ;
        read_bits(c, 1);
        read_bits(c, resolution > 1 ? bits_for(resolution) : 1);
        read_bits(c, 1);
        read_bits(c, 2);
        read_bits(c, 3);
        if (type != VOP_I)
            read_bits(c, 3);
        if (type == VOP_B)
            read_bits(c, 3);
    }
    run->first_bit = c->bit;
}

/* the VOP's data, up to any unit after it: an end of sequence, a packed B-VOP */
static size_t coded_size(const struct slice *s)
{
    for (size_t i = 0; i + 3 <= s->size; i++)
        if (!s->data[i] && !s->data[i + 1] && s->data[i + 2] == 1)
            return i;
    return s->size;
}

/* video packets start byte-aligned at a resync marker */
static unsigned split_packets(const struct slice *s, const VAPictureParameterBufferMPEG4 *pp,
                              unsigned macroblocks, struct run *runs)
{
    unsigned zeros = resync_zeros(pp), count = 1;
    size_t size = coded_size(s);
    for (size_t byte = (runs[0].first_bit + 7) / 8; byte < size && count < MAX_RUNS; byte++) {
        if (s->data[byte] || zeros_at(s->data, s->size, byte * 8) != zeros)
            continue;
        runs[count - 1].end_byte = byte;
        struct bit_cursor c = { s->data, s->size, byte * 8 + zeros + 1 };
        read_packet_header(&c, pp, macroblocks, &runs[count]);
        count++;
    }
    return count;
}

/* GOB headers, aligned or not: 16 zeros, a one, a GOB number neither 0 nor the end of sequence,
 * its first macroblock past the last run's and inside the picture, a quantiser */
static unsigned split_gobs(const struct slice *s, const VAPictureParameterBufferMPEG4 *pp,
                           unsigned macroblocks, struct run *runs)
{
    unsigned count = 1;
    size_t end = s->size * 8;
    for (size_t bit = runs[0].first_bit; bit + GOB_START_ZEROS < end && count < MAX_RUNS; bit++) {
        if (zeros_at(s->data, s->size, bit) != GOB_START_ZEROS)
            continue;
        struct bit_cursor c = { s->data, s->size, bit + GOB_START_ZEROS + 1 };
        unsigned number = read_bits(&c, GOB_NUMBER_BITS);
        unsigned macroblock = number * pp->num_macroblocks_in_gob;
        read_bits(&c, GOB_FRAME_ID_BITS);
        unsigned quant = read_bits(&c, GOB_QUANT_BITS);
        if (!number || number == GOB_END_OF_SEQUENCE || !quant ||
            macroblock <= runs[count - 1].macroblock || macroblock >= macroblocks)
            continue;
        runs[count - 1].end_byte = (bit + 7) / 8;
        runs[count] = (struct run){ .macroblock = macroblock, .quant = quant, .first_bit = c.bit };
        count++;
        bit = c.bit;
    }
    return count;
}

static void fill_vol(struct v4l2_ctrl_mpeg4_vol *vol, const VAPictureParameterBufferMPEG4 *pp)
{
    const typeof(pp->vol_fields.bits) *f = &pp->vol_fields.bits;
    *vol = (struct v4l2_ctrl_mpeg4_vol){ .width = pp->vop_width, .height = pp->vop_height };
    /* FFmpeg fills H.263's other VOL fields from a context that has none */
    if (f->short_video_header) {
        vol->flags = V4L2_MPEG4_VOL_FLAG_SHORT_VIDEO_HEADER;
        return;
    }
    vol->sprite_enable = f->sprite_enable;
    vol->sprite_warping_accuracy = f->sprite_warping_accuracy;
    vol->no_of_sprite_warping_points = pp->no_of_sprite_warping_points;
    const struct {
        bool set;
        uint32_t flag;
    } flags[] = {
        { f->interlaced, V4L2_MPEG4_VOL_FLAG_INTERLACED },
        { f->quant_type, V4L2_MPEG4_VOL_FLAG_QUANT_TYPE },
        { f->quarter_sample, V4L2_MPEG4_VOL_FLAG_QUARTER_SAMPLE },
        { f->resync_marker_disable, V4L2_MPEG4_VOL_FLAG_RESYNC_MARKER_DISABLE },
        { f->data_partitioned, V4L2_MPEG4_VOL_FLAG_DATA_PARTITIONED },
        { f->reversible_vlc, V4L2_MPEG4_VOL_FLAG_REVERSIBLE_VLC },
    };
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); i++)
        if (flags[i].set)
            vol->flags |= flags[i].flag;
}

/* the coding type of the context's latest reference VOP: a B-VOP's backward reference */
struct mpeg4_state {
    uint8_t last_ref_coding_type;
};

static void fill_vop(const struct request_ctx *rq, struct v4l2_ctrl_mpeg4_vop *vop,
                     const VAPictureParameterBufferMPEG4 *pp)
{
    const typeof(pp->vop_fields.bits) *f = &pp->vop_fields.bits;
    struct mpeg4_state *st = rq->codec_state;
    *vop = (struct v4l2_ctrl_mpeg4_vop){
        /* VDPU2 parses video packet headers by it */
        .vop_time_increment_resolution = pp->vop_time_increment_resolution,
        .last_ref_coding_type = st->last_ref_coding_type,
        .trb = pp->TRB,
        .trd = pp->TRD,
        .vop_coding_type = f->vop_coding_type,
        .intra_dc_vlc_thr = f->intra_dc_vlc_thr,
        .vop_fcode_forward = pp->vop_fcode_forward,
        .vop_fcode_backward = pp->vop_fcode_backward,
    };
    if (f->vop_coding_type != VOP_B)
        st->last_ref_coding_type = f->vop_coding_type;
    if (f->vop_coding_type != VOP_I)
        vop->forward_ref_ts = request_timestamp(rq, pp->forward_reference_picture);
    if (f->vop_coding_type == VOP_B)
        vop->backward_ref_ts = request_timestamp(rq, pp->backward_reference_picture);
    if (f->vop_rounding_type)
        vop->flags |= V4L2_MPEG4_VOP_FLAG_ROUNDING_TYPE;
    if (f->top_field_first)
        vop->flags |= V4L2_MPEG4_VOP_FLAG_TOP_FIELD_FIRST;
    if (f->alternate_vertical_scan_flag)
        vop->flags |= V4L2_MPEG4_VOP_FLAG_ALTERNATE_VERTICAL_SCAN;
    for (unsigned i = 0; i < 3; i++) {
        vop->sprite_trajectory_du[i] = pp->sprite_trajectory_du[i];
        vop->sprite_trajectory_dv[i] = pp->sprite_trajectory_dv[i];
    }
}

/* VA's matrices are in zigzag order already; one not loaded is the default */
static void fill_quantisation(struct v4l2_ctrl_mpeg4_quantisation *q,
                              const VAIQMatrixBufferMPEG4 *iq)
{
    memcpy(q->intra_quantiser_matrix,
           iq && iq->load_intra_quant_mat ? iq->intra_quant_mat : mpeg4_default_intra,
           MPEG4_MATRIX_SIZE);
    memcpy(q->non_intra_quantiser_matrix,
           iq && iq->load_non_intra_quant_mat ? iq->non_intra_quant_mat : mpeg4_default_non_intra,
           MPEG4_MATRIX_SIZE);
}

static int submit_run(struct request_ctx *rq, struct v4l2_ext_control *controls,
                      struct v4l2_ctrl_mpeg4_slice *slice, const struct slice *s,
                      const struct run *run, unsigned next_macroblock, bool first, bool last)
{
    size_t from = run->first_bit / 8;
    struct annexb data = { 0 };
    if (run->end_byte <= from || next_macroblock <= run->macroblock)
        return -EINVAL;
    int ret = annexb_append_raw(&data, s->data + from, run->end_byte - from);
    *slice = (struct v4l2_ctrl_mpeg4_slice){
        .bit_size = data.size * 8,
        .data_bit_offset = run->first_bit % 8,
        .macroblock_number = run->macroblock,
        .num_macroblocks = next_macroblock - run->macroblock,
        .quant_scale = run->quant,
    };
    request_dump(rq, "macroblock_number", slice->macroblock_number);
    request_dump(rq, "quant_scale", slice->quant_scale);
    if (!ret)
        ret = request_queue(rq, controls, NUM_CONTROLS, &data, first, last);
    annexb_free(&data);
    return ret;
}

/* the whole VOP in one request, from the 64-bit word holding its first macroblock: an engine that
 * keeps no picture across requests, as VDPU2, reads its packet and GOB headers itself */
static int submit_vop(struct request_ctx *rq, struct v4l2_ext_control *controls,
                      struct v4l2_ctrl_mpeg4_slice *slice, const struct slice *s,
                      const struct run *first, unsigned macroblocks)
{
    size_t byte = first->first_bit / 8, back = byte % sizeof(uint64_t), from = byte - back;
    struct annexb data = { 0 };
    if (coded_size(s) <= byte)
        return -EINVAL;
    int ret = annexb_append_raw(&data, s->data + from, coded_size(s) - from);
    *slice = (struct v4l2_ctrl_mpeg4_slice){
        .bit_size = data.size * 8,
        .data_bit_offset = back * 8 + first->first_bit % 8,
        .num_macroblocks = macroblocks,
        .quant_scale = first->quant,
    };
    if (!ret)
        ret = request_queue(rq, controls, NUM_CONTROLS, &data, true, true);
    annexb_free(&data);
    return ret;
}

static int mpeg4_submit(struct request_ctx *rq, const struct picture *pic)
{
    const VAPictureParameterBufferMPEG4 *pp = pic->picture_param;
    const VASliceParameterBufferMPEG4 *sp = pic->num_slices ? pic->slices[0].param : NULL;
    struct v4l2_ctrl_mpeg4_vol vol;
    struct v4l2_ctrl_mpeg4_vop vop;
    struct v4l2_ctrl_mpeg4_quantisation quantisation;
    struct v4l2_ctrl_mpeg4_slice slice;
    static struct run runs[MAX_RUNS];
    int ret = 0;

    if (!pp || !sp || (!pp->vol_fields.bits.short_video_header && !pp->quant_precision))
        return -EINVAL;
    /* Cedrus predicts interlaced B-VOPs otherwise, and VA does not say whether any come */
    if (pp->vol_fields.bits.interlaced)
        return -ENOTSUP;
    const struct slice *s = &pic->slices[0];
    unsigned macroblocks = ((pp->vop_width + MB_SIZE - 1) / MB_SIZE) *
                           ((pp->vop_height + MB_SIZE - 1) / MB_SIZE);
    bool short_header = pp->vol_fields.bits.short_video_header;
    fill_vol(&vol, pp);
    fill_vop(rq, &vop, pp);
    fill_quantisation(&quantisation, pic->iq_matrix);
    runs[0] = (struct run){ .first_bit = sp->macroblock_offset, .quant = sp->quant_scale };
    unsigned count = short_header                               ? split_gobs(s, pp, macroblocks, runs)
                     : pp->vol_fields.bits.resync_marker_disable ? 1
                                                                 : split_packets(s, pp, macroblocks,
                                                                                 runs);
    runs[count - 1].end_byte = coded_size(s);
    request_dump(rq, "vop_coding_type", vop.vop_coding_type);
    request_dump(rq, "intra_dc_vlc_thr", vop.intra_dc_vlc_thr);
    if (vop.vop_coding_type != VOP_I)
        request_dump(rq, "vop_fcode_forward", vop.vop_fcode_forward);
    struct v4l2_ext_control controls[NUM_CONTROLS] = {
        { .id = V4L2_CID_STATELESS_MPEG4_VOL, .size = sizeof(vol), .ptr = &vol },
        { .id = V4L2_CID_STATELESS_MPEG4_VOP, .size = sizeof(vop), .ptr = &vop },
        { .id = V4L2_CID_STATELESS_MPEG4_QUANTISATION,
          .size = sizeof(quantisation),
          .ptr = &quantisation },
        { .id = V4L2_CID_STATELESS_MPEG4_SLICE, .size = sizeof(slice), .ptr = &slice },
    };
    /* the host's dump records Cedrus's requests */
    if (!rq->holds_capture && !rq->dump)
        return submit_vop(rq, controls, &slice, s, &runs[0], macroblocks);
    for (unsigned i = 0; i < count && !ret; i++) {
        unsigned next = i + 1 < count ? runs[i + 1].macroblock : macroblocks;
        ret = submit_run(rq, controls, &slice, s, &runs[i], next, i == 0, i + 1 == count);
    }
    return ret;
}

const struct request_codec request_mpeg4 = {
    .kind = CODEC_MPEG4,
    .pixelformat = V4L2_PIX_FMT_MPEG4_SLICE,
    .state_size = sizeof(struct mpeg4_state),
    .submit = mpeg4_submit,
};
