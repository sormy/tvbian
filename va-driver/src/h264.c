/* H.264: the SPS and PPS rebuilt from VA's picture parameters, ahead of the slices as they came. */
#include <errno.h>
#include <string.h>

#include "driver.h"

enum {
    NAL_SLICE = 1,
    NAL_IDR_SLICE = 5,
    NAL_SPS = 7,
    NAL_PPS = 8,
    NAL_TYPE_MASK = 0x1f,
    NAL_REF_IDC_HIGHEST = 3 << 5,
};

enum { SLICE_P = 0, SLICE_B = 1, SLICE_SP = 3, SLICE_TYPES = 5 };

enum {
    PROFILE_HIGH = 100,
    PROFILE_HIGH10 = 110,
    /* the slice syntax ignores the level: 5.1 is what decoders expect to read */
    LEVEL_5_1 = 51,
    CHROMA_444 = 3,
    POC_TYPE_LSB = 0,
    POC_TYPE_DELTA = 1,
    FLAT_SCALE = 16,
    SCALING_LIST_START = 8,
    MAX_MV_LENGTH_LOG2 = 16,
    MAX_PPS = 256,
    QP_BD_OFFSET_PER_BIT = 6,
};

static const uint8_t zigzag_4x4[16] = { 0, 1, 4, 8, 5, 2, 3, 6, 9, 12, 13, 10, 7, 11, 14, 15 };

static const uint8_t zigzag_8x8[64] = {
    0,  1,  8,  16, 9,  2,  3,  10, 17, 24, 32, 25, 18, 11, 4,  5,  12, 19, 26, 33, 40, 48,
    41, 34, 27, 20, 13, 6,  7,  14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23,
    30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
};

/* What VA leaves out, learned from the slices, and what was last sent. */
struct h264_state {
    uint8_t num_ref_idx_l0_default[MAX_PPS];
    uint8_t num_ref_idx_l1_default[MAX_PPS];
    struct bit_writer sent_sps;
    struct bit_writer sent_pps;
    int sent_pps_id;
};

struct slice_header {
    unsigned nal_unit_type;
    unsigned slice_type;
    unsigned pps_id;
    bool overrides_num_ref_idx;
};

static bool is_inter(unsigned slice_type)
{
    return slice_type == SLICE_P || slice_type == SLICE_B || slice_type == SLICE_SP;
}

/* 7.3.3, as far as num_ref_idx_active_override_flag */
static bool parse_slice_header(const VAPictureParameterBufferH264 *pp, const struct slice *s,
                               struct slice_header *sh)
{
    struct bit_reader br;
    bool field_pic = false;

    if (s->size < 2)
        return false;
    sh->nal_unit_type = s->data[0] & NAL_TYPE_MASK;
    if (sh->nal_unit_type != NAL_SLICE && sh->nal_unit_type != NAL_IDR_SLICE)
        return false;
    br_init(&br, s->data + 1, s->size - 1);
    br_ue(&br);
    sh->slice_type = br_ue(&br) % SLICE_TYPES;
    sh->pps_id = br_ue(&br);
    if (pp->seq_fields.bits.residual_colour_transform_flag)
        br_bits(&br, 2);
    br_bits(&br, pp->seq_fields.bits.log2_max_frame_num_minus4 + 4);
    if (!pp->seq_fields.bits.frame_mbs_only_flag) {
        field_pic = br_bits(&br, 1);
        if (field_pic)
            br_bits(&br, 1);
    }
    if (sh->nal_unit_type == NAL_IDR_SLICE)
        br_ue(&br);
    bool bottom_poc_present = pp->pic_fields.bits.pic_order_present_flag && !field_pic;
    if (pp->seq_fields.bits.pic_order_cnt_type == POC_TYPE_LSB) {
        br_bits(&br, pp->seq_fields.bits.log2_max_pic_order_cnt_lsb_minus4 + 4);
        if (bottom_poc_present)
            br_se(&br);
    }
    if (pp->pic_fields.bits.redundant_pic_cnt_present_flag)
        br_ue(&br);
    if (sh->slice_type == SLICE_B)
        br_bits(&br, 1);
    sh->overrides_num_ref_idx = is_inter(sh->slice_type) && br_bits(&br, 1);
    return !br.overrun && sh->pps_id < MAX_PPS;
}

