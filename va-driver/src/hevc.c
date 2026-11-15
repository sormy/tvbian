/*
 * HEVC: VPS, SPS and PPS rebuilt from VA's picture parameters. VA leaves out the SPS's
 * short-term reference picture sets, so each slice that names one gets its header rewritten
 * with the set inline, rebuilt from the reference frames VA lists.
 */
#include <errno.h>
#include <string.h>

#include "driver.h"

enum {
    NAL_IDR_W_RADL = 19,
    NAL_IDR_N_LP = 20,
    NAL_BLA_W_LP = 16,
    NAL_IRAP_LAST = 23,
    NAL_VPS = 32,
    NAL_SPS = 33,
    NAL_PPS = 34,
    NAL_HEADER_SIZE = 2,
    NAL_TEMPORAL_ID_PLUS1 = 1,
};

enum {
    PROFILE_MAIN = 1,
    PROFILE_MAIN10 = 2,
    LEVEL_5_1 = 153,
    LEVEL_6_2 = 186,
    LEVEL_5_1_MAX_SAMPLES = 4096 * 2304,
    PTL_RESERVED_ZERO_BITS = 43,
    CHROMA_444 = 3,
    MAX_PPS = 64,
    MAX_HEADER_BYTES = 1024,
    SCALING_SIZES = 4,
    SCALING_MATRICES = 6,
    SCALING_LIST_START = 8,
    SIZE_32X32 = 3,
};

/* What was last sent: a parameter set goes out again only when it changed, or on an IRAP. */
struct hevc_state {
    struct bit_writer sent_vps;
    struct bit_writer sent_sps;
    struct bit_writer sent_pps;
    int sent_pps_id;
};

static unsigned ceil_log2(unsigned value)
{
    unsigned bits = 0;
    while ((1u << bits) < value)
        bits++;
    return bits;
}

static void nal_header(uint8_t header[NAL_HEADER_SIZE], unsigned type)
{
    header[0] = type << 1;
    header[1] = NAL_TEMPORAL_ID_PLUS1;
}

static void write_profile_tier_level(struct bit_writer *bw, const VAPictureParameterBufferHEVC *pp)
{
    unsigned profile = pp->bit_depth_luma_minus8 ? PROFILE_MAIN10 : PROFILE_MAIN;
    unsigned samples = (unsigned)pp->pic_width_in_luma_samples * pp->pic_height_in_luma_samples;

    bw_bits(bw, 2, 0);
    bw_flag(bw, 0);
    bw_bits(bw, 5, profile);
    /* Main is also Main 10 compatible */
    for (unsigned j = 0; j < 32; j++)
        bw_flag(bw, j == profile || (profile == PROFILE_MAIN && j == PROFILE_MAIN10));
    bw_flag(bw, 1);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_flag(bw, 1);
    bw_bits(bw, PTL_RESERVED_ZERO_BITS, 0);
    bw_flag(bw, 0);
    bw_bits(bw, 8, samples <= LEVEL_5_1_MAX_SAMPLES ? LEVEL_5_1 : LEVEL_6_2);
}

static void write_vps(struct bit_writer *bw, const VAPictureParameterBufferHEVC *pp)
{
    bw_init(bw);
    bw_bits(bw, 4, 0);
    bw_flag(bw, 1);
    bw_flag(bw, 1);
    bw_bits(bw, 6, 0);
    bw_bits(bw, 3, 0);
    bw_flag(bw, 1);
    bw_bits(bw, 16, 0xffff);
    write_profile_tier_level(bw, pp);
    bw_flag(bw, 1);
    bw_ue(bw, pp->sps_max_dec_pic_buffering_minus1);
    bw_ue(bw, 0);
    bw_ue(bw, 0);
    bw_bits(bw, 6, 0);
    bw_ue(bw, 0);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_trailing(bw);
}

/* VA's lists are in raster order; the bitstream's in up-right diagonal order */
static void diagonal_scan(unsigned size, uint8_t *raster_of)
{
    unsigned i = 0;
    for (unsigned line = 0; i < size * size; line++)
        for (int y = line, x = 0; y >= 0; y--, x++)
            if ((unsigned)x < size && (unsigned)y < size)
                raster_of[i++] = y * size + x;
}

