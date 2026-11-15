/*
 * HEVC onto the stateless controls. VA leaves out the long-term set's size, the entry points
 * and no_output_of_prior_pics_flag: each slice header is read in full, with VA's parameters
 * for the syntax it depends on. The current picture's sets come from VA's reference flags.
 */
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include "request.h"

enum {
    NAL_BLA_W_LP = 16,
    NAL_IDR_W_RADL = 19,
    NAL_IDR_N_LP = 20,
    NAL_IRAP_LAST = 23,
    NAL_HEADER_SIZE = 2,
    TEMPORAL_ID_MASK = 7,
    SLICE_B = 0,
    SLICE_P = 1,
    MAX_HEADER_BYTES = 1024,
    MAX_ENTRY_POINTS = 4096,
    NUM_CONTROLS = 6,
};

static const uint8_t start_code[] = { 0, 0, 1 };

struct hevc_state {
    int decode_mode;
    int start_code;
    uint32_t entry_points[MAX_ENTRY_POINTS];
};

struct slice_header {
    unsigned nal_unit_type;
    unsigned temporal_id_plus1;
    bool first_slice;
    bool no_output_of_prior_pics;
    bool dependent;
    unsigned segment_address;
    unsigned pic_order_cnt_lsb;
    unsigned long_term_bits;
    bool collocated_present;
    unsigned collocated_ref_idx;
    unsigned num_entry_points;
    /* where slice_data() starts in the bytes as they came */
    size_t raw_data_offset;
};

static unsigned ceil_log2(unsigned value)
{
    unsigned bits = 0;
    while ((1u << bits) < value)
        bits++;
    return bits;
}

static bool is_irap(unsigned type)
{
    return type >= NAL_BLA_W_LP && type <= NAL_IRAP_LAST;
}

static bool is_idr(unsigned type)
{
    return type == NAL_IDR_W_RADL || type == NAL_IDR_N_LP;
}

static unsigned pictures_in_current_sets(const VAPictureParameterBufferHEVC *pp)
{
    unsigned count = 0;
    for (unsigned i = 0; i < 15; i++)
        count += !!(pp->ReferenceFrames[i].flags &
                    (VA_PICTURE_HEVC_RPS_ST_CURR_BEFORE | VA_PICTURE_HEVC_RPS_ST_CURR_AFTER |
                     VA_PICTURE_HEVC_RPS_LT_CURR));
    return count;
}

static void skip_list_modification(struct bit_reader *br, unsigned entries, unsigned bits)
{
    if (br_bits(br, 1))
        for (unsigned i = 0; i < entries; i++)
            br_bits(br, bits);
}

static void skip_weights(struct bit_reader *br, unsigned entries, bool chroma)
{
    bool luma_flags[15] = { 0 }, chroma_flags[15] = { 0 };
    for (unsigned i = 0; i < entries; i++)
        luma_flags[i] = br_bits(br, 1);
    for (unsigned i = 0; chroma && i < entries; i++)
        chroma_flags[i] = br_bits(br, 1);
    for (unsigned i = 0; i < entries; i++) {
        if (luma_flags[i]) {
            br_se(br);
            br_se(br);
        }
        for (unsigned c = 0; chroma_flags[i] && c < 2; c++) {
            br_se(br);
            br_se(br);
        }
    }
}