static void write_sps(struct bit_writer *bw, const VAPictureParameterBufferH264 *pp)
{
    unsigned frame_mbs_only = pp->seq_fields.bits.frame_mbs_only_flag;
    unsigned height_in_map_units = (pp->picture_height_in_mbs_minus1 + 1) / (2 - frame_mbs_only);

    bw_init(bw);
    bw_bits(bw, 8, pp->bit_depth_luma_minus8 ? PROFILE_HIGH10 : PROFILE_HIGH);
    bw_bits(bw, 8, 0);
    bw_bits(bw, 8, LEVEL_5_1);
    bw_ue(bw, 0);
    bw_ue(bw, pp->seq_fields.bits.chroma_format_idc);
    if (pp->seq_fields.bits.chroma_format_idc == CHROMA_444)
        bw_flag(bw, pp->seq_fields.bits.residual_colour_transform_flag);
    bw_ue(bw, pp->bit_depth_luma_minus8);
    bw_ue(bw, pp->bit_depth_chroma_minus8);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_ue(bw, pp->seq_fields.bits.log2_max_frame_num_minus4);
    bw_ue(bw, pp->seq_fields.bits.pic_order_cnt_type);
    if (pp->seq_fields.bits.pic_order_cnt_type == POC_TYPE_LSB)
        bw_ue(bw, pp->seq_fields.bits.log2_max_pic_order_cnt_lsb_minus4);
    bw_ue(bw, pp->num_ref_frames);
    bw_flag(bw, pp->seq_fields.bits.gaps_in_frame_num_value_allowed_flag);
    bw_ue(bw, pp->picture_width_in_mbs_minus1);
    bw_ue(bw, height_in_map_units - 1);
    bw_flag(bw, frame_mbs_only);
    if (!frame_mbs_only)
        bw_flag(bw, pp->seq_fields.bits.mb_adaptive_frame_field_flag);
    bw_flag(bw, pp->seq_fields.bits.direct_8x8_inference_flag);
    bw_flag(bw, 0);
    bw_flag(bw, 1);

    /* VUI: only a reorder depth of 0, so a decoder's own DPB hands each picture out at once */
    bw_bits(bw, 4, 0);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_flag(bw, 1);
    bw_flag(bw, 1);
    bw_ue(bw, 0);
    bw_ue(bw, 0);
    bw_ue(bw, MAX_MV_LENGTH_LOG2);
    bw_ue(bw, MAX_MV_LENGTH_LOG2);
    bw_ue(bw, 0);
    bw_ue(bw, pp->num_ref_frames);
    bw_trailing(bw);
}

static bool is_flat(const uint8_t *list, size_t size)
{
    for (size_t i = 0; i < size; i++)
        if (list[i] != FLAT_SCALE)
            return false;
    return true;
}

static void write_scaling_list(struct bit_writer *bw, const uint8_t *raster, const uint8_t *zigzag,
                               size_t size)
{
    int last = SCALING_LIST_START;
    for (size_t i = 0; i < size; i++) {
        int delta = raster[zigzag[i]] - last;
        delta = delta > INT8_MAX ? delta - 256 : delta < INT8_MIN ? delta + 256 : delta;
        bw_se(bw, delta);
        last = raster[zigzag[i]];
    }
}