static void write_scaling_list(struct bit_writer *bw, const uint8_t *raster, unsigned size,
                               int dc)
{
    uint8_t raster_of[64];
    int last = SCALING_LIST_START;
    diagonal_scan(size, raster_of);
    if (dc >= 0) {
        bw_se(bw, dc - SCALING_LIST_START);
        last = dc;
    }
    for (unsigned i = 0; i < size * size; i++) {
        int delta = raster[raster_of[i]] - last;
        delta = delta > INT8_MAX ? delta - 256 : delta < INT8_MIN ? delta + 256 : delta;
        bw_se(bw, delta);
        last = raster[raster_of[i]];
    }
}

static void write_scaling_list_data(struct bit_writer *bw, const VAIQMatrixBufferHEVC *iq)
{
    for (unsigned size_id = 0; size_id < SCALING_SIZES; size_id++) {
        for (unsigned matrix = 0; matrix < SCALING_MATRICES; matrix += size_id == SIZE_32X32 ? 3 : 1) {
            bw_flag(bw, 1);
            switch (size_id) {
            case 0:
                write_scaling_list(bw, iq->ScalingList4x4[matrix], 4, -1);
                break;
            case 1:
                write_scaling_list(bw, iq->ScalingList8x8[matrix], 8, -1);
                break;
            case 2:
                write_scaling_list(bw, iq->ScalingList16x16[matrix], 8,
                                   iq->ScalingListDC16x16[matrix]);
                break;
            default:
                write_scaling_list(bw, iq->ScalingList32x32[matrix / 3], 8,
                                   iq->ScalingListDC32x32[matrix / 3]);
                break;
            }
        }
    }
}

static void write_sps(struct bit_writer *bw, const VAPictureParameterBufferHEVC *pp,
                      const VAIQMatrixBufferHEVC *iq)
{
    bw_init(bw);
    bw_bits(bw, 4, 0);
    bw_bits(bw, 3, 0);
    bw_flag(bw, 1);
    write_profile_tier_level(bw, pp);
    bw_ue(bw, 0);
    bw_ue(bw, pp->pic_fields.bits.chroma_format_idc);
    if (pp->pic_fields.bits.chroma_format_idc == CHROMA_444)
        bw_flag(bw, pp->pic_fields.bits.separate_colour_plane_flag);
    bw_ue(bw, pp->pic_width_in_luma_samples);
    bw_ue(bw, pp->pic_height_in_luma_samples);
    bw_flag(bw, 0);
    bw_ue(bw, pp->bit_depth_luma_minus8);
    bw_ue(bw, pp->bit_depth_chroma_minus8);
    bw_ue(bw, pp->log2_max_pic_order_cnt_lsb_minus4);
    /* a reorder depth of 0: each picture out once decoded */
    bw_flag(bw, 1);
    bw_ue(bw, pp->sps_max_dec_pic_buffering_minus1);
    bw_ue(bw, 0);
    bw_ue(bw, 0);
    bw_ue(bw, pp->log2_min_luma_coding_block_size_minus3);
    bw_ue(bw, pp->log2_diff_max_min_luma_coding_block_size);
    bw_ue(bw, pp->log2_min_transform_block_size_minus2);
    bw_ue(bw, pp->log2_diff_max_min_transform_block_size);
    bw_ue(bw, pp->max_transform_hierarchy_depth_inter);
    bw_ue(bw, pp->max_transform_hierarchy_depth_intra);
    bw_flag(bw, pp->pic_fields.bits.scaling_list_enabled_flag);
    if (pp->pic_fields.bits.scaling_list_enabled_flag) {
        bw_flag(bw, iq != NULL);
        if (iq)
            write_scaling_list_data(bw, iq);
    }
    bw_flag(bw, pp->pic_fields.bits.amp_enabled_flag);
    bw_flag(bw, pp->slice_parsing_fields.bits.sample_adaptive_offset_enabled_flag);
    bw_flag(bw, pp->pic_fields.bits.pcm_enabled_flag);
    if (pp->pic_fields.bits.pcm_enabled_flag) {
        bw_bits(bw, 4, pp->pcm_sample_bit_depth_luma_minus1);
        bw_bits(bw, 4, pp->pcm_sample_bit_depth_chroma_minus1);
        bw_ue(bw, pp->log2_min_pcm_luma_coding_block_size_minus3);
        bw_ue(bw, pp->log2_diff_max_min_pcm_luma_coding_block_size);
        bw_flag(bw, pp->pic_fields.bits.pcm_loop_filter_disabled_flag);
    }
    /* the sets go inline in each slice */
    bw_ue(bw, 0);
    bw_flag(bw, pp->slice_parsing_fields.bits.long_term_ref_pics_present_flag);
    if (pp->slice_parsing_fields.bits.long_term_ref_pics_present_flag)
        bw_ue(bw, 0);
    bw_flag(bw, pp->slice_parsing_fields.bits.sps_temporal_mvp_enabled_flag);
    bw_flag(bw, pp->pic_fields.bits.strong_intra_smoothing_enabled_flag);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_trailing(bw);
}