/* 7.3.6.1 in full, over the unescaped header; entry points kept */
static bool parse_slice_header(const VAPictureParameterBufferHEVC *pp,
                               const VASliceParameterBufferHEVC *sp, const uint8_t *rbsp,
                               size_t size, struct slice_header *sh, uint32_t *entry_points)
{
    const typeof(pp->slice_parsing_fields.bits) *parsing = &pp->slice_parsing_fields.bits;
    const typeof(pp->pic_fields.bits) *fields = &pp->pic_fields.bits;
    unsigned ctb_log2 = pp->log2_min_luma_coding_block_size_minus3 + 3 +
                        pp->log2_diff_max_min_luma_coding_block_size;
    unsigned ctb = 1u << ctb_log2;
    unsigned ctbs = ((pp->pic_width_in_luma_samples + ctb - 1) >> ctb_log2) *
                    ((pp->pic_height_in_luma_samples + ctb - 1) >> ctb_log2);
    unsigned slice_type = sp->LongSliceFlags.fields.slice_type;
    bool chroma = fields->chroma_format_idc != 0;
    bool temporal_mvp = false, sao = false;
    struct bit_reader br;

    memset(sh, 0, sizeof(*sh));
    sh->nal_unit_type = (rbsp[0] >> 1) & 0x3f;
    sh->temporal_id_plus1 = rbsp[1] & TEMPORAL_ID_MASK;
    br_init_unescaped(&br, rbsp + NAL_HEADER_SIZE, size - NAL_HEADER_SIZE);
    sh->first_slice = br_bits(&br, 1);
    if (is_irap(sh->nal_unit_type))
        sh->no_output_of_prior_pics = br_bits(&br, 1);
    br_ue(&br);
    if (!sh->first_slice) {
        if (parsing->dependent_slice_segments_enabled_flag)
            sh->dependent = br_bits(&br, 1);
        sh->segment_address = br_bits(&br, ceil_log2(ctbs));
    }
    if (!sh->dependent) {
        br_bits(&br, pp->num_extra_slice_header_bits);
        br_ue(&br);
        if (parsing->output_flag_present_flag)
            br_bits(&br, 1);
        if (fields->separate_colour_plane_flag)
            br_bits(&br, 2);
        if (!is_idr(sh->nal_unit_type)) {
            sh->pic_order_cnt_lsb = br_bits(&br, pp->log2_max_pic_order_cnt_lsb_minus4 + 4);
            if (!br_bits(&br, 1))
                br_bits(&br, pp->st_rps_bits);
            else if (pp->num_short_term_ref_pic_sets > 1)
                br_bits(&br, ceil_log2(pp->num_short_term_ref_pic_sets));
            size_t long_term_start = br_position(&br);
            if (parsing->long_term_ref_pics_present_flag) {
                unsigned from_sps = pp->num_long_term_ref_pic_sps ? br_ue(&br) : 0;
                unsigned pictures = br_ue(&br);
                for (unsigned i = 0; i < from_sps + pictures && !br.overrun; i++) {
                    if (i < from_sps) {
                        if (pp->num_long_term_ref_pic_sps > 1)
                            br_bits(&br, ceil_log2(pp->num_long_term_ref_pic_sps));
                    } else {
                        br_bits(&br, pp->log2_max_pic_order_cnt_lsb_minus4 + 4);
                        br_bits(&br, 1);
                    }
                    if (br_bits(&br, 1))
                        br_ue(&br);
                }
            }
            sh->long_term_bits = br_position(&br) - long_term_start;
            if (parsing->sps_temporal_mvp_enabled_flag)
                temporal_mvp = br_bits(&br, 1);
        }
        if (parsing->sample_adaptive_offset_enabled_flag) {
            sao = br_bits(&br, 1);
            if (chroma)
                sao |= br_bits(&br, 1);
        }
        if (slice_type == SLICE_P || slice_type == SLICE_B) {
            unsigned l0 = sp->num_ref_idx_l0_active_minus1 + 1;
            unsigned l1 = sp->num_ref_idx_l1_active_minus1 + 1;
            if (br_bits(&br, 1)) {
                br_ue(&br);
                if (slice_type == SLICE_B)
                    br_ue(&br);
            }
            unsigned total = pictures_in_current_sets(pp);
            if (parsing->lists_modification_present_flag && total > 1) {
                skip_list_modification(&br, l0, ceil_log2(total));
                if (slice_type == SLICE_B)
                    skip_list_modification(&br, l1, ceil_log2(total));
            }
            if (slice_type == SLICE_B)
                br_bits(&br, 1);
            if (parsing->cabac_init_present_flag)
                br_bits(&br, 1);
            if (temporal_mvp) {
                bool from_l0 = slice_type != SLICE_B || br_bits(&br, 1);
                if ((from_l0 && l0 > 1) || (!from_l0 && l1 > 1)) {
                    sh->collocated_present = true;
                    sh->collocated_ref_idx = br_ue(&br);
                }
            }
            if ((fields->weighted_pred_flag && slice_type == SLICE_P) ||
                (fields->weighted_bipred_flag && slice_type == SLICE_B)) {
                br_ue(&br);
                if (chroma)
                    br_se(&br);
                skip_weights(&br, l0, chroma);
                if (slice_type == SLICE_B)
                    skip_weights(&br, l1, chroma);
            }
            br_ue(&br);
        }
        br_se(&br);
        if (parsing->pps_slice_chroma_qp_offsets_present_flag) {
            br_se(&br);
            br_se(&br);
        }
        bool deblocking_disabled = parsing->pps_disable_deblocking_filter_flag;
        if (parsing->deblocking_filter_override_enabled_flag && br_bits(&br, 1)) {
            deblocking_disabled = br_bits(&br, 1);
            if (!deblocking_disabled) {
                br_se(&br);
                br_se(&br);
            }
        }
        if (fields->pps_loop_filter_across_slices_enabled_flag && (sao || !deblocking_disabled))
            br_bits(&br, 1);
    }
    if (fields->tiles_enabled_flag || fields->entropy_coding_sync_enabled_flag) {
        sh->num_entry_points = br_ue(&br);
        if (sh->num_entry_points > MAX_ENTRY_POINTS)
            return false;
        unsigned bits = sh->num_entry_points ? br_ue(&br) + 1 : 0;
        for (unsigned i = 0; i < sh->num_entry_points; i++)
            entry_points[i] = br_bits(&br, bits) + 1;
    }
    return !br.overrun;
}

