/*
 * VC-1 onto Cedrus's private controls (linux-sunxi 0064, 0065): one request a picture or field,
 * its data from the picture header on, as VA gives it, with later slices' start codes back
 * and the picture header a slice repeats left out.
 * VA's bitplanes, a nibble a macroblock, are unpacked into Cedrus's planes of a bit each. A
 * skipped picture goes to no request: it is its forward reference's picture.
 */
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include "request.h"
/* after request.h: it needs videodev2.h's types */
#include "vc1-ctrls.h"

enum {
    PTYPE_I = 0,
    PTYPE_P = 1,
    PTYPE_B = 2,
    PTYPE_BI = 3,
    PTYPE_SKIPPED = 4,
    FCM_FIELD = 2,
    START_SLICE = 0x0b,
    SLICE_ADDR_BITS = 9,
    MB_SIZE = 16,
    FIELD_MB_HEIGHT = 32,
    PQINDEX_UNIFORM_MAX = 8,
    PQINDEX_MAX = 31,
    NUM_CONTROLS = 2,
};

/* VA's MV mode to the bitstream's MVMODE, which Cedrus takes */
static const uint8_t bitstream_mvmode[] = {
    [VAMvMode1MvHalfPelBilinear] = 0,
    [VAMvMode1Mv] = 1,
    [VAMvMode1MvHalfPel] = 2,
    [VAMvModeMixedMv] = 3,
    [VAMvModeIntensityCompensation] = 4,
};

static uint8_t mvmode_of(unsigned va_mode)
{
    return va_mode < sizeof(bitstream_mvmode) ? bitstream_mvmode[va_mode] : 0;
}

/* PQINDEX to PQUANT with the implicit quantizer, SMPTE 421M table 36 */
static const uint8_t implicit_pquant[PQINDEX_MAX + 1] = {
    0,  1,  2,  3,  4,  5,  6,  7,  8,  6,  7,  8,  9,  10, 11, 12,
    13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 27, 29, 31,
};

/* a field picture's FPTYPE, each field's own type: I/I, I/P, P/I, P/P, B/B, B/BI, BI/B, BI/BI */
static const uint8_t field_ptypes[8][2] = {
    { PTYPE_I, PTYPE_I },   { PTYPE_I, PTYPE_P },  { PTYPE_P, PTYPE_I },  { PTYPE_P, PTYPE_P },
    { PTYPE_B, PTYPE_B },   { PTYPE_B, PTYPE_BI }, { PTYPE_BI, PTYPE_B }, { PTYPE_BI, PTYPE_BI },
};

struct vc1_request_state {
    struct v4l2_ctrl_vc1_bitplanes bitplanes;
};

static unsigned ptype_of(const VAPictureParameterBufferVC1 *pp)
{
    unsigned type = pp->picture_fields.bits.picture_type;
    if (pp->picture_fields.bits.frame_coding_mode != FCM_FIELD)
        return type;
    return field_ptypes[type & 7][!pp->picture_fields.bits.is_first_field];
}

/* Cedrus wants PQINDEX; VA gives PQUANT and whether it is uniform */
static unsigned pqindex_of(const VAPictureParameterBufferVC1 *pp)
{
    unsigned pq = pp->pic_quantizer_fields.bits.pic_quantizer_scale;
    bool uniform = pp->pic_quantizer_fields.bits.pic_quantizer_type;
    if (pp->pic_quantizer_fields.bits.quantizer)
        return pq;
    for (unsigned i = 1; i <= PQINDEX_MAX; i++)
        if (implicit_pquant[i] == pq && (i <= PQINDEX_UNIFORM_MAX) == uniform)
            return i;
    return pq;
}

/* each flag whose condition holds, ORed into target */
#define FLAGS(target, ...)                                                                         \
    do {                                                                                           \
        const struct {                                                                             \
            bool set;                                                                              \
            uint32_t flag;                                                                         \
        } pairs[] = { __VA_ARGS__ };                                                               \
        for (size_t i = 0; i < sizeof(pairs) / sizeof(pairs[0]); i++)                              \
            if (pairs[i].set)                                                                      \
                (target) |= pairs[i].flag;                                                         \
    } while (0)