static void write_pps(struct bit_writer *bw, unsigned pps_id, const VAPictureParameterBufferHEVC *pp)
{
    bw_init(bw);
    bw_ue(bw, pps_id);
    bw_ue(bw, 0);
    bw_flag(bw, pp->slice_parsing_fields.bits.dependent_slice_segments_enabled_flag);
    bw_flag(bw, pp->slice_parsing_fields.bits.output_flag_present_flag);
    bw_bits(bw, 3, pp->num_extra_slice_header_bits);
    bw_flag(bw, pp->pic_fields.bits.sign_data_hiding_enabled_flag);
    bw_flag(bw, pp->slice_parsing_fields.bits.cabac_init_present_flag);
    bw_ue(bw, pp->num_ref_idx_l0_default_active_minus1);
    bw_ue(bw, pp->num_ref_idx_l1_default_active_minus1);
    bw_se(bw, pp->init_qp_minus26);
    bw_flag(bw, pp->pic_fields.bits.constrained_intra_pred_flag);
    bw_flag(bw, pp->pic_fields.bits.transform_skip_enabled_flag);
    bw_flag(bw, pp->pic_fields.bits.cu_qp_delta_enabled_flag);
    if (pp->pic_fields.bits.cu_qp_delta_enabled_flag)
        bw_ue(bw, pp->diff_cu_qp_delta_depth);
    bw_se(bw, pp->pps_cb_qp_offset);
    bw_se(bw, pp->pps_cr_qp_offset);
    bw_flag(bw, pp->slice_parsing_fields.bits.pps_slice_chroma_qp_offsets_present_flag);
    bw_flag(bw, pp->pic_fields.bits.weighted_pred_flag);
    bw_flag(bw, pp->pic_fields.bits.weighted_bipred_flag);
    bw_flag(bw, pp->pic_fields.bits.transquant_bypass_enabled_flag);
    bw_flag(bw, pp->pic_fields.bits.tiles_enabled_flag);
    bw_flag(bw, pp->pic_fields.bits.entropy_coding_sync_enabled_flag);
    if (pp->pic_fields.bits.tiles_enabled_flag) {
        bw_ue(bw, pp->num_tile_columns_minus1);
        bw_ue(bw, pp->num_tile_rows_minus1);
        bw_flag(bw, 0);
        for (unsigned i = 0; i < pp->num_tile_columns_minus1; i++)
            bw_ue(bw, pp->column_width_minus1[i]);
        for (unsigned i = 0; i < pp->num_tile_rows_minus1; i++)
            bw_ue(bw, pp->row_height_minus1[i]);
        bw_flag(bw, pp->pic_fields.bits.loop_filter_across_tiles_enabled_flag);
    }
    bw_flag(bw, pp->pic_fields.bits.pps_loop_filter_across_slices_enabled_flag);
    /* present always: with the override off and offsets 0 it reads as absent */
    bw_flag(bw, 1);
    bw_flag(bw, pp->slice_parsing_fields.bits.deblocking_filter_override_enabled_flag);
    bw_flag(bw, pp->slice_parsing_fields.bits.pps_disable_deblocking_filter_flag);
    if (!pp->slice_parsing_fields.bits.pps_disable_deblocking_filter_flag) {
        bw_se(bw, pp->pps_beta_offset_div2);
        bw_se(bw, pp->pps_tc_offset_div2);
    }
    bw_flag(bw, 0);
    bw_flag(bw, pp->slice_parsing_fields.bits.lists_modification_present_flag);
    bw_ue(bw, pp->log2_parallel_merge_level_minus2);
    bw_flag(bw, pp->slice_parsing_fields.bits.slice_segment_header_extension_present_flag);
    bw_flag(bw, 0);
    bw_trailing(bw);
}