static void fill_sps(struct v4l2_ctrl_hevc_sps *sps, const VAPictureParameterBufferHEVC *pp)
{
    const typeof(pp->pic_fields.bits) *f = &pp->pic_fields.bits;
    const typeof(pp->slice_parsing_fields.bits) *p = &pp->slice_parsing_fields.bits;
    *sps = (struct v4l2_ctrl_hevc_sps){
        .pic_width_in_luma_samples = pp->pic_width_in_luma_samples,
        .pic_height_in_luma_samples = pp->pic_height_in_luma_samples,
        .bit_depth_luma_minus8 = pp->bit_depth_luma_minus8,
        .bit_depth_chroma_minus8 = pp->bit_depth_chroma_minus8,
        .log2_max_pic_order_cnt_lsb_minus4 = pp->log2_max_pic_order_cnt_lsb_minus4,
        .sps_max_dec_pic_buffering_minus1 = pp->sps_max_dec_pic_buffering_minus1,
        .log2_min_luma_coding_block_size_minus3 = pp->log2_min_luma_coding_block_size_minus3,
        .log2_diff_max_min_luma_coding_block_size = pp->log2_diff_max_min_luma_coding_block_size,
        .log2_min_luma_transform_block_size_minus2 = pp->log2_min_transform_block_size_minus2,
        .log2_diff_max_min_luma_transform_block_size = pp->log2_diff_max_min_transform_block_size,
        .max_transform_hierarchy_depth_inter = pp->max_transform_hierarchy_depth_inter,
        .max_transform_hierarchy_depth_intra = pp->max_transform_hierarchy_depth_intra,
        .pcm_sample_bit_depth_luma_minus1 = pp->pcm_sample_bit_depth_luma_minus1,
        .pcm_sample_bit_depth_chroma_minus1 = pp->pcm_sample_bit_depth_chroma_minus1,
        .log2_min_pcm_luma_coding_block_size_minus3 = pp->log2_min_pcm_luma_coding_block_size_minus3,
        .log2_diff_max_min_pcm_luma_coding_block_size =
            pp->log2_diff_max_min_pcm_luma_coding_block_size,
        .num_short_term_ref_pic_sets = pp->num_short_term_ref_pic_sets,
        .num_long_term_ref_pics_sps = pp->num_long_term_ref_pic_sps,
        .chroma_format_idc = f->chroma_format_idc,
    };
    const struct {
        bool set;
        uint64_t flag;
    } flags[] = {
        { f->separate_colour_plane_flag, V4L2_HEVC_SPS_FLAG_SEPARATE_COLOUR_PLANE },
        { f->scaling_list_enabled_flag, V4L2_HEVC_SPS_FLAG_SCALING_LIST_ENABLED },
        { f->amp_enabled_flag, V4L2_HEVC_SPS_FLAG_AMP_ENABLED },
        { p->sample_adaptive_offset_enabled_flag, V4L2_HEVC_SPS_FLAG_SAMPLE_ADAPTIVE_OFFSET },
        { f->pcm_enabled_flag, V4L2_HEVC_SPS_FLAG_PCM_ENABLED },
        { f->pcm_loop_filter_disabled_flag, V4L2_HEVC_SPS_FLAG_PCM_LOOP_FILTER_DISABLED },
        { p->long_term_ref_pics_present_flag, V4L2_HEVC_SPS_FLAG_LONG_TERM_REF_PICS_PRESENT },
        { p->sps_temporal_mvp_enabled_flag, V4L2_HEVC_SPS_FLAG_SPS_TEMPORAL_MVP_ENABLED },
        { f->strong_intra_smoothing_enabled_flag,
          V4L2_HEVC_SPS_FLAG_STRONG_INTRA_SMOOTHING_ENABLED },
    };
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); i++)
        if (flags[i].set)
            sps->flags |= flags[i].flag;
}