static void write_pps(struct bit_writer *bw, const struct h264_state *st, unsigned pps_id,
                      const VAPictureParameterBufferH264 *pp, const VAIQMatrixBufferH264 *iq)
{
    bool transform_8x8 = pp->pic_fields.bits.transform_8x8_mode_flag;
    bool scaling = iq && (!is_flat(&iq->ScalingList4x4[0][0], sizeof(iq->ScalingList4x4)) ||
                          !is_flat(&iq->ScalingList8x8[0][0], sizeof(iq->ScalingList8x8)));

    bw_init(bw);
    bw_ue(bw, pps_id);
    bw_ue(bw, 0);
    bw_flag(bw, pp->pic_fields.bits.entropy_coding_mode_flag);
    bw_flag(bw, pp->pic_fields.bits.pic_order_present_flag);
    bw_ue(bw, 0);
    bw_ue(bw, st->num_ref_idx_l0_default[pps_id]);
    bw_ue(bw, st->num_ref_idx_l1_default[pps_id]);
    bw_flag(bw, pp->pic_fields.bits.weighted_pred_flag);
    bw_bits(bw, 2, pp->pic_fields.bits.weighted_bipred_idc);
    /* FFmpeg, the one client of High 10 (no other VA driver decodes it), adds QpBdOffset */
    int qp_bd_offset = QP_BD_OFFSET_PER_BIT * pp->bit_depth_luma_minus8;
    bw_se(bw, pp->pic_init_qp_minus26 - qp_bd_offset);
    bw_se(bw, pp->pic_init_qs_minus26 - qp_bd_offset);
    bw_se(bw, pp->chroma_qp_index_offset);
    bw_flag(bw, pp->pic_fields.bits.deblocking_filter_control_present_flag);
    bw_flag(bw, pp->pic_fields.bits.constrained_intra_pred_flag);
    bw_flag(bw, pp->pic_fields.bits.redundant_pic_cnt_present_flag);
    if (transform_8x8 || scaling || pp->second_chroma_qp_index_offset != pp->chroma_qp_index_offset) {
        bw_flag(bw, transform_8x8);
        bw_flag(bw, scaling);
        if (scaling) {
            for (unsigned i = 0; i < 6; i++) {
                bw_flag(bw, 1);
                write_scaling_list(bw, iq->ScalingList4x4[i], zigzag_4x4, 16);
            }
            for (unsigned i = 0; transform_8x8 && i < 2; i++) {
                bw_flag(bw, 1);
                write_scaling_list(bw, iq->ScalingList8x8[i], zigzag_8x8, 64);
            }
        }
        bw_se(bw, pp->second_chroma_qp_index_offset);
    }
    bw_trailing(bw);
}

static bool same_rbsp(const struct bit_writer *a, const struct bit_writer *b)
{
    return a->bits == b->bits && !memcmp(a->data, b->data, bw_bytes(a));
}

static int h264_build_packet(void *state, const struct picture *pic, struct annexb *out,
                             struct packet_info *info)
{
    struct h264_state *st = state;
    const VAPictureParameterBufferH264 *pp = pic->picture_param;
    struct slice_header first = { 0 };
    struct bit_writer sps, pps;
    int ret;

    if (!pp || !pic->num_slices)
        return -EINVAL;
    /* VA carries no POC cycle, which type 1 needs */
    if (pp->seq_fields.bits.pic_order_cnt_type == POC_TYPE_DELTA)
        return -ENOTSUP;

    for (unsigned i = 0; i < pic->num_slices; i++) {
        const VASliceParameterBufferH264 *sp = pic->slices[i].param;
        struct slice_header sh;
        if (!parse_slice_header(pp, &pic->slices[i], &sh))
            return -EINVAL;
        if (!i)
            first = sh;
        if (is_inter(sh.slice_type) && !sh.overrides_num_ref_idx)
            st->num_ref_idx_l0_default[sh.pps_id] = sp->num_ref_idx_l0_active_minus1;
        if (sh.slice_type == SLICE_B && !sh.overrides_num_ref_idx)
            st->num_ref_idx_l1_default[sh.pps_id] = sp->num_ref_idx_l1_active_minus1;
    }

    bool idr = first.nal_unit_type == NAL_IDR_SLICE;
    write_sps(&sps, pp);
    if (idr || !same_rbsp(&sps, &st->sent_sps)) {
        if ((ret = annexb_append_rbsp(out, &(uint8_t){ NAL_REF_IDC_HIGHEST | NAL_SPS }, 1, &sps)))
            return ret;
        st->sent_sps = sps;
    }
    write_pps(&pps, st, first.pps_id, pp, pic->iq_matrix);
    if (idr || st->sent_pps_id != (int)first.pps_id || !same_rbsp(&pps, &st->sent_pps)) {
        if ((ret = annexb_append_rbsp(out, &(uint8_t){ NAL_REF_IDC_HIGHEST | NAL_PPS }, 1, &pps)))
            return ret;
        st->sent_pps = pps;
        st->sent_pps_id = first.pps_id;
    }
    for (unsigned i = 0; i < pic->num_slices; i++)
        if ((ret = annexb_append_nal(out, pic->slices[i].data, pic->slices[i].size)))
            return ret;
    return 0;
}

static void h264_restart(void *state)
{
    struct h264_state *st = state;
    st->sent_sps.bits = st->sent_pps.bits = 0;
    st->sent_pps_id = -1;
}

const struct codec codec_h264 = {
    .kind = CODEC_H264,
    .state_size = sizeof(struct h264_state),
    .build_packet = h264_build_packet,
    .restart = h264_restart,
};
