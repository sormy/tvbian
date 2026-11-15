/*
 * H.264 onto the stateless controls. VA leaves out what the controls need from the slice header
 * (nal_ref_idc, idr_pic_id, the POC fields and the bit sizes of their syntax and of
 * dec_ref_pic_marking()), so each slice header is read again with VA's picture parameters.
 */
#include <errno.h>
#include <string.h>

#include "request.h"

enum {
    NAL_IDR_SLICE = 5,
    NAL_TYPE_MASK = 0x1f,
    NAL_REF_IDC_SHIFT = 5,
    NAL_REF_IDC_MASK = 3,
    SLICE_P = 0,
    SLICE_B = 1,
    SLICE_I = 2,
    SLICE_SP = 3,
    SLICE_SI = 4,
    SLICE_TYPES = 5,
    POC_TYPE_LSB = 0,
    POC_TYPE_DELTA = 1,
    MODIFICATION_END = 3,
    MMCO_END = 0,
    LEVEL_5_1 = 51,
    PROFILE_HIGH = 100,
    PROFILE_HIGH10 = 110,
    NUM_CONTROLS = 6,
    NAL_HEADER_BITS = 8,
    MAX_PPS = 256,
};

static const uint8_t start_code[] = { 0, 0, 1 };

struct h264_state {
    int decode_mode;
    int start_code;
    uint8_t num_ref_idx_l0_default[MAX_PPS];
    uint8_t num_ref_idx_l1_default[MAX_PPS];
    /* learned from a slice that does not override; before that no slice reads it */
    bool l0_default_known[MAX_PPS];
};

/* what the slice header holds and VA does not pass on */
struct slice_header {
    unsigned nal_ref_idc;
    unsigned nal_unit_type;
    unsigned slice_type;
    unsigned pps_id;
    bool field_pic;
    bool bottom_field;
    bool overrides_num_ref_idx;
    unsigned idr_pic_id;
    unsigned pic_order_cnt_lsb;
    int delta_pic_order_cnt_bottom;
    int delta_pic_order_cnt[2];
    unsigned redundant_pic_cnt;
    unsigned pic_order_cnt_bit_size;
    unsigned dec_ref_pic_marking_bit_size;
    unsigned header_bit_size;
};

static bool is_p(unsigned type)
{
    return type == SLICE_P || type == SLICE_SP;
}

static void skip_modifications(struct bit_reader *br)
{
    if (!br_bits(br, 1))
        return;
    for (unsigned idc = br_ue(br); idc != MODIFICATION_END && !br->overrun; idc = br_ue(br))
        br_ue(br);
}

static void skip_weights(struct bit_reader *br, unsigned count, bool chroma)
{
    for (unsigned i = 0; i < count && !br->overrun; i++) {
        if (br_bits(br, 1)) {
            br_se(br);
            br_se(br);
        }
        if (chroma && br_bits(br, 1)) {
            br_se(br);
            br_se(br);
            br_se(br);
            br_se(br);
        }
    }
}

static void skip_marking(struct bit_reader *br, bool idr)
{
    if (idr) {
        br_bits(br, 2);
        return;
    }
    if (!br_bits(br, 1))
        return;
    for (unsigned mmco = br_ue(br); mmco != MMCO_END && !br->overrun; mmco = br_ue(br)) {
        if (mmco == 1 || mmco == 3)
            br_ue(br);
        if (mmco == 2)
            br_ue(br);
        if (mmco == 3 || mmco == 6)
            br_ue(br);
        if (mmco == 4)
            br_ue(br);
    }
}