/* the current picture's short-term set, from the short-term references VA lists */
static void write_st_ref_pic_set(struct bit_writer *bw, const VAPictureParameterBufferHEVC *pp)
{
    const VAPictureHEVC *before[15], *after[15];
    unsigned num_before = 0, num_after = 0;
    int current = pp->CurrPic.pic_order_cnt;

    for (unsigned i = 0; i < 15; i++) {
        const VAPictureHEVC *ref = &pp->ReferenceFrames[i];
        if (ref->picture_id == VA_INVALID_SURFACE || ref->flags & VA_PICTURE_HEVC_INVALID ||
            ref->flags & VA_PICTURE_HEVC_LONG_TERM_REFERENCE)
            continue;
        const VAPictureHEVC **side = ref->pic_order_cnt < current ? before : after;
        unsigned *count = ref->pic_order_cnt < current ? &num_before : &num_after;
        /* insertion: before descending, after ascending */
        unsigned at = *count;
        while (at && (side == before ? side[at - 1]->pic_order_cnt < ref->pic_order_cnt
                                     : side[at - 1]->pic_order_cnt > ref->pic_order_cnt)) {
            side[at] = side[at - 1];
            at--;
        }
        side[at] = ref;
        (*count)++;
    }
    bw_ue(bw, num_before);
    bw_ue(bw, num_after);
    int previous = current;
    for (unsigned i = 0; i < num_before; i++) {
        bw_ue(bw, previous - before[i]->pic_order_cnt - 1);
        bw_flag(bw, before[i]->flags & VA_PICTURE_HEVC_RPS_ST_CURR_BEFORE);
        previous = before[i]->pic_order_cnt;
    }
    previous = current;
    for (unsigned i = 0; i < num_after; i++) {
        bw_ue(bw, after[i]->pic_order_cnt - previous - 1);
        bw_flag(bw, after[i]->flags & VA_PICTURE_HEVC_RPS_ST_CURR_AFTER);
        previous = after[i]->pic_order_cnt;
    }
}

struct slice_header {
    unsigned nal_unit_type;
    unsigned pps_id;
    bool dependent;
    bool hidden;
    /* the bits a rewrite replaces: [rps_start, rps_end) */
    size_t rps_start;
    size_t rps_end;
};

static bool is_idr(unsigned nal_unit_type)
{
    return nal_unit_type == NAL_IDR_W_RADL || nal_unit_type == NAL_IDR_N_LP;
}

static bool is_irap(unsigned nal_unit_type)
{
    return nal_unit_type >= NAL_BLA_W_LP && nal_unit_type <= NAL_IRAP_LAST;
}

/* 7.3.6.1, as far as the short-term reference picture set */
static bool parse_slice_header(const VAPictureParameterBufferHEVC *pp, const uint8_t *rbsp,
                               size_t size, struct slice_header *sh)
{
    struct bit_reader br;
    unsigned ctb_log2 = pp->log2_min_luma_coding_block_size_minus3 + 3 +
                        pp->log2_diff_max_min_luma_coding_block_size;
    unsigned ctb = 1u << ctb_log2;
    unsigned ctbs = ((pp->pic_width_in_luma_samples + ctb - 1) >> ctb_log2) *
                    ((pp->pic_height_in_luma_samples + ctb - 1) >> ctb_log2);

    memset(sh, 0, sizeof(*sh));
    sh->nal_unit_type = (rbsp[0] >> 1) & 0x3f;
    br_init_unescaped(&br, rbsp + NAL_HEADER_SIZE, size - NAL_HEADER_SIZE);
    bool first_slice = br_bits(&br, 1);
    if (is_irap(sh->nal_unit_type))
        br_bits(&br, 1);
    sh->pps_id = br_ue(&br);
    if (!first_slice) {
        if (pp->slice_parsing_fields.bits.dependent_slice_segments_enabled_flag)
            sh->dependent = br_bits(&br, 1);
        br_bits(&br, ceil_log2(ctbs));
    }
    if (!sh->dependent) {
        br_bits(&br, pp->num_extra_slice_header_bits);
        br_ue(&br);
        if (pp->slice_parsing_fields.bits.output_flag_present_flag)
            sh->hidden = !br_bits(&br, 1);
        if (pp->pic_fields.bits.separate_colour_plane_flag)
            br_bits(&br, 2);
        if (!is_idr(sh->nal_unit_type)) {
            br_bits(&br, pp->log2_max_pic_order_cnt_lsb_minus4 + 4);
            sh->rps_start = br_position(&br);
            bool from_sps = br_bits(&br, 1);
            if (!from_sps)
                br_bits(&br, pp->st_rps_bits);
            else if (pp->num_short_term_ref_pic_sets > 1)
                br_bits(&br, ceil_log2(pp->num_short_term_ref_pic_sets));
            sh->rps_end = br_position(&br);
        }
    }
    return !br.overrun && sh->pps_id < MAX_PPS;
}