static void fill_pps(struct v4l2_ctrl_hevc_pps *pps, const VAPictureParameterBufferHEVC *pp)
{
    const typeof(pp->pic_fields.bits) *f = &pp->pic_fields.bits;
    const typeof(pp->slice_parsing_fields.bits) *p = &pp->slice_parsing_fields.bits;
    *pps = (struct v4l2_ctrl_hevc_pps){
        .num_extra_slice_header_bits = pp->num_extra_slice_header_bits,
        .num_ref_idx_l0_default_active_minus1 = pp->num_ref_idx_l0_default_active_minus1,
        .num_ref_idx_l1_default_active_minus1 = pp->num_ref_idx_l1_default_active_minus1,
        .init_qp_minus26 = pp->init_qp_minus26,
        .diff_cu_qp_delta_depth = pp->diff_cu_qp_delta_depth,
        .pps_cb_qp_offset = pp->pps_cb_qp_offset,
        .pps_cr_qp_offset = pp->pps_cr_qp_offset,
        .num_tile_columns_minus1 = pp->num_tile_columns_minus1,
        .num_tile_rows_minus1 = pp->num_tile_rows_minus1,
        .pps_beta_offset_div2 = pp->pps_beta_offset_div2,
        .pps_tc_offset_div2 = pp->pps_tc_offset_div2,
        .log2_parallel_merge_level_minus2 = pp->log2_parallel_merge_level_minus2,
        /* present always: with the override off and offsets 0 it reads as absent */
        .flags = V4L2_HEVC_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT,
    };
    for (unsigned i = 0; i < pp->num_tile_columns_minus1 && i < 19; i++)
        pps->column_width_minus1[i] = pp->column_width_minus1[i];
    for (unsigned i = 0; i < pp->num_tile_rows_minus1 && i < 21; i++)
        pps->row_height_minus1[i] = pp->row_height_minus1[i];
    const struct {
        bool set;
        uint64_t flag;
    } flags[] = {
        { p->dependent_slice_segments_enabled_flag, V4L2_HEVC_PPS_FLAG_DEPENDENT_SLICE_SEGMENT_ENABLED },
        { p->output_flag_present_flag, V4L2_HEVC_PPS_FLAG_OUTPUT_FLAG_PRESENT },
        { f->sign_data_hiding_enabled_flag, V4L2_HEVC_PPS_FLAG_SIGN_DATA_HIDING_ENABLED },
        { p->cabac_init_present_flag, V4L2_HEVC_PPS_FLAG_CABAC_INIT_PRESENT },
        { f->constrained_intra_pred_flag, V4L2_HEVC_PPS_FLAG_CONSTRAINED_INTRA_PRED },
        { f->transform_skip_enabled_flag, V4L2_HEVC_PPS_FLAG_TRANSFORM_SKIP_ENABLED },
        { f->cu_qp_delta_enabled_flag, V4L2_HEVC_PPS_FLAG_CU_QP_DELTA_ENABLED },
        { p->pps_slice_chroma_qp_offsets_present_flag,
          V4L2_HEVC_PPS_FLAG_PPS_SLICE_CHROMA_QP_OFFSETS_PRESENT },
        { f->weighted_pred_flag, V4L2_HEVC_PPS_FLAG_WEIGHTED_PRED },
        { f->weighted_bipred_flag, V4L2_HEVC_PPS_FLAG_WEIGHTED_BIPRED },
        { f->transquant_bypass_enabled_flag, V4L2_HEVC_PPS_FLAG_TRANSQUANT_BYPASS_ENABLED },
        { f->tiles_enabled_flag, V4L2_HEVC_PPS_FLAG_TILES_ENABLED },
        { f->entropy_coding_sync_enabled_flag, V4L2_HEVC_PPS_FLAG_ENTROPY_CODING_SYNC_ENABLED },
        { f->loop_filter_across_tiles_enabled_flag,
          V4L2_HEVC_PPS_FLAG_LOOP_FILTER_ACROSS_TILES_ENABLED },
        { f->pps_loop_filter_across_slices_enabled_flag,
          V4L2_HEVC_PPS_FLAG_PPS_LOOP_FILTER_ACROSS_SLICES_ENABLED },
        { p->deblocking_filter_override_enabled_flag,
          V4L2_HEVC_PPS_FLAG_DEBLOCKING_FILTER_OVERRIDE_ENABLED },
        { p->pps_disable_deblocking_filter_flag, V4L2_HEVC_PPS_FLAG_PPS_DISABLE_DEBLOCKING_FILTER },
        { p->lists_modification_present_flag, V4L2_HEVC_PPS_FLAG_LISTS_MODIFICATION_PRESENT },
        { p->slice_segment_header_extension_present_flag,
          V4L2_HEVC_PPS_FLAG_SLICE_SEGMENT_HEADER_EXTENSION_PRESENT },
    };
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); i++)
        if (flags[i].set)
            pps->flags |= flags[i].flag;
}