/* 7.3.3, whole: header_bit_size reaches slice_data() */
static bool parse_slice_header(const VAPictureParameterBufferH264 *pp,
                               const VASliceParameterBufferH264 *sp, const struct slice *s,
                               struct slice_header *sh)
{
    struct bit_reader br;
    memset(sh, 0, sizeof(*sh));
    if (s->size < 2)
        return false;
    sh->nal_ref_idc = (s->data[0] >> NAL_REF_IDC_SHIFT) & NAL_REF_IDC_MASK;
    sh->nal_unit_type = s->data[0] & NAL_TYPE_MASK;
    br_init(&br, s->data + 1, s->size - 1);
    br_ue(&br);
    sh->slice_type = br_ue(&br) % SLICE_TYPES;
    if ((sh->pps_id = br_ue(&br)) >= MAX_PPS)
        return false;
    if (pp->seq_fields.bits.residual_colour_transform_flag)
        br_bits(&br, 2);
    br_bits(&br, pp->seq_fields.bits.log2_max_frame_num_minus4 + 4);
    if (!pp->seq_fields.bits.frame_mbs_only_flag && (sh->field_pic = br_bits(&br, 1)))
        sh->bottom_field = br_bits(&br, 1);
    if (sh->nal_unit_type == NAL_IDR_SLICE)
        sh->idr_pic_id = br_ue(&br);
    size_t poc_start = br_rbsp_position(&br);
    bool bottom_present = pp->pic_fields.bits.pic_order_present_flag && !sh->field_pic;
    if (pp->seq_fields.bits.pic_order_cnt_type == POC_TYPE_LSB) {
        sh->pic_order_cnt_lsb = br_bits(&br, pp->seq_fields.bits.log2_max_pic_order_cnt_lsb_minus4 + 4);
        if (bottom_present)
            sh->delta_pic_order_cnt_bottom = br_se(&br);
    }
    if (pp->seq_fields.bits.pic_order_cnt_type == POC_TYPE_DELTA &&
        !pp->seq_fields.bits.delta_pic_order_always_zero_flag) {
        sh->delta_pic_order_cnt[0] = br_se(&br);
        if (bottom_present)
            sh->delta_pic_order_cnt[1] = br_se(&br);
    }
    sh->pic_order_cnt_bit_size = br_rbsp_position(&br) - poc_start;
    if (pp->pic_fields.bits.redundant_pic_cnt_present_flag)
        sh->redundant_pic_cnt = br_ue(&br);
    if (sh->slice_type == SLICE_B)
        br_bits(&br, 1);
    if (is_p(sh->slice_type) || sh->slice_type == SLICE_B) {
        if ((sh->overrides_num_ref_idx = br_bits(&br, 1))) {
            br_ue(&br);
            if (sh->slice_type == SLICE_B)
                br_ue(&br);
        }
        skip_modifications(&br);
        if (sh->slice_type == SLICE_B)
            skip_modifications(&br);
    }
    bool weighted = (pp->pic_fields.bits.weighted_pred_flag && is_p(sh->slice_type)) ||
                    (pp->pic_fields.bits.weighted_bipred_idc == 1 && sh->slice_type == SLICE_B);
    bool chroma = pp->seq_fields.bits.chroma_format_idc != 0;
    if (weighted) {
        br_ue(&br);
        if (chroma)
            br_ue(&br);
        skip_weights(&br, sp->num_ref_idx_l0_active_minus1 + 1, chroma);
        if (sh->slice_type == SLICE_B)
            skip_weights(&br, sp->num_ref_idx_l1_active_minus1 + 1, chroma);
    }
    size_t marking_start = br_rbsp_position(&br);
    if (sh->nal_ref_idc)
        skip_marking(&br, sh->nal_unit_type == NAL_IDR_SLICE);
    sh->dec_ref_pic_marking_bit_size = br_rbsp_position(&br) - marking_start;
    if (pp->pic_fields.bits.entropy_coding_mode_flag && sh->slice_type != SLICE_I &&
        sh->slice_type != SLICE_SI)
        br_ue(&br);
    br_se(&br);
    if (sh->slice_type == SLICE_SP || sh->slice_type == SLICE_SI) {
        if (sh->slice_type == SLICE_SP)
            br_bits(&br, 1);
        br_se(&br);
    }
    if (pp->pic_fields.bits.deblocking_filter_control_present_flag && br_ue(&br) != 1) {
        br_se(&br);
        br_se(&br);
    }
    /* counted from the NAL header byte, in the bitstream without emulation prevention */
    sh->header_bit_size = br_rbsp_position(&br) + NAL_HEADER_BITS;
    return !br.overrun;
}

