/*
 * VP8 onto the stateless frame control. VA gives each segment's quantiser and filter level
 * as absolute values, so the segment update goes in absolute mode; the frame goes out with the
 * frame tag and key-frame header VA strips, rebuilt as for the bitstream engines.
 */
#include <errno.h>
#include <string.h>

#include "request.h"

enum {
    SEGMENTS = 4,
    Y_AC = 0,
    Y_DC = 1,
    Y2_DC = 2,
    Y2_AC = 3,
    UV_DC = 4,
    UV_AC = 5,
};

static void fill_frame(const struct request_ctx *rq, struct v4l2_ctrl_vp8_frame *f,
                       const VAPictureParameterBufferVP8 *pp,
                       const VASliceParameterBufferVP8 *sp, const VAIQMatrixBufferVP8 *iq,
                       const VAProbabilityDataBufferVP8 *probabilities)
{
    const typeof(pp->pic_fields.bits) *bits = &pp->pic_fields.bits;
    const uint16_t *base = iq->quantization_index[0];
    *f = (struct v4l2_ctrl_vp8_frame){
        .width = pp->frame_width,
        .height = pp->frame_height,
        .version = bits->version,
        .prob_skip_false = pp->prob_skip_false,
        .prob_intra = pp->prob_intra,
        .prob_last = pp->prob_last,
        .prob_gf = pp->prob_gf,
        .num_dct_parts = sp->num_of_partitions - 1,
        /* VA's first partition size leaves out the header the client read */
        .first_part_size = sp->partition_size[0] + (sp->macroblock_offset + 7) / 8,
        .first_part_header_bits = sp->macroblock_offset,
        .last_frame_ts = request_timestamp(rq, pp->last_ref_frame),
        .golden_frame_ts = request_timestamp(rq, pp->golden_ref_frame),
        .alt_frame_ts = request_timestamp(rq, pp->alt_ref_frame),
        .coder_state = { pp->bool_coder_ctx.range, pp->bool_coder_ctx.value,
                         pp->bool_coder_ctx.count },
        .quant = {
            .y_ac_qi = base[Y_AC],
            .y_dc_delta = base[Y_DC] - base[Y_AC],
            .y2_dc_delta = base[Y2_DC] - base[Y_AC],
            .y2_ac_delta = base[Y2_AC] - base[Y_AC],
            .uv_dc_delta = base[UV_DC] - base[Y_AC],
            .uv_ac_delta = base[UV_AC] - base[Y_AC],
        },
        .lf = { .sharpness_level = bits->sharpness_level, .level = pp->loop_filter_level[0] },
    };
    for (unsigned i = 0; i + 1 < sp->num_of_partitions && i < 8; i++)
        f->dct_part_sizes[i] = sp->partition_size[i + 1];
    for (unsigned i = 0; i < SEGMENTS; i++) {
        f->segment.quant_update[i] = iq->quantization_index[i][Y_AC];
        f->segment.lf_update[i] = pp->loop_filter_level[i];
        f->lf.ref_frm_delta[i] = pp->loop_filter_deltas_ref_frame[i];
        f->lf.mb_mode_delta[i] = pp->loop_filter_deltas_mode[i];
    }
    memcpy(f->segment.segment_probs, pp->mb_segment_tree_probs, sizeof(f->segment.segment_probs));
    if (bits->segmentation_enabled)
        f->segment.flags |= V4L2_VP8_SEGMENT_FLAG_ENABLED;
    if (bits->update_mb_segmentation_map)
        f->segment.flags |= V4L2_VP8_SEGMENT_FLAG_UPDATE_MAP;
    if (bits->update_segment_feature_data)
        f->segment.flags |= V4L2_VP8_SEGMENT_FLAG_UPDATE_FEATURE_DATA;
    if (bits->loop_filter_adj_enable)
        f->lf.flags |= V4L2_VP8_LF_ADJ_ENABLE;
    if (bits->mode_ref_lf_delta_update)
        f->lf.flags |= V4L2_VP8_LF_DELTA_UPDATE;
    if (bits->filter_type)
        f->lf.flags |= V4L2_VP8_LF_FILTER_TYPE_SIMPLE;
    memcpy(f->entropy.coeff_probs, probabilities->dct_coeff_probs, sizeof(f->entropy.coeff_probs));
    memcpy(f->entropy.y_mode_probs, pp->y_mode_probs, sizeof(f->entropy.y_mode_probs));
    memcpy(f->entropy.uv_mode_probs, pp->uv_mode_probs, sizeof(f->entropy.uv_mode_probs));
    memcpy(f->entropy.mv_probs, pp->mv_probs, sizeof(f->entropy.mv_probs));
    /* VA's key_frame is the bitstream's frame type: 0 for a key frame */
    f->flags = V4L2_VP8_FRAME_FLAG_SHOW_FRAME | (!bits->key_frame ? V4L2_VP8_FRAME_FLAG_KEY_FRAME : 0) |
               (bits->mb_no_coeff_skip ? V4L2_VP8_FRAME_FLAG_MB_NO_SKIP_COEFF : 0) |
               (bits->sign_bias_golden ? V4L2_VP8_FRAME_FLAG_SIGN_BIAS_GOLDEN : 0) |
               (bits->sign_bias_alternate ? V4L2_VP8_FRAME_FLAG_SIGN_BIAS_ALT : 0);
}

static int vp8_submit(struct request_ctx *rq, const struct picture *pic)
{
    const VASliceParameterBufferVP8 *sp = pic->num_slices ? pic->slices[0].param : NULL;
    struct v4l2_ctrl_vp8_frame frame;
    struct annexb data = { 0 };
    struct packet_info info;
    int ret;

    if (!pic->picture_param || !sp || !pic->iq_matrix || !pic->probabilities)
        return -EINVAL;
    fill_frame(rq, &frame, pic->picture_param, sp, pic->iq_matrix, pic->probabilities);
    request_dump(rq, "width", frame.width);
    request_dump(rq, "frame_type", !(frame.flags & V4L2_VP8_FRAME_FLAG_KEY_FRAME));
    request_dump(rq, "first_part_size", frame.first_part_size);
    request_dump(rq, "prob_skip_false", frame.prob_skip_false);
    request_dump(rq, "y_ac_qi", frame.quant.y_ac_qi);
    request_dump(rq, "sharpness_level", frame.lf.sharpness_level);
    request_dump(rq, "loop_filter_level", frame.lf.level);
    if ((ret = codec_vp8.build_packet(NULL, pic, &data, &info)) == 0) {
        struct v4l2_ext_control control = { .id = V4L2_CID_STATELESS_VP8_FRAME,
                                            .size = sizeof(frame), .ptr = &frame };
        ret = request_queue(rq, &control, 1, &data, true, true);
    }
    annexb_free(&data);
    return ret;
}

const struct request_codec request_vp8 = {
    .kind = CODEC_VP8,
    .pixelformat = V4L2_PIX_FMT_VP8_FRAME,
    .state_size = 1,
    .submit = vp8_submit,
};