static void fill_scaling(struct v4l2_ctrl_hevc_scaling_matrix *m, const VAIQMatrixBufferHEVC *iq)
{
    /* both in raster order */
    memcpy(m->scaling_list_4x4, iq->ScalingList4x4, sizeof(m->scaling_list_4x4));
    memcpy(m->scaling_list_8x8, iq->ScalingList8x8, sizeof(m->scaling_list_8x8));
    memcpy(m->scaling_list_16x16, iq->ScalingList16x16, sizeof(m->scaling_list_16x16));
    memcpy(m->scaling_list_32x32, iq->ScalingList32x32, sizeof(m->scaling_list_32x32));
    memcpy(m->scaling_list_dc_coef_16x16, iq->ScalingListDC16x16, sizeof(iq->ScalingListDC16x16));
    memcpy(m->scaling_list_dc_coef_32x32, iq->ScalingListDC32x32, sizeof(iq->ScalingListDC32x32));
}

/* entries of one set, by POC: before descending, after ascending, as the RPS lists them */
static unsigned collect_set(const VAPictureParameterBufferHEVC *pp, uint32_t flag, bool descending,
                            uint8_t *indices)
{
    unsigned count = 0;
    for (unsigned i = 0; i < 15; i++) {
        if (!(pp->ReferenceFrames[i].flags & flag))
            continue;
        unsigned at = count++;
        int poc = pp->ReferenceFrames[i].pic_order_cnt;
        while (at && (descending ? pp->ReferenceFrames[indices[at - 1]].pic_order_cnt < poc
                                 : pp->ReferenceFrames[indices[at - 1]].pic_order_cnt > poc)) {
            indices[at] = indices[at - 1];
            at--;
        }
        indices[at] = i;
    }
    return count;
}