/* High or High 10, a superset of the syntax VA delivers */
static void fill_sps(struct v4l2_ctrl_h264_sps *sps, const VAPictureParameterBufferH264 *pp)
{
    unsigned frame_mbs_only = pp->seq_fields.bits.frame_mbs_only_flag;
    *sps = (struct v4l2_ctrl_h264_sps){
        .profile_idc = pp->bit_depth_luma_minus8 ? PROFILE_HIGH10 : PROFILE_HIGH,
        .level_idc = LEVEL_5_1,
        .chroma_format_idc = pp->seq_fields.bits.chroma_format_idc,
        .bit_depth_luma_minus8 = pp->bit_depth_luma_minus8,
        .bit_depth_chroma_minus8 = pp->bit_depth_chroma_minus8,
        .log2_max_frame_num_minus4 = pp->seq_fields.bits.log2_max_frame_num_minus4,
        .pic_order_cnt_type = pp->seq_fields.bits.pic_order_cnt_type,
        .log2_max_pic_order_cnt_lsb_minus4 = pp->seq_fields.bits.log2_max_pic_order_cnt_lsb_minus4,
        .max_num_ref_frames = pp->num_ref_frames,
        .pic_width_in_mbs_minus1 = pp->picture_width_in_mbs_minus1,
        /* VA's height is the frame's; the SPS counts map units, fields when not frame_mbs_only */
        .pic_height_in_map_units_minus1 =
            (pp->picture_height_in_mbs_minus1 + 1) / (2 - frame_mbs_only) - 1,
    };
    const struct {
        bool set;
        uint64_t flag;
    } flags[] = {
        { pp->seq_fields.bits.residual_colour_transform_flag, V4L2_H264_SPS_FLAG_SEPARATE_COLOUR_PLANE },
        { pp->seq_fields.bits.delta_pic_order_always_zero_flag,
          V4L2_H264_SPS_FLAG_DELTA_PIC_ORDER_ALWAYS_ZERO },
        { pp->seq_fields.bits.gaps_in_frame_num_value_allowed_flag,
          V4L2_H264_SPS_FLAG_GAPS_IN_FRAME_NUM_VALUE_ALLOWED },
        { frame_mbs_only, V4L2_H264_SPS_FLAG_FRAME_MBS_ONLY },
        { pp->seq_fields.bits.mb_adaptive_frame_field_flag, V4L2_H264_SPS_FLAG_MB_ADAPTIVE_FRAME_FIELD },
        { pp->seq_fields.bits.direct_8x8_inference_flag, V4L2_H264_SPS_FLAG_DIRECT_8X8_INFERENCE },
    };
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); i++)
        if (flags[i].set)
            sps->flags |= flags[i].flag;
}

static void fill_pps(struct v4l2_ctrl_h264_pps *pps, const struct h264_state *st,
                     const struct slice_header *sh, const VAPictureParameterBufferH264 *pp,
                     bool scaling)
{
    *pps = (struct v4l2_ctrl_h264_pps){
        .pic_parameter_set_id = sh->pps_id,
        .num_ref_idx_l0_default_active_minus1 = st->num_ref_idx_l0_default[sh->pps_id],
        .num_ref_idx_l1_default_active_minus1 = st->num_ref_idx_l1_default[sh->pps_id],
        .weighted_bipred_idc = pp->pic_fields.bits.weighted_bipred_idc,
        .pic_init_qp_minus26 = pp->pic_init_qp_minus26,
        .pic_init_qs_minus26 = pp->pic_init_qs_minus26,
        .chroma_qp_index_offset = pp->chroma_qp_index_offset,
        .second_chroma_qp_index_offset = pp->second_chroma_qp_index_offset,
    };
    const struct {
        bool set;
        uint64_t flag;
    } flags[] = {
        { pp->pic_fields.bits.entropy_coding_mode_flag, V4L2_H264_PPS_FLAG_ENTROPY_CODING_MODE },
        { pp->pic_fields.bits.pic_order_present_flag,
          V4L2_H264_PPS_FLAG_BOTTOM_FIELD_PIC_ORDER_IN_FRAME_PRESENT },
        { pp->pic_fields.bits.weighted_pred_flag, V4L2_H264_PPS_FLAG_WEIGHTED_PRED },
        { pp->pic_fields.bits.deblocking_filter_control_present_flag,
          V4L2_H264_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT },
        { pp->pic_fields.bits.constrained_intra_pred_flag, V4L2_H264_PPS_FLAG_CONSTRAINED_INTRA_PRED },
        { pp->pic_fields.bits.redundant_pic_cnt_present_flag,
          V4L2_H264_PPS_FLAG_REDUNDANT_PIC_CNT_PRESENT },
        { pp->pic_fields.bits.transform_8x8_mode_flag, V4L2_H264_PPS_FLAG_TRANSFORM_8X8_MODE },
        { scaling, V4L2_H264_PPS_FLAG_SCALING_MATRIX_PRESENT },
    };
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); i++)
        if (flags[i].set)
            pps->flags |= flags[i].flag;
}

