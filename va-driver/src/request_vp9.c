/*
 * VP9 onto the stateless frame and compressed-header controls. VA's slice data is the whole
 * frame: its two headers are read from it, the loop filter deltas and segment features carried
 * from frame to frame. The references are VA's, each by its surface's timestamp.
 */
#include <errno.h>

#include "request.h"
#include "vp9_header.h"

enum { NUM_CONTROLS = 2 };

static void dump_frame(struct request_ctx *rq, const struct v4l2_ctrl_vp9_frame *f,
                       const struct v4l2_ctrl_vp9_compressed_hdr *h)
{
    unsigned coef_updates = 0;
    for (size_t i = 0; i < sizeof(h->coef); i++)
        coef_updates += (&h->coef[0][0][0][0][0][0])[i] != 0;
    request_dump(rq, "frame_type", !(f->flags & V4L2_VP9_FRAME_FLAG_KEY_FRAME));
    request_dump(rq, "show_frame", !!(f->flags & V4L2_VP9_FRAME_FLAG_SHOW_FRAME));
    request_dump(rq, "frame_width_minus_1", f->frame_width_minus_1);
    request_dump(rq, "base_q_idx", f->quant.base_q_idx);
    request_dump(rq, "loop_filter_level", f->lf.level);
    request_dump(rq, "loop_filter_sharpness", f->lf.sharpness);
    request_dump(rq, "header_size_in_bytes", f->compressed_header_size);
    request_dump(rq, "frame_context_idx", f->frame_context_idx);
    request_dump(rq, "refresh_frame_context", !!(f->flags & V4L2_VP9_FRAME_FLAG_REFRESH_FRAME_CTX));
    request_dump(rq, "segmentation_enabled", !!(f->seg.flags & V4L2_VP9_SEGMENTATION_FLAG_ENABLED));
    request_dump(rq, "tx_mode", h->tx_mode);
    request_dump(rq, "reference_mode", f->reference_mode);
    request_dump(rq, "coef_updates", coef_updates);
}

static int vp9_submit(struct request_ctx *rq, const struct picture *pic)
{
    const VADecPictureParameterBufferVP9 *pp = pic->picture_param;
    struct vp9_persistent *st = rq->codec_state;
    struct v4l2_ctrl_vp9_frame frame;
    struct v4l2_ctrl_vp9_compressed_hdr probabilities;
    struct annexb data = { 0 };
    int ret;

    if (!pp || pic->num_slices != 1)
        return -EINVAL;
    const struct slice *s = &pic->slices[0];
    if ((ret = vp9_parse_uncompressed(st, s->data, s->size, pp->frame_width, pp->frame_height,
                                      &frame)) < 0 ||
        (ret = vp9_parse_compressed(s->data + frame.uncompressed_header_size,
                                    frame.compressed_header_size, &frame, &probabilities)) < 0)
        return ret;
    frame.last_frame_ts = request_timestamp(rq, pp->reference_frames[pp->pic_fields.bits.last_ref_frame]);
    frame.golden_frame_ts = request_timestamp(rq, pp->reference_frames[pp->pic_fields.bits.golden_ref_frame]);
    frame.alt_frame_ts = request_timestamp(rq, pp->reference_frames[pp->pic_fields.bits.alt_ref_frame]);
    dump_frame(rq, &frame, &probabilities);
    struct v4l2_ext_control controls[NUM_CONTROLS] = {
        { .id = V4L2_CID_STATELESS_VP9_FRAME, .size = sizeof(frame), .ptr = &frame },
        { .id = V4L2_CID_STATELESS_VP9_COMPRESSED_HDR,
          .size = sizeof(probabilities),
          .ptr = &probabilities },
    };
    if (!(ret = annexb_append_raw(&data, s->data, s->size)))
        ret = request_queue(rq, controls, NUM_CONTROLS, &data, true, true);
    annexb_free(&data);
    return ret;
}

static void vp9_picture_size(const struct picture *pic, unsigned *width, unsigned *height)
{
    const VADecPictureParameterBufferVP9 *pp = pic->picture_param;
    bool key = pp && pp->pic_fields.bits.frame_type == 0;
    *width = key ? pp->frame_width : 0;
    *height = key ? pp->frame_height : 0;
}

const struct request_codec request_vp9 = {
    .kind = CODEC_VP9,
    .pixelformat = V4L2_PIX_FMT_VP9_FRAME,
    .state_size = sizeof(struct vp9_persistent),
    .submit = vp9_submit,
    .picture_size = vp9_picture_size,
};