static void fill_decode_params(const struct request_ctx *rq,
                               struct v4l2_ctrl_hevc_decode_params *dp,
                               const VAPictureParameterBufferHEVC *pp, const struct slice_header *sh)
{
    *dp = (struct v4l2_ctrl_hevc_decode_params){
        .pic_order_cnt_val = pp->CurrPic.pic_order_cnt,
        .short_term_ref_pic_set_size = pp->st_rps_bits,
        .long_term_ref_pic_set_size = sh->long_term_bits,
    };
    for (unsigned i = 0; i < 15; i++) {
        const VAPictureHEVC *ref = &pp->ReferenceFrames[i];
        if (ref->picture_id == VA_INVALID_SURFACE || ref->flags & VA_PICTURE_HEVC_INVALID)
            continue;
        dp->dpb[i] = (struct v4l2_hevc_dpb_entry){
            .timestamp = request_timestamp(rq, ref->picture_id),
            .flags = ref->flags & VA_PICTURE_HEVC_LONG_TERM_REFERENCE
                         ? V4L2_HEVC_DPB_ENTRY_LONG_TERM_REFERENCE
                         : 0,
            .pic_order_cnt_val = ref->pic_order_cnt,
        };
        dp->num_active_dpb_entries = i + 1;
    }
    dp->num_poc_st_curr_before =
        collect_set(pp, VA_PICTURE_HEVC_RPS_ST_CURR_BEFORE, true, dp->poc_st_curr_before);
    dp->num_poc_st_curr_after =
        collect_set(pp, VA_PICTURE_HEVC_RPS_ST_CURR_AFTER, false, dp->poc_st_curr_after);
    dp->num_poc_lt_curr = collect_set(pp, VA_PICTURE_HEVC_RPS_LT_CURR, false, dp->poc_lt_curr);
    if (is_irap(sh->nal_unit_type))
        dp->flags |= V4L2_HEVC_DECODE_PARAM_FLAG_IRAP_PIC;
    if (is_idr(sh->nal_unit_type))
        dp->flags |= V4L2_HEVC_DECODE_PARAM_FLAG_IDR_PIC;
    if (sh->no_output_of_prior_pics)
        dp->flags |= V4L2_HEVC_DECODE_PARAM_FLAG_NO_OUTPUT_OF_PRIOR;
}