static bool is_valid_reference(const VAPictureH264 *ref)
{
    return ref->picture_id != VA_INVALID_SURFACE && !(ref->flags & VA_PICTURE_H264_INVALID);
}

static uint8_t fields_of(uint32_t va_flags)
{
    if (va_flags & VA_PICTURE_H264_TOP_FIELD && !(va_flags & VA_PICTURE_H264_BOTTOM_FIELD))
        return V4L2_H264_TOP_FIELD_REF;
    if (va_flags & VA_PICTURE_H264_BOTTOM_FIELD && !(va_flags & VA_PICTURE_H264_TOP_FIELD))
        return V4L2_H264_BOTTOM_FIELD_REF;
    return V4L2_H264_FRAME_REF;
}

/* the DPB from VA's reference frames, in their order: the lists index into it */
static void fill_decode_params(const struct request_ctx *rq,
                               struct v4l2_ctrl_h264_decode_params *dp,
                               const VAPictureParameterBufferH264 *pp,
                               const struct slice_header *sh, bool any_p, bool any_b)
{
    *dp = (struct v4l2_ctrl_h264_decode_params){
        .nal_ref_idc = sh->nal_ref_idc,
        .frame_num = pp->frame_num,
        .top_field_order_cnt = pp->CurrPic.TopFieldOrderCnt,
        .bottom_field_order_cnt = pp->CurrPic.BottomFieldOrderCnt,
        .idr_pic_id = sh->idr_pic_id,
        .pic_order_cnt_lsb = sh->pic_order_cnt_lsb,
        .delta_pic_order_cnt_bottom = sh->delta_pic_order_cnt_bottom,
        .delta_pic_order_cnt0 = sh->delta_pic_order_cnt[0],
        .delta_pic_order_cnt1 = sh->delta_pic_order_cnt[1],
        .dec_ref_pic_marking_bit_size = sh->dec_ref_pic_marking_bit_size,
        .pic_order_cnt_bit_size = sh->pic_order_cnt_bit_size,
    };
    if (sh->nal_unit_type == NAL_IDR_SLICE)
        dp->flags |= V4L2_H264_DECODE_PARAM_FLAG_IDR_PIC;
    if (sh->field_pic)
        dp->flags |= V4L2_H264_DECODE_PARAM_FLAG_FIELD_PIC;
    if (sh->bottom_field)
        dp->flags |= V4L2_H264_DECODE_PARAM_FLAG_BOTTOM_FIELD;
    if (any_p)
        dp->flags |= V4L2_H264_DECODE_PARAM_FLAG_PFRAME;
    if (any_b)
        dp->flags |= V4L2_H264_DECODE_PARAM_FLAG_BFRAME;
    for (unsigned i = 0; i < V4L2_H264_NUM_DPB_ENTRIES; i++) {
        const VAPictureH264 *ref = &pp->ReferenceFrames[i];
        if (!is_valid_reference(ref))
            continue;
        bool long_term = ref->flags & VA_PICTURE_H264_LONG_TERM_REFERENCE;
        dp->dpb[i] = (struct v4l2_h264_dpb_entry){
            .reference_ts = request_timestamp(rq, ref->picture_id),
            .pic_num = ref->frame_idx,
            .frame_num = ref->frame_idx,
            .fields = fields_of(ref->flags),
            .top_field_order_cnt = ref->TopFieldOrderCnt,
            .bottom_field_order_cnt = ref->BottomFieldOrderCnt,
            .flags = V4L2_H264_DPB_ENTRY_FLAG_VALID | V4L2_H264_DPB_ENTRY_FLAG_ACTIVE |
                     (long_term ? V4L2_H264_DPB_ENTRY_FLAG_LONG_TERM : 0) |
                     (sh->field_pic ? V4L2_H264_DPB_ENTRY_FLAG_FIELD : 0),
        };
    }
}

