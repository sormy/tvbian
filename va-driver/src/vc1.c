/*
 * VC-1: VA keeps each picture's own layer, from its picture header on, but drops the sequence
 * layer and the start codes. Advanced profile gets a sequence and an entry-point header rebuilt
 * from VA's parameters and its start codes back; a field picture waits for its second field, so
 * the frame goes out whole. Simple and Main profile frames go out behind STRUCT_C, the sequence
 * layer an engine takes out of band (SMPTE 421M Annex J).
 */
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include "driver.h"

enum {
    START_SLICE = 0x0b,
    START_FIELD = 0x0c,
    START_FRAME = 0x0d,
    START_ENTRY_POINT = 0x0e,
    START_SEQUENCE = 0x0f,
    PROFILE_ADVANCED = 3,
    LEVEL_4 = 4,
    CHROMA_420 = 1,
    FIELD_INTERLACE = 2,
    SIZE_BITS = 12,
    PICTURE_I = 0,
    FPTYPE_I_FIRST_LAST = 1,
    STRUCT_C_PROFILE_SHIFT = 2,
};

struct vc1_state {
    struct bit_writer sent_sequence;
    /* a first field, held until its second */
    struct annexb first_field;
};

static void write_sequence(struct bit_writer *bw, const VAPictureParameterBufferVC1 *pp)
{
    bw_init(bw);
    bw_bits(bw, 2, PROFILE_ADVANCED);
    bw_bits(bw, 3, LEVEL_4);
    bw_bits(bw, 2, CHROMA_420);
    bw_bits(bw, 3, 0);
    bw_bits(bw, 5, 0);
    /* POSTPROCFLAG: VA gives POSTPROC's value alone, so a stream sending 0 throughout is read
     * as having none */
    bw_flag(bw, pp->post_processing != 0);
    bw_bits(bw, SIZE_BITS, pp->coded_width / 2 - 1);
    bw_bits(bw, SIZE_BITS, pp->coded_height / 2 - 1);
    bw_flag(bw, pp->sequence_fields.bits.pulldown);
    bw_flag(bw, pp->sequence_fields.bits.interlace);
    bw_flag(bw, pp->sequence_fields.bits.tfcntrflag);
    bw_flag(bw, pp->sequence_fields.bits.finterpflag);
    bw_flag(bw, 1);
    bw_flag(bw, pp->sequence_fields.bits.psf);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_trailing(bw);
}

static void write_entry_point(struct bit_writer *bw, const VAPictureParameterBufferVC1 *pp)
{
    bool extended_mv = pp->mv_fields.bits.extended_mv_flag;
    bw_init(bw);
    bw_flag(bw, pp->entrypoint_fields.bits.broken_link);
    bw_flag(bw, pp->entrypoint_fields.bits.closed_entry);
    bw_flag(bw, pp->entrypoint_fields.bits.panscan_flag);
    bw_flag(bw, pp->reference_fields.bits.reference_distance_flag);
    bw_flag(bw, pp->entrypoint_fields.bits.loopfilter);
    bw_flag(bw, pp->fast_uvmc_flag);
    bw_flag(bw, extended_mv);
    bw_bits(bw, 2, pp->pic_quantizer_fields.bits.dquant);
    bw_flag(bw, pp->transform_fields.bits.variable_sized_transform_flag);
    bw_flag(bw, pp->sequence_fields.bits.overlap);
    bw_bits(bw, 2, pp->pic_quantizer_fields.bits.quantizer);
    bw_flag(bw, 0);
    if (extended_mv)
        bw_flag(bw, pp->mv_fields.bits.extended_dmv_flag);
    bw_flag(bw, pp->range_mapping_fields.bits.luma_flag);
    if (pp->range_mapping_fields.bits.luma_flag)
        bw_bits(bw, 3, pp->range_mapping_fields.bits.luma);
    bw_flag(bw, pp->range_mapping_fields.bits.chroma_flag);
    if (pp->range_mapping_fields.bits.chroma_flag)
        bw_bits(bw, 3, pp->range_mapping_fields.bits.chroma);
    bw_trailing(bw);
}

