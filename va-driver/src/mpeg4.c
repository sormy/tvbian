/*
 * MPEG-4 Part 2 and H.263: VA hands over the picture from the byte holding its first macroblock
 * bit. The VOS, VO and VOL, or H.263's picture header, are rebuilt from VA's parameters, then
 * the VOP header, and the coded data shifted in behind it. VA carries no VOP timing: times are
 * made up whose spacing gives each B-VOP the TRB and TRD it came with.
 */
#include <errno.h>
#include <string.h>

#include "driver.h"

enum {
    START_VOS = 0xb0,
    START_VO = 0xb5,
    START_VIDEO_OBJECT = 0x00,
    START_VOL = 0x20,
    START_VOP = 0xb6,
    SEQUENCE_END = 0xb1,
    START_CODE_BYTES = 3,
    PROFILE_ASP_L5 = 0xf5,
    VISUAL_OBJECT_VIDEO = 1,
    OBJECT_TYPE_ASP = 17,
    VERSION_1 = 1,
    VERSION_2 = 2,
    LAYER_PRIORITY = 1,
    ASPECT_SQUARE = 1,
    CHROMA_420 = 1,
    SHAPE_RECTANGULAR = 0,
    DEFAULT_QUANT_PRECISION = 5,
    BITS_PER_PIXEL = 8,
    VOP_B = 2,
    VOP_S = 3,
    SIZE_BITS = 13,
    TIME_RESOLUTION_BITS = 16,
    H263_START_BITS = 22,
    H263_START = 0x20,
    H263_TR_BITS = 8,
    H263_TR_MODULO = 256,
    H263_QUANT_BITS = 5,
};

/* H.263's source formats, by index; anything else needs H.263+'s PLUSPTYPE */
static const struct {
    unsigned width;
    unsigned height;
} h263_sizes[] = {
    { 0, 0 }, { 128, 96 }, { 176, 144 }, { 352, 288 }, { 704, 576 }, { 1408, 1152 },
};

struct mpeg4_state {
    struct bit_writer sent_vol;
    /* the made-up clock, in VOL ticks: the last I/P-VOP's time */
    unsigned anchor_time;
    unsigned pictures;
};

static void start_code(struct bit_writer *bw, unsigned code)
{
    bw_bits(bw, 24, 1);
    bw_bits(bw, 8, code);
}

/* next_start_code(): a 0, then 1s to the byte */
static void stuffing(struct bit_writer *bw)
{
    bw_flag(bw, 0);
    while (bw->bits % 8)
        bw_flag(bw, 1);
}

static unsigned time_increment_bits(unsigned resolution)
{
    unsigned bits = 1;
    while (resolution > 1u << bits)
        bits++;
    return resolution > 1 ? bits : 1;
}

const uint8_t mpeg4_default_intra[MPEG4_MATRIX_SIZE] = {
    8, 17, 17, 20, 18, 18, 19, 19, 21, 21, 22, 22, 22, 21, 21, 23, 23, 23, 23, 23, 23, 25, 24,
    24, 24, 24, 25, 25, 27, 27, 26, 26, 26, 26, 26, 27, 28, 28, 28, 28, 28, 28, 28, 30, 30, 30,
    30, 30, 30, 32, 32, 32, 32, 32, 35, 35, 35, 35, 38, 38, 38, 41, 41, 45,
};
const uint8_t mpeg4_default_non_intra[MPEG4_MATRIX_SIZE] = {
    16, 17, 17, 18, 18, 18, 19, 19, 19, 19, 20, 20, 20, 20, 20, 21, 21, 21, 21, 21, 21, 22, 22,
    22, 22, 22, 22, 22, 23, 23, 23, 23, 23, 23, 23, 23, 24, 24, 24, 25, 24, 24, 24, 25, 26, 26,
    26, 26, 25, 27, 27, 27, 27, 27, 28, 28, 28, 28, 30, 30, 30, 31, 31, 33,
};

/* loaded only where it is not the default: the same stream, and MPP decodes a loaded default
 * otherwise */
static void write_matrix(struct bit_writer *bw, bool load, const uint8_t *zigzag,
                         const uint8_t *standard)
{
    load = load && memcmp(zigzag, standard, MPEG4_MATRIX_SIZE);
    bw_flag(bw, load);
    for (unsigned i = 0; load && i < MPEG4_MATRIX_SIZE; i++)
        bw_bits(bw, 8, zigzag[i]);
}