static void fill_list(struct v4l2_h264_reference *list, const VAPictureH264 *va_list,
                      unsigned count, const VAPictureParameterBufferH264 *pp)
{
    for (unsigned i = 0; i < count && i < V4L2_H264_REF_LIST_LEN; i++) {
        for (unsigned d = 0; d < V4L2_H264_NUM_DPB_ENTRIES; d++) {
            if (is_valid_reference(&va_list[i]) &&
                pp->ReferenceFrames[d].picture_id == va_list[i].picture_id) {
                list[i] = (struct v4l2_h264_reference){ fields_of(va_list[i].flags), d };
                break;
            }
        }
    }
}

static void fill_slice_params(struct v4l2_ctrl_h264_slice_params *slice,
                              const struct slice_header *sh, const VASliceParameterBufferH264 *sp,
                              const VAPictureParameterBufferH264 *pp)
{
    *slice = (struct v4l2_ctrl_h264_slice_params){
        .header_bit_size = sh->header_bit_size,
        .first_mb_in_slice = sp->first_mb_in_slice,
        .slice_type = sh->slice_type,
        .redundant_pic_cnt = sh->redundant_pic_cnt,
        .cabac_init_idc = sp->cabac_init_idc,
        .slice_qp_delta = sp->slice_qp_delta,
        .disable_deblocking_filter_idc = sp->disable_deblocking_filter_idc,
        .slice_alpha_c0_offset_div2 = sp->slice_alpha_c0_offset_div2,
        .slice_beta_offset_div2 = sp->slice_beta_offset_div2,
        .num_ref_idx_l0_active_minus1 = sp->num_ref_idx_l0_active_minus1,
        .num_ref_idx_l1_active_minus1 = sp->num_ref_idx_l1_active_minus1,
        .flags = sp->direct_spatial_mv_pred_flag ? V4L2_H264_SLICE_FLAG_DIRECT_SPATIAL_MV_PRED : 0,
    };
    if (sh->slice_type != SLICE_I && sh->slice_type != SLICE_SI)
        fill_list(slice->ref_pic_list0, sp->RefPicList0, sp->num_ref_idx_l0_active_minus1 + 1, pp);
    if (sh->slice_type == SLICE_B)
        fill_list(slice->ref_pic_list1, sp->RefPicList1, sp->num_ref_idx_l1_active_minus1 + 1, pp);
}

static void fill_weights(struct v4l2_ctrl_h264_pred_weights *w, const VASliceParameterBufferH264 *sp)
{
    *w = (struct v4l2_ctrl_h264_pred_weights){
        .luma_log2_weight_denom = sp->luma_log2_weight_denom,
        .chroma_log2_weight_denom = sp->chroma_log2_weight_denom,
    };
    memcpy(w->weight_factors[0].luma_weight, sp->luma_weight_l0, sizeof(sp->luma_weight_l0));
    memcpy(w->weight_factors[0].luma_offset, sp->luma_offset_l0, sizeof(sp->luma_offset_l0));
    memcpy(w->weight_factors[0].chroma_weight, sp->chroma_weight_l0, sizeof(sp->chroma_weight_l0));
    memcpy(w->weight_factors[0].chroma_offset, sp->chroma_offset_l0, sizeof(sp->chroma_offset_l0));
    memcpy(w->weight_factors[1].luma_weight, sp->luma_weight_l1, sizeof(sp->luma_weight_l1));
    memcpy(w->weight_factors[1].luma_offset, sp->luma_offset_l1, sizeof(sp->luma_offset_l1));
    memcpy(w->weight_factors[1].chroma_weight, sp->chroma_weight_l1, sizeof(sp->chroma_weight_l1));
    memcpy(w->weight_factors[1].chroma_offset, sp->chroma_offset_l1, sizeof(sp->chroma_offset_l1));
}