static void fill_slice_params(struct v4l2_ctrl_hevc_slice_params *slice,
                              const VAPictureParameterBufferHEVC *pp,
                              const VASliceParameterBufferHEVC *sp, const struct slice_header *sh,
                              size_t bytes, size_t data_offset)
{
    const typeof(sp->LongSliceFlags.fields) *f = &sp->LongSliceFlags.fields;
    *slice = (struct v4l2_ctrl_hevc_slice_params){
        .bit_size = bytes * 8,
        .data_byte_offset = data_offset,
        .num_entry_point_offsets = sh->num_entry_points,
        .nal_unit_type = sh->nal_unit_type,
        .nuh_temporal_id_plus1 = sh->temporal_id_plus1,
        .slice_type = f->slice_type,
        .colour_plane_id = f->color_plane_id,
        .slice_pic_order_cnt = pp->CurrPic.pic_order_cnt,
        .num_ref_idx_l0_active_minus1 = sp->num_ref_idx_l0_active_minus1,
        .num_ref_idx_l1_active_minus1 = sp->num_ref_idx_l1_active_minus1,
        .collocated_ref_idx = sp->collocated_ref_idx,
        .five_minus_max_num_merge_cand = sp->five_minus_max_num_merge_cand,
        .slice_qp_delta = sp->slice_qp_delta,
        .slice_cb_qp_offset = sp->slice_cb_qp_offset,
        .slice_cr_qp_offset = sp->slice_cr_qp_offset,
        .slice_beta_offset_div2 = sp->slice_beta_offset_div2,
        .slice_tc_offset_div2 = sp->slice_tc_offset_div2,
        .pic_struct = V4L2_HEVC_SEI_PIC_STRUCT_FRAME,
        .slice_segment_addr = sp->slice_segment_address,
        .short_term_ref_pic_set_size = pp->st_rps_bits,
        .long_term_ref_pic_set_size = sh->long_term_bits,
    };
    /* VA's lists index its reference frames, which are the DPB in the same order */
    memcpy(slice->ref_idx_l0, sp->RefPicList[0], sizeof(sp->RefPicList[0]));
    memcpy(slice->ref_idx_l1, sp->RefPicList[1], sizeof(sp->RefPicList[1]));
    struct v4l2_hevc_pred_weight_table *w = &slice->pred_weight_table;
    w->luma_log2_weight_denom = sp->luma_log2_weight_denom;
    w->delta_chroma_log2_weight_denom = sp->delta_chroma_log2_weight_denom;
    memcpy(w->delta_luma_weight_l0, sp->delta_luma_weight_l0, sizeof(sp->delta_luma_weight_l0));
    memcpy(w->luma_offset_l0, sp->luma_offset_l0, sizeof(sp->luma_offset_l0));
    memcpy(w->delta_chroma_weight_l0, sp->delta_chroma_weight_l0, sizeof(sp->delta_chroma_weight_l0));
    memcpy(w->chroma_offset_l0, sp->ChromaOffsetL0, sizeof(sp->ChromaOffsetL0));
    memcpy(w->delta_luma_weight_l1, sp->delta_luma_weight_l1, sizeof(sp->delta_luma_weight_l1));
    memcpy(w->luma_offset_l1, sp->luma_offset_l1, sizeof(sp->luma_offset_l1));
    memcpy(w->delta_chroma_weight_l1, sp->delta_chroma_weight_l1, sizeof(sp->delta_chroma_weight_l1));
    memcpy(w->chroma_offset_l1, sp->ChromaOffsetL1, sizeof(sp->ChromaOffsetL1));
    const struct {
        bool set;
        uint64_t flag;
    } flags[] = {
        { f->slice_sao_luma_flag, V4L2_HEVC_SLICE_PARAMS_FLAG_SLICE_SAO_LUMA },
        { f->slice_sao_chroma_flag, V4L2_HEVC_SLICE_PARAMS_FLAG_SLICE_SAO_CHROMA },
        { f->slice_temporal_mvp_enabled_flag, V4L2_HEVC_SLICE_PARAMS_FLAG_SLICE_TEMPORAL_MVP_ENABLED },
        { f->mvd_l1_zero_flag, V4L2_HEVC_SLICE_PARAMS_FLAG_MVD_L1_ZERO },
        { f->cabac_init_flag, V4L2_HEVC_SLICE_PARAMS_FLAG_CABAC_INIT },
        { f->collocated_from_l0_flag, V4L2_HEVC_SLICE_PARAMS_FLAG_COLLOCATED_FROM_L0 },
        { f->slice_deblocking_filter_disabled_flag,
          V4L2_HEVC_SLICE_PARAMS_FLAG_SLICE_DEBLOCKING_FILTER_DISABLED },
        { f->slice_loop_filter_across_slices_enabled_flag,
          V4L2_HEVC_SLICE_PARAMS_FLAG_SLICE_LOOP_FILTER_ACROSS_SLICES_ENABLED },
        { f->dependent_slice_segment_flag, V4L2_HEVC_SLICE_PARAMS_FLAG_DEPENDENT_SLICE_SEGMENT },
    };
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); i++)
        if (flags[i].set)
            slice->flags |= flags[i].flag;
}

static void dump_slice(struct request_ctx *rq, const struct slice_header *sh,
                       const struct v4l2_ctrl_hevc_slice_params *slice)
{
    if (!sh->first_slice)
        request_dump(rq, "slice_segment_address", sh->segment_address);
    if (!is_idr(sh->nal_unit_type))
        request_dump(rq, "slice_pic_order_cnt_lsb", sh->pic_order_cnt_lsb);
    if (sh->collocated_present)
        request_dump(rq, "collocated_ref_idx", slice->collocated_ref_idx);
    request_dump(rq, "slice_qp_delta", slice->slice_qp_delta);
    request_dump(rq, "num_entry_point_offsets", slice->num_entry_point_offsets);
}

static void dump_entry_points(struct request_ctx *rq, const uint32_t *offsets, unsigned count)
{
    for (unsigned i = 0; i < count; i++)
        request_dump(rq, "entry_point_offset_minus1", offsets[i] - 1);
}

static int hevc_init(struct request_ctx *rq)
{
    struct hevc_state *st = rq->codec_state;
    if (request_get_control(rq, V4L2_CID_STATELESS_HEVC_DECODE_MODE, &st->decode_mode) < 0)
        st->decode_mode = V4L2_STATELESS_HEVC_DECODE_MODE_SLICE_BASED;
    if (request_get_control(rq, V4L2_CID_STATELESS_HEVC_START_CODE, &st->start_code) < 0)
        st->start_code = V4L2_STATELESS_HEVC_START_CODE_NONE;
    /* one request a slice: the frame-based engines take a slice array this does not build */
    return st->decode_mode == V4L2_STATELESS_HEVC_DECODE_MODE_SLICE_BASED ? 0 : -ENOTSUP;
}