/* Annex J's STRUCT_C, its reserved bits as a current encoder sets them */
static void write_struct_c(struct bit_writer *bw, const VAPictureParameterBufferVC1 *pp)
{
    bw_init(bw);
    bw_bits(bw, 4, pp->sequence_fields.bits.profile << STRUCT_C_PROFILE_SHIFT);
    bw_bits(bw, 3, 0);
    bw_bits(bw, 5, 0);
    bw_flag(bw, pp->entrypoint_fields.bits.loopfilter);
    bw_flag(bw, 0);
    bw_flag(bw, pp->sequence_fields.bits.multires);
    bw_flag(bw, 1);
    bw_flag(bw, pp->fast_uvmc_flag);
    bw_flag(bw, pp->mv_fields.bits.extended_mv_flag);
    bw_bits(bw, 2, pp->pic_quantizer_fields.bits.dquant);
    bw_flag(bw, pp->transform_fields.bits.variable_sized_transform_flag);
    bw_flag(bw, 0);
    bw_flag(bw, pp->sequence_fields.bits.overlap);
    bw_flag(bw, pp->sequence_fields.bits.syncmarker);
    bw_flag(bw, pp->sequence_fields.bits.rangered);
    bw_bits(bw, 3, pp->sequence_fields.bits.max_b_frames);
    bw_bits(bw, 2, pp->pic_quantizer_fields.bits.quantizer);
    bw_flag(bw, pp->sequence_fields.bits.finterpflag);
    bw_flag(bw, 1);
}

static int append_unit(struct annexb *out, unsigned code, const uint8_t *data, size_t size)
{
    const uint8_t start[] = { 0, 0, 1, (uint8_t)code };
    int ret = annexb_append_raw(out, start, sizeof(start));
    return ret ? ret : annexb_append_raw(out, data, size);
}

static int append_header(struct annexb *out, unsigned code, const struct bit_writer *bw)
{
    const uint8_t suffix = (uint8_t)code;
    return annexb_append_rbsp(out, &suffix, 1, bw);
}

static int build_advanced(struct vc1_state *st, const struct picture *pic, struct annexb *out)
{
    const VAPictureParameterBufferVC1 *pp = pic->picture_param;
    bool field = pp->picture_fields.bits.frame_coding_mode == FIELD_INTERLACE;
    bool first_field = pp->picture_fields.bits.is_first_field;
    struct annexb *dst = field && first_field ? &st->first_field : out;
    struct bit_writer bw;
    int ret;

    if (field && !first_field && (ret = annexb_append_raw(out, st->first_field.data,
                                                          st->first_field.size)))
        return ret;
    st->first_field.size = 0;
    if (first_field) {
        write_sequence(&bw, pp);
        bool changed = bw.bits != st->sent_sequence.bits ||
                       memcmp(bw.data, st->sent_sequence.data, bw_bytes(&bw));
        /* FPTYPE 0 and 1 begin with an I field */
        unsigned type = pp->picture_fields.bits.picture_type;
        bool intra = field ? type <= FPTYPE_I_FIRST_LAST : type == PICTURE_I;
        if (intra || changed) {
            if ((ret = append_header(dst, START_SEQUENCE, &bw)))
                return ret;
            st->sent_sequence = bw;
            write_entry_point(&bw, pp);
            if ((ret = append_header(dst, START_ENTRY_POINT, &bw)))
                return ret;
        }
    }
    for (unsigned i = 0; i < pic->num_slices; i++) {
        unsigned code = i ? START_SLICE : first_field ? START_FRAME : START_FIELD;
        if ((ret = append_unit(dst, code, pic->slices[i].data, pic->slices[i].size)))
            return ret;
    }
    return 0;
}

static int vc1_build_packet(void *state, const struct picture *pic, struct annexb *out,
                            struct packet_info *info)
{
    struct vc1_state *st = state;
    const VAPictureParameterBufferVC1 *pp = pic->picture_param;
    struct bit_writer bw;
    int ret;

    if (!pp || !pic->num_slices)
        return -EINVAL;
    info->hidden = false;
    bool field = pp->picture_fields.bits.frame_coding_mode == FIELD_INTERLACE;
    unsigned type = pp->picture_fields.bits.picture_type;
    info->predicted = field ? type > FPTYPE_I_FIRST_LAST : type != PICTURE_I;
    if (pp->sequence_fields.bits.profile == PROFILE_ADVANCED)
        return build_advanced(st, pic, out);
    write_struct_c(&bw, pp);
    if ((ret = annexb_append_raw(out, bw.data, bw_bytes(&bw))))
        return ret;
    for (unsigned i = 0; i < pic->num_slices; i++)
        if ((ret = annexb_append_raw(out, pic->slices[i].data, pic->slices[i].size)))
            return ret;
    return 0;
}

static void vc1_free(void *state)
{
    struct vc1_state *st = state;
    annexb_free(&st->first_field);
}

static void vc1_restart(void *state)
{
    struct vc1_state *st = state;
    st->sent_sequence.bits = 0;
}

const struct codec codec_vc1 = {
    .kind = CODEC_VC1,
    .state_size = sizeof(struct vc1_state),
    .build_packet = vc1_build_packet,
    .free_state = vc1_free,
    .restart = vc1_restart,
};