static size_t alignment_bit(const uint8_t *rbsp, size_t data_offset)
{
    uint8_t last = rbsp[data_offset - 1];
    unsigned zeros = 0;
    while (zeros < 8 && !(last & (1u << zeros)))
        zeros++;
    return (data_offset - 1) * 8 + 7 - zeros;
}

/* the header again with the set inline, then the slice data as it came */
static int rewrite_slice(const VAPictureParameterBufferHEVC *pp, const struct slice *s,
                         const uint8_t *rbsp, size_t data_offset, size_t raw_data_offset,
                         const struct slice_header *sh, struct annexb *out)
{
    size_t header_bits = NAL_HEADER_SIZE * 8;
    size_t end = alignment_bit(rbsp, data_offset);
    struct bit_writer bw;
    int ret;

    if (end < header_bits + sh->rps_end)
        return -EINVAL;
    bw_init(&bw);
    bw_copy_bits(&bw, rbsp + NAL_HEADER_SIZE, 0, sh->rps_start);
    bw_flag(&bw, 0);
    write_st_ref_pic_set(&bw, pp);
    bw_copy_bits(&bw, rbsp + NAL_HEADER_SIZE, sh->rps_end, end - header_bits);
    bw_trailing(&bw);
    if ((ret = annexb_append_rbsp(out, rbsp, NAL_HEADER_SIZE, &bw)))
        return ret;
    return annexb_append_raw(out, s->data + raw_data_offset, s->size - raw_data_offset);
}

static int append_parameter_set(struct annexb *out, unsigned type, const struct bit_writer *bw,
                                struct bit_writer *sent, bool force)
{
    uint8_t header[NAL_HEADER_SIZE];
    if (!force && sent->bits == bw->bits && !memcmp(sent->data, bw->data, bw_bytes(bw)))
        return 0;
    nal_header(header, type);
    *sent = *bw;
    return annexb_append_rbsp(out, header, NAL_HEADER_SIZE, bw);
}

static int hevc_build_packet(void *state, const struct picture *pic, struct annexb *out,
                             struct packet_info *info)
{
    struct hevc_state *st = state;
    const VAPictureParameterBufferHEVC *pp = pic->picture_param;
    struct slice_header first;
    uint8_t rbsp[MAX_HEADER_BYTES];
    struct bit_writer bw;
    int ret;

    if (!pp || !pic->num_slices || !pic->slices[0].param)
        return -EINVAL;
    /* VA carries no long-term sets of the SPS for a slice to name */
    if (pp->num_long_term_ref_pic_sps)
        return -ENOTSUP;

    for (unsigned i = 0; i < pic->num_slices; i++) {
        const struct slice *s = &pic->slices[i];
        const VASliceParameterBufferHEVC *sp = s->param;
        if (!sp)
            return -EINVAL;
        size_t data_offset = sp->slice_data_byte_offset;
        size_t raw_data_offset = data_offset > NAL_HEADER_SIZE && data_offset <= MAX_HEADER_BYTES
                                     ? unescape_prefix(s->data, s->size, rbsp, data_offset)
                                     : 0;
        struct slice_header sh;
        if (!raw_data_offset || !parse_slice_header(pp, rbsp, data_offset, &sh))
            return -EINVAL;
        if (!i) {
            first = sh;
            bool irap = is_irap(sh.nal_unit_type);
            write_vps(&bw, pp);
            if ((ret = append_parameter_set(out, NAL_VPS, &bw, &st->sent_vps, irap)))
                return ret;
            write_sps(&bw, pp, pic->iq_matrix);
            if ((ret = append_parameter_set(out, NAL_SPS, &bw, &st->sent_sps, irap)))
                return ret;
            write_pps(&bw, sh.pps_id, pp);
            if ((ret = append_parameter_set(out, NAL_PPS, &bw, &st->sent_pps,
                                            irap || st->sent_pps_id != (int)sh.pps_id)))
                return ret;
            st->sent_pps_id = sh.pps_id;
        }
        ret = sh.rps_end ? rewrite_slice(pp, s, rbsp, data_offset, raw_data_offset, &sh, out)
                         : annexb_append_nal(out, s->data, s->size);
        if (ret)
            return ret;
    }
    info->hidden = first.hidden;
    return 0;
}

static void hevc_restart(void *state)
{
    struct hevc_state *st = state;
    st->sent_vps.bits = st->sent_sps.bits = st->sent_pps.bits = 0;
    st->sent_pps_id = -1;
}

const struct codec codec_hevc = {
    .kind = CODEC_HEVC,
    .state_size = sizeof(struct hevc_state),
    .build_packet = hevc_build_packet,
    .restart = hevc_restart,
};