static void fill_slice_params(const struct request_ctx *rq, struct v4l2_ctrl_vc1_slice_params *sp,
                              const VAPictureParameterBufferVC1 *pp, unsigned ptype)
{
    const typeof(pp->sequence_fields.bits) *seq = &pp->sequence_fields.bits;
    const typeof(pp->mv_fields.bits) *mv = &pp->mv_fields.bits;
    const typeof(pp->pic_quantizer_fields.bits) *quant = &pp->pic_quantizer_fields.bits;
    const typeof(pp->transform_fields.bits) *transform = &pp->transform_fields.bits;
    const typeof(pp->range_mapping_fields.bits) *range = &pp->range_mapping_fields.bits;
    bool interlaced_picture = pp->picture_fields.bits.frame_coding_mode != 0;

    if (ptype == PTYPE_P || ptype == PTYPE_B)
        sp->forward_ref_ts = request_timestamp(rq, pp->forward_reference_picture);
    if (ptype == PTYPE_B)
        sp->backward_ref_ts = request_timestamp(rq, pp->backward_reference_picture);
    sp->sequence = (struct v4l2_vc1_sequence){ .profile = seq->profile, .colordiff_format = 1 };
    FLAGS(sp->sequence.flags, { seq->pulldown, V4L2_VC1_SEQUENCE_FLAG_PULLDOWN },
          { seq->interlace, V4L2_VC1_SEQUENCE_FLAG_INTERLACE },
          { seq->tfcntrflag, V4L2_VC1_SEQUENCE_FLAG_TFCNTRFLAG },
          { seq->finterpflag, V4L2_VC1_SEQUENCE_FLAG_FINTERPFLAG },
          { seq->psf, V4L2_VC1_SEQUENCE_FLAG_PSF });
    sp->entrypoint_header = (struct v4l2_vc1_entrypoint_header){
        .dquant = quant->dquant,
        .quantizer = quant->quantizer,
        .coded_width = pp->coded_width,
        .coded_height = pp->coded_height,
        .range_mapy = range->luma,
        .range_mapuv = range->chroma,
    };
    FLAGS(sp->entrypoint_header.flags,
          { pp->entrypoint_fields.bits.broken_link, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_BROKEN_LINK },
          { pp->entrypoint_fields.bits.closed_entry, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_CLOSED_ENTRY },
          { pp->entrypoint_fields.bits.panscan_flag, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_PANSCAN },
          { pp->reference_fields.bits.reference_distance_flag,
            V4L2_VC1_ENTRYPOINT_HEADER_FLAG_REFDIST },
          { pp->entrypoint_fields.bits.loopfilter, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_LOOPFILTER },
          { pp->fast_uvmc_flag, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_FASTUVMC },
          { mv->extended_mv_flag, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_EXTENDED_MV },
          { transform->variable_sized_transform_flag, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_VSTRANSFORM },
          { seq->overlap, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_OVERLAP },
          { mv->extended_dmv_flag, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_EXTENDED_DMV },
          { range->luma_flag, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_RANGE_MAPY },
          { range->chroma_flag, V4L2_VC1_ENTRYPOINT_HEADER_FLAG_RANGE_MAPUV });
    sp->picture_layer = (struct v4l2_vc1_picture_layer){
        .ptype = ptype,
        .pqindex = pqindex_of(pp),
        .mvrange = mv->extended_mv_range,
        .respic = pp->picture_resolution_index,
        .transacfrm = transform->transform_ac_codingset_idx1,
        .transacfrm2 = transform->transform_ac_codingset_idx2,
        .bfraction = pp->b_picture_fraction,
        .fcm = pp->picture_fields.bits.frame_coding_mode,
        .mvmode = mvmode_of(mv->mv_mode),
        .mvmode2 = mvmode_of(mv->mv_mode2),
        .lumscale = pp->luma_scale,
        .lumshift = pp->luma_shift,
        .lumscale2 = pp->luma_scale2,
        .lumshift2 = pp->luma_shift2,
        .mvtab = interlaced_picture ? 0 : mv->mv_table,
        .cbptab = interlaced_picture ? 0 : pp->cbp_table,
        .intcompfield = pp->intensity_compensation_field,
        .dmvrange = mv->extended_dmv_range,
        .mbmodetab = pp->mb_mode_table,
        .twomvbptab = mv->two_mv_block_pattern_table,
        .fourmvbptab = mv->four_mv_block_pattern_table,
        .ttfrm = transform->frame_level_transform_type,
        .refdist = pp->reference_fields.bits.reference_distance,
        .condover = pp->conditional_overlap_flag,
        .imvtab = interlaced_picture ? mv->mv_table : 0,
        .icbptab = interlaced_picture ? pp->cbp_table : 0,
    };
    FLAGS(sp->picture_layer.flags,
          { pp->range_reduction_frame, V4L2_VC1_PICTURE_LAYER_FLAG_RANGEREDFRM },
          { quant->half_qp, V4L2_VC1_PICTURE_LAYER_FLAG_HALFQP },
          { quant->pic_quantizer_type, V4L2_VC1_PICTURE_LAYER_FLAG_PQUANTIZER },
          { transform->intra_transform_dc_table, V4L2_VC1_PICTURE_LAYER_FLAG_TRANSDCTAB },
          { pp->picture_fields.bits.top_field_first, V4L2_VC1_PICTURE_LAYER_FLAG_TFF },
          { pp->rounding_control, V4L2_VC1_PICTURE_LAYER_FLAG_RNDCTRL },
          { transform->mb_level_transform_type_flag, V4L2_VC1_PICTURE_LAYER_FLAG_TTMBF },
          { mv->four_mv_switch, V4L2_VC1_PICTURE_LAYER_FLAG_4MVSWITCH },
          { pp->picture_fields.bits.intensity_compensation, V4L2_VC1_PICTURE_LAYER_FLAG_INTCOMP },
          { pp->reference_fields.bits.num_reference_pictures, V4L2_VC1_PICTURE_LAYER_FLAG_NUMREF },
          { pp->reference_fields.bits.reference_field_pic_indicator,
            V4L2_VC1_PICTURE_LAYER_FLAG_REFFIELD },
          { !pp->picture_fields.bits.is_first_field, V4L2_VC1_PICTURE_LAYER_FLAG_SECOND_FIELD });
    sp->vopdquant = (struct v4l2_vc1_vopdquant){
        .altpquant = quant->alt_pic_quantizer,
        .dqprofile = quant->dq_profile,
        .dqsbedge = quant->dq_sb_edge,
        .dqdbedge = quant->dq_db_edge,
    };
    FLAGS(sp->vopdquant.flags, { quant->dq_frame, V4L2_VC1_VOPDQUANT_FLAG_DQUANTFRM },
          { quant->dq_binary_level, V4L2_VC1_VOPDQUANT_FLAG_DQBILEVEL });
    sp->metadata = (struct v4l2_vc1_metadata){ .maxbframes = seq->max_b_frames };
    FLAGS(sp->metadata.flags, { seq->multires, V4L2_VC1_METADATA_FLAG_MULTIRES },
          { seq->syncmarker, V4L2_VC1_METADATA_FLAG_SYNCMARKER },
          { seq->rangered, V4L2_VC1_METADATA_FLAG_RANGERED });
    /* VA's raw-coding and bitplane flags are in the controls' bit order */
    sp->raw_coding_flags = pp->raw_coding.value & 0x7f;
}