static void fill_scaling(struct v4l2_ctrl_h264_scaling_matrix *m, const VAIQMatrixBufferH264 *iq)
{
    /* both in raster order; V4L2's 8x8 lists are Intra Y, Inter Y first, then chroma's */
    memcpy(m->scaling_list_4x4, iq->ScalingList4x4, sizeof(m->scaling_list_4x4));
    memcpy(m->scaling_list_8x8[0], iq->ScalingList8x8[0], sizeof(m->scaling_list_8x8[0]));
    memcpy(m->scaling_list_8x8[1], iq->ScalingList8x8[1], sizeof(m->scaling_list_8x8[1]));
}

static void dump_slice(struct request_ctx *rq, const struct slice_header *sh,
                       const struct v4l2_ctrl_h264_slice_params *slice)
{
    request_dump(rq, "first_mb_in_slice", slice->first_mb_in_slice);
    request_dump(rq, "slice_type", sh->slice_type);
    request_dump(rq, "pic_parameter_set_id", sh->pps_id);
    if (sh->nal_unit_type == NAL_IDR_SLICE)
        request_dump(rq, "idr_pic_id", sh->idr_pic_id);
    request_dump(rq, "pic_order_cnt_lsb", sh->pic_order_cnt_lsb);
    request_dump(rq, "slice_qp_delta", slice->slice_qp_delta);
    request_dump(rq, "disable_deblocking_filter_idc", slice->disable_deblocking_filter_idc);
    request_dump(rq, "header_bit_size", slice->header_bit_size);
}

static int h264_init(struct request_ctx *rq)
{
    struct h264_state *st = rq->codec_state;
    if (request_get_control(rq, V4L2_CID_STATELESS_H264_DECODE_MODE, &st->decode_mode) < 0)
        st->decode_mode = V4L2_STATELESS_H264_DECODE_MODE_SLICE_BASED;
    if (request_get_control(rq, V4L2_CID_STATELESS_H264_START_CODE, &st->start_code) < 0)
        st->start_code = V4L2_STATELESS_H264_START_CODE_NONE;
    return 0;
}

static int append_slice(struct annexb *data, const struct h264_state *st, const struct slice *s)
{
    int ret = st->start_code == V4L2_STATELESS_H264_START_CODE_ANNEX_B
                  ? annexb_append_raw(data, start_code, sizeof(start_code))
                  : 0;
    return ret ? ret : annexb_append_raw(data, s->data, s->size);
}