static void write_vol(struct bit_writer *bw, const VAPictureParameterBufferMPEG4 *pp,
                      const VAIQMatrixBufferMPEG4 *iq)
{
    bool quarter_sample = pp->vol_fields.bits.quarter_sample;
    unsigned version = quarter_sample ? VERSION_2 : VERSION_1;
    bool quant_type = pp->vol_fields.bits.quant_type;

    bw_init(bw);
    start_code(bw, START_VOS);
    bw_bits(bw, 8, PROFILE_ASP_L5);
    start_code(bw, START_VO);
    bw_flag(bw, 0);
    bw_bits(bw, 4, VISUAL_OBJECT_VIDEO);
    bw_flag(bw, 0);
    stuffing(bw);
    start_code(bw, START_VIDEO_OBJECT);
    start_code(bw, START_VOL);
    bw_flag(bw, 0);
    bw_bits(bw, 8, OBJECT_TYPE_ASP);
    bw_flag(bw, 1);
    bw_bits(bw, 4, version);
    bw_bits(bw, 3, LAYER_PRIORITY);
    bw_bits(bw, 4, ASPECT_SQUARE);
    bw_flag(bw, 1);
    bw_bits(bw, 2, CHROMA_420);
    /* not low delay: VA does not say whether B-VOPs come, and a decoder told there are none
     * may predict them otherwise */
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_bits(bw, 2, SHAPE_RECTANGULAR);
    bw_flag(bw, 1);
    bw_bits(bw, TIME_RESOLUTION_BITS, pp->vop_time_increment_resolution);
    bw_flag(bw, 1);
    bw_flag(bw, 0);
    bw_flag(bw, 1);
    bw_bits(bw, SIZE_BITS, pp->vop_width);
    bw_flag(bw, 1);
    bw_bits(bw, SIZE_BITS, pp->vop_height);
    bw_flag(bw, 1);
    bw_flag(bw, pp->vol_fields.bits.interlaced);
    bw_flag(bw, pp->vol_fields.bits.obmc_disable);
    bw_bits(bw, version == VERSION_1 ? 1 : 2, 0);
    bw_flag(bw, pp->quant_precision != DEFAULT_QUANT_PRECISION);
    if (pp->quant_precision != DEFAULT_QUANT_PRECISION) {
        bw_bits(bw, 4, pp->quant_precision);
        bw_bits(bw, 4, BITS_PER_PIXEL);
    }
    bw_flag(bw, quant_type);
    if (quant_type) {
        write_matrix(bw, iq && iq->load_intra_quant_mat, iq ? iq->intra_quant_mat : NULL,
                     mpeg4_default_intra);
        write_matrix(bw, iq && iq->load_non_intra_quant_mat, iq ? iq->non_intra_quant_mat : NULL,
                     mpeg4_default_non_intra);
    }
    if (version != VERSION_1)
        bw_flag(bw, quarter_sample);
    bw_flag(bw, 1);
    bw_flag(bw, pp->vol_fields.bits.resync_marker_disable);
    bw_flag(bw, pp->vol_fields.bits.data_partitioned);
    if (pp->vol_fields.bits.data_partitioned)
        bw_flag(bw, pp->vol_fields.bits.reversible_vlc);
    if (version != VERSION_1) {
        bw_flag(bw, 0);
        bw_flag(bw, 0);
    }
    bw_flag(bw, 0);
    stuffing(bw);
}

/*
 * Times each VOP's TRB and TRD agree with: an I/P-VOP comes TRD after the last, a B-VOP TRB after
 * the one before that. Its modulo_time_base counts seconds from that same reference.
 */
static int write_vop(struct bit_writer *bw, struct mpeg4_state *st,
                     const VAPictureParameterBufferMPEG4 *pp, unsigned quant)
{
    unsigned type = pp->vop_fields.bits.vop_coding_type;
    unsigned resolution = pp->vop_time_increment_resolution ? pp->vop_time_increment_resolution : 1;
    bool b_vop = type == VOP_B;
    int trb = pp->TRB, trd = pp->TRD;
    if (trb < 0 || trd < 0 || (b_vop && ((unsigned)trd > st->anchor_time || trb > trd)))
        return -EINVAL;
    unsigned reference = b_vop ? st->anchor_time - (unsigned)trd : st->anchor_time;
    unsigned time = reference + (unsigned)(b_vop ? trb : trd);
    if (!b_vop)
        st->anchor_time = time;

    bw_init(bw);
    start_code(bw, START_VOP);
    bw_bits(bw, 2, type);
    for (unsigned s = reference / resolution; s < time / resolution; s++)
        bw_flag(bw, 1);
    bw_flag(bw, 0);
    bw_flag(bw, 1);
    bw_bits(bw, time_increment_bits(resolution), time % resolution);
    bw_flag(bw, 1);
    bw_flag(bw, 1);
    if (type == 1)
        bw_flag(bw, pp->vop_fields.bits.vop_rounding_type);
    bw_bits(bw, 3, pp->vop_fields.bits.intra_dc_vlc_thr);
    if (pp->vol_fields.bits.interlaced) {
        bw_flag(bw, pp->vop_fields.bits.top_field_first);
        bw_flag(bw, pp->vop_fields.bits.alternate_vertical_scan_flag);
    }
    bw_bits(bw, pp->quant_precision, quant);
    if (type)
        bw_bits(bw, 3, pp->vop_fcode_forward);
    if (b_vop)
        bw_bits(bw, 3, pp->vop_fcode_backward);
    return 0;
}