static int hevc_submit(struct request_ctx *rq, const struct picture *pic)
{
    struct hevc_state *st = rq->codec_state;
    const VAPictureParameterBufferHEVC *pp = pic->picture_param;
    struct v4l2_ctrl_hevc_sps sps;
    struct v4l2_ctrl_hevc_pps pps;
    struct v4l2_ctrl_hevc_scaling_matrix scaling = { 0 };
    struct v4l2_ctrl_hevc_decode_params decode;
    struct v4l2_ctrl_hevc_slice_params slice;
    struct annexb data = { 0 };
    uint8_t rbsp[MAX_HEADER_BYTES];
    int ret = 0;

    if (!pp || !pic->num_slices)
        return -EINVAL;
    fill_sps(&sps, pp);
    fill_pps(&pps, pp);
    if (pic->iq_matrix)
        fill_scaling(&scaling, pic->iq_matrix);
    request_dump(rq, "log2_max_pic_order_cnt_lsb_minus4", sps.log2_max_pic_order_cnt_lsb_minus4);
    request_dump(rq, "num_short_term_ref_pic_sets", sps.num_short_term_ref_pic_sets);
    request_dump(rq, "init_qp_minus26", pps.init_qp_minus26);
    for (unsigned i = 0; i < pic->num_slices && !ret; i++) {
        const struct slice *s = &pic->slices[i];
        const VASliceParameterBufferHEVC *sp = s->param;
        struct slice_header sh;
        size_t header = sp ? sp->slice_data_byte_offset : 0;
        size_t raw_offset = header > NAL_HEADER_SIZE && header <= MAX_HEADER_BYTES
                                ? unescape_prefix(s->data, s->size, rbsp, header)
                                : 0;
        if (!raw_offset || !parse_slice_header(pp, sp, rbsp, header, &sh, st->entry_points))
            return -EINVAL;
        bool annex_b = st->start_code == V4L2_STATELESS_HEVC_START_CODE_ANNEX_B;
        size_t prefix = annex_b ? sizeof(start_code) : 0;
        fill_decode_params(rq, &decode, pp, &sh);
        fill_slice_params(&slice, pp, sp, &sh, s->size + prefix, raw_offset + prefix);
        dump_slice(rq, &sh, &slice);
        dump_entry_points(rq, st->entry_points, sh.num_entry_points);
        data.size = 0;
        if ((annex_b && (ret = annexb_append_raw(&data, start_code, sizeof(start_code)))) ||
            (ret = annexb_append_raw(&data, s->data, s->size)))
            break;
        struct v4l2_ext_control controls[NUM_CONTROLS] = {
            { .id = V4L2_CID_STATELESS_HEVC_SPS, .size = sizeof(sps), .ptr = &sps },
            { .id = V4L2_CID_STATELESS_HEVC_PPS, .size = sizeof(pps), .ptr = &pps },
            { .id = V4L2_CID_STATELESS_HEVC_SCALING_MATRIX, .size = sizeof(scaling),
              .ptr = &scaling },
            { .id = V4L2_CID_STATELESS_HEVC_DECODE_PARAMS, .size = sizeof(decode), .ptr = &decode },
            { .id = V4L2_CID_STATELESS_HEVC_SLICE_PARAMS, .size = sizeof(slice), .ptr = &slice },
            { .id = V4L2_CID_STATELESS_HEVC_ENTRY_POINT_OFFSETS,
              .size = sh.num_entry_points * sizeof(uint32_t), .ptr = st->entry_points },
        };
        unsigned count = sh.num_entry_points ? NUM_CONTROLS : NUM_CONTROLS - 1;
        ret = request_queue(rq, controls, count, &data, !i, i + 1 == pic->num_slices);
    }
    annexb_free(&data);
    return ret;
}

const struct request_codec request_hevc = {
    .kind = CODEC_HEVC,
    .pixelformat = V4L2_PIX_FMT_HEVC_SLICE,
    .state_size = sizeof(struct hevc_state),
    .init = hevc_init,
    .submit = hevc_submit,
};