/* VA's nibbles: the first macroblock of a pair high; bits 0-2 the planes the picture type has */
static int unpack_bitplanes(struct v4l2_ctrl_vc1_bitplanes *planes, const struct picture *pic,
                            const VAPictureParameterBufferVC1 *pp, unsigned ptype)
{
    uint8_t *by_bit[3];
    if (ptype == PTYPE_P)
        by_bit[0] = planes->directmb, by_bit[1] = planes->skipmb, by_bit[2] = planes->mvtypemb;
    else if (ptype == PTYPE_B)
        by_bit[0] = planes->directmb, by_bit[1] = planes->skipmb, by_bit[2] = planes->forwardmb;
    else
        by_bit[0] = planes->fieldtx, by_bit[1] = planes->acpred, by_bit[2] = planes->overflags;
    memset(planes, 0, sizeof(*planes));
    planes->bitplane_flags = pp->bitplane_present.value & 0x7f;
    if (!planes->bitplane_flags)
        return 0;
    unsigned mb_height = pp->picture_fields.bits.frame_coding_mode == FCM_FIELD
                             ? (pp->coded_height + FIELD_MB_HEIGHT - 1) / FIELD_MB_HEIGHT
                             : (pp->coded_height + MB_SIZE - 1) / MB_SIZE;
    size_t count = (size_t)(pp->coded_width + MB_SIZE - 1) / MB_SIZE * mb_height;
    if (!pic->bitplane || pic->bitplane_size * 2 < count || count > sizeof(planes->skipmb) * 8)
        return -EINVAL;
    for (size_t n = 0; n < count; n++) {
        unsigned nibble = n % 2 ? pic->bitplane[n / 2] & 0xf : pic->bitplane[n / 2] >> 4;
        for (unsigned bit = 0; bit < 3; bit++)
            by_bit[bit][n / 8] |= ((nibble >> bit) & 1) << (n % 8);
    }
    return 0;
}