static int h264_submit(struct request_ctx *rq, const struct picture *pic)
{
    struct h264_state *st = rq->codec_state;
    const VAPictureParameterBufferH264 *pp = pic->picture_param;
    const VAIQMatrixBufferH264 *iq = pic->iq_matrix;
    struct slice_header first, sh;
    struct v4l2_ctrl_h264_sps sps;
    struct v4l2_ctrl_h264_pps pps;
    struct v4l2_ctrl_h264_scaling_matrix scaling = { 0 };
    struct v4l2_ctrl_h264_decode_params decode;
    struct v4l2_ctrl_h264_slice_params slice;
    struct v4l2_ctrl_h264_pred_weights weights;
    struct annexb data = { 0 };
    bool any_p = false, any_b = false;
    int ret = 0;

    if (!pp || !pic->num_slices)
        return -EINVAL;
    for (unsigned i = 0; i < pic->num_slices; i++) {
        const VASliceParameterBufferH264 *sp = pic->slices[i].param;
        if (!sp || !parse_slice_header(pp, sp, &pic->slices[i], &sh))
            return -EINVAL;
        if (!i)
            first = sh;
        any_p |= is_p(sh.slice_type);
        any_b |= sh.slice_type == SLICE_B;
        /* the PPS defaults VA leaves out: what a slice that does not override uses */
        if (!sh.overrides_num_ref_idx && sh.slice_type != SLICE_I && sh.slice_type != SLICE_SI) {
            st->num_ref_idx_l0_default[sh.pps_id] = sp->num_ref_idx_l0_active_minus1;
            st->l0_default_known[sh.pps_id] = true;
        }
        if (!sh.overrides_num_ref_idx && sh.slice_type == SLICE_B)
            st->num_ref_idx_l1_default[sh.pps_id] = sp->num_ref_idx_l1_active_minus1;
    }
    fill_sps(&sps, pp);
    fill_pps(&pps, st, &first, pp, iq != NULL);
    if (iq)
        fill_scaling(&scaling, iq);
    fill_decode_params(rq, &decode, pp, &first, any_p, any_b);
    request_dump(rq, "log2_max_frame_num_minus4", sps.log2_max_frame_num_minus4);
    request_dump(rq, "pic_order_cnt_type", sps.pic_order_cnt_type);
    request_dump(rq, "max_num_ref_frames", sps.max_num_ref_frames);
    request_dump(rq, "pic_height_in_map_units_minus1", sps.pic_height_in_map_units_minus1);
    if (st->l0_default_known[first.pps_id])
        request_dump(rq, "num_ref_idx_l0_default_active_minus1",
                     pps.num_ref_idx_l0_default_active_minus1);
    request_dump(rq, "pic_init_qp_minus26", pps.pic_init_qp_minus26);

    struct v4l2_ext_control controls[NUM_CONTROLS] = {
        { .id = V4L2_CID_STATELESS_H264_SPS, .size = sizeof(sps), .ptr = &sps },
        { .id = V4L2_CID_STATELESS_H264_PPS, .size = sizeof(pps), .ptr = &pps },
        { .id = V4L2_CID_STATELESS_H264_SCALING_MATRIX, .size = sizeof(scaling), .ptr = &scaling },
        { .id = V4L2_CID_STATELESS_H264_DECODE_PARAMS, .size = sizeof(decode), .ptr = &decode },
        { .id = V4L2_CID_STATELESS_H264_SLICE_PARAMS, .size = sizeof(slice), .ptr = &slice },
        { .id = V4L2_CID_STATELESS_H264_PRED_WEIGHTS, .size = sizeof(weights), .ptr = &weights },
    };
    bool frame_based = st->decode_mode == V4L2_STATELESS_H264_DECODE_MODE_FRAME_BASED;
    for (unsigned i = 0; i < pic->num_slices && !ret; i++) {
        const VASliceParameterBufferH264 *sp = pic->slices[i].param;
        bool last = i + 1 == pic->num_slices;
        parse_slice_header(pp, sp, &pic->slices[i], &sh);
        fill_slice_params(&slice, &sh, sp, pp);
        fill_weights(&weights, sp);
        dump_slice(rq, &sh, &slice);
        if ((ret = append_slice(&data, st, &pic->slices[i])))
            break;
        if (frame_based && !last)
            continue;
        bool weighted = (pps.flags & V4L2_H264_PPS_FLAG_WEIGHTED_PRED && is_p(sh.slice_type)) ||
                        (pps.weighted_bipred_idc == 1 && sh.slice_type == SLICE_B);
        /* a frame-based engine takes no slice parameters, a slice-based one each slice's */
        unsigned count = frame_based ? 4 : weighted ? NUM_CONTROLS : NUM_CONTROLS - 1;
        ret = request_queue(rq, controls, count, &data, frame_based || !i, last);
        data.size = 0;
    }
    annexb_free(&data);
    return ret;
}

const struct request_codec request_h264 = {
    .kind = CODEC_H264,
    .pixelformat = V4L2_PIX_FMT_H264_SLICE,
    .state_size = sizeof(struct h264_state),
    .init = h264_init,
    .submit = h264_submit,
};