static int h263_source_format(const VAPictureParameterBufferMPEG4 *pp)
{
    for (unsigned i = 1; i < sizeof(h263_sizes) / sizeof(h263_sizes[0]); i++)
        if (h263_sizes[i].width == pp->vop_width && h263_sizes[i].height == pp->vop_height)
            return (int)i;
    return -ENOTSUP;
}

/* the short header: TR counted, as VA has none */
static void write_h263_picture(struct bit_writer *bw, unsigned temporal_reference,
                               unsigned source_format, const VAPictureParameterBufferMPEG4 *pp,
                               unsigned quant)
{
    bw_init(bw);
    bw_bits(bw, H263_START_BITS, H263_START);
    bw_bits(bw, H263_TR_BITS, temporal_reference % H263_TR_MODULO);
    bw_flag(bw, 1);
    bw_flag(bw, 0);
    bw_bits(bw, 3, 0);
    bw_bits(bw, 3, source_format);
    bw_flag(bw, pp->vop_fields.bits.vop_coding_type != 0);
    bw_bits(bw, 4, 0);
    bw_bits(bw, H263_QUANT_BITS, quant);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
}

/* where the VOP ends: the packet may go on with another unit, an end of sequence */
static size_t next_start_code(const uint8_t *data, size_t size)
{
    for (size_t i = 0; i + 3 <= size; i++)
        if (!data[i] && !data[i + 1] && data[i + 2] == 1)
            return i;
    return size;
}

/* the data's own trailing stuffing, a 0 and then 1s, left out: the header may move the end */
static size_t coded_end(const uint8_t *data, size_t size)
{
    while (size && !data[size - 1])
        size--;
    if (!size)
        return 0;
    unsigned ones = 0;
    while (ones < 8 && (data[size - 1] >> ones) & 1)
        ones++;
    return ones < 8 ? size * 8 - ones - 1 : size * 8;
}

static int mpeg4_build_packet(void *state, const struct picture *pic, struct annexb *out,
                              struct packet_info *info)
{
    struct mpeg4_state *st = state;
    const VAPictureParameterBufferMPEG4 *pp = pic->picture_param;
    const VASliceParameterBufferMPEG4 *sp = pic->num_slices ? pic->slices[0].param : NULL;
    struct bit_writer bw;
    int ret;

    if (!pp || !sp)
        return -EINVAL;
    info->predicted = pp->vop_fields.bits.vop_coding_type != 0;
    info->hidden = false;
    const struct slice *s = &pic->slices[0];
    /* FFmpeg reads H.263's VOL fields from a context that has none: only these count */
    if (pp->vol_fields.bits.short_video_header) {
        int format = h263_source_format(pp);
        if (format < 0)
            return format;
        write_h263_picture(&bw, st->pictures++, format, pp, sp->quant_scale);
        size_t end = s->size * 8;
        return annexb_append_bits(out, &bw, s->data, sp->macroblock_offset, end,
                                  (8 - (bw.bits + end - sp->macroblock_offset) % 8) % 8, 0);
    }
    /* sprites and GMC need their trajectories coded back: not done */
    if (pp->vol_fields.bits.sprite_enable || pp->vop_fields.bits.vop_coding_type == VOP_S)
        return -ENOTSUP;
    write_vol(&bw, pp, pic->iq_matrix);
    if (pp->vop_fields.bits.vop_coding_type == 0 || bw.bits != st->sent_vol.bits ||
        memcmp(bw.data, st->sent_vol.data, bw_bytes(&bw))) {
        if ((ret = annexb_append_raw(out, bw.data, bw_bytes(&bw))))
            return ret;
        st->sent_vol = bw;
    }
    if ((ret = write_vop(&bw, st, pp, sp->quant_scale)))
        return ret;
    size_t tail = next_start_code(s->data, s->size);
    size_t end = coded_end(s->data, tail);
    if (end < sp->macroblock_offset)
        return -EINVAL;
    unsigned pad_bits = 8 - (bw.bits + end - sp->macroblock_offset) % 8;
    ret = annexb_append_bits(out, &bw, s->data, sp->macroblock_offset, end, pad_bits,
                             (1u << (pad_bits - 1)) - 1);
    /* an end of sequence goes on; a packed B-VOP behind it comes again as its own picture */
    bool sequence_end = s->size - tail > START_CODE_BYTES && s->data[tail + 3] == SEQUENCE_END;
    return ret || !sequence_end ? ret : annexb_append_raw(out, s->data + tail, s->size - tail);
}

static void mpeg4_restart(void *state)
{
    struct mpeg4_state *st = state;
    st->sent_vol.bits = 0;
}

const struct codec codec_mpeg4 = {
    .kind = CODEC_MPEG4,
    .state_size = sizeof(struct mpeg4_state),
    .build_packet = mpeg4_build_packet,
    .restart = mpeg4_restart,
};