/* a later slice's data starts at its address, PIC_HEADER_FLAG after it */
static bool repeats_header(const struct slice *s)
{
    return s->size > 1 && s->data[1] & 1u << (15 - SLICE_ADDR_BITS);
}

/* Cedrus reads a slice's address and flag, not the header the flag says follows: the slice goes
 * with the flag cleared and its macroblocks where the header was */
static int append_bare_slice(struct annexb *out, const struct slice *s)
{
    const VASliceParameterBufferVC1 *sp = s->param;
    uint8_t *rbsp = malloc(s->size);
    struct annexb bare = { 0 };
    struct bit_writer head;
    int ret = -ENOMEM;
    if (!rbsp)
        return ret;
    size_t bits = unescape(s->data, s->size, rbsp) * 8;
    bw_init(&head);
    bw_copy_bits(&head, rbsp, 0, SLICE_ADDR_BITS);
    bw_flag(&head, false);
    if (sp->macroblock_offset > bits) {
        ret = -EINVAL;
    } else {
        unsigned pad = (8 - (head.bits + bits - sp->macroblock_offset) % 8) % 8;
        ret = annexb_append_bits(&bare, &head, rbsp, sp->macroblock_offset, bits, pad, 0);
    }
    free(rbsp);
    if (!ret)
        ret = annexb_append_escaped(out, bare.data, bare.size);
    annexb_free(&bare);
    return ret;
}

static int vc1_submit(struct request_ctx *rq, const struct picture *pic)
{
    struct vc1_request_state *st = rq->codec_state;
    const VAPictureParameterBufferVC1 *pp = pic->picture_param;
    const VASliceParameterBufferVC1 *first = pic->num_slices ? pic->slices[0].param : NULL;
    struct v4l2_ctrl_vc1_slice_params slice_params = { 0 };
    struct annexb data = { 0 };
    int ret = 0;

    if (!pp || !first)
        return -EINVAL;
    unsigned ptype = ptype_of(pp);
    fill_slice_params(rq, &slice_params, pp, ptype);
    if ((ret = unpack_bitplanes(&st->bitplanes, pic, pp, ptype)))
        return ret;
    for (unsigned i = 0; i < pic->num_slices && !ret; i++) {
        const uint8_t slice_start[] = { 0, 0, 1, START_SLICE };
        const struct slice *s = &pic->slices[i];
        if (i)
            ret = annexb_append_raw(&data, slice_start, sizeof(slice_start));
        if (!ret)
            ret = i && repeats_header(s) ? append_bare_slice(&data, s)
                                         : annexb_append_raw(&data, s->data, s->size);
    }
    slice_params.bit_size = data.size * 8;
    slice_params.data_bit_offset = first->macroblock_offset;
    request_dump(rq, "PTYPE", ptype);
    if (ptype != PTYPE_SKIPPED)
        request_dump(rq, "PQINDEX", slice_params.picture_layer.pqindex);
    request_dump(rq, "DQUANT", slice_params.entrypoint_header.dquant);
    request_dump(rq, "QUANTIZER", slice_params.entrypoint_header.quantizer);
    request_dump(rq, "LOOPFILTER", pp->entrypoint_fields.bits.loopfilter);
    request_dump(rq, "OVERLAP", pp->sequence_fields.bits.overlap);
    request_dump(rq, "VSTRANSFORM", pp->transform_fields.bits.variable_sized_transform_flag);
    request_dump(rq, "data_bit_offset", slice_params.data_bit_offset);
    struct v4l2_ext_control controls[NUM_CONTROLS] = {
        { .id = V4L2_CID_STATELESS_VC1_SLICE_PARAMS,
          .size = sizeof(slice_params),
          .ptr = &slice_params },
        { .id = V4L2_CID_STATELESS_VC1_BITPLANES,
          .size = sizeof(st->bitplanes),
          .ptr = &st->bitplanes },
    };
    if (!ret)
        ret = ptype == PTYPE_SKIPPED
                  ? request_repeat_reference(rq, pp->forward_reference_picture)
                  : request_queue(rq, controls, NUM_CONTROLS, &data, true, true);
    annexb_free(&data);
    return ret;
}

const struct request_codec request_vc1 = {
    .kind = CODEC_VC1,
    .pixelformat = V4L2_PIX_FMT_VC1_SLICE,
    .state_size = sizeof(struct vc1_request_state),
    .submit = vc1_submit,
};
