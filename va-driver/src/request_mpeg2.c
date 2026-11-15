/* MPEG-2 onto the stateless controls: one request a picture, its slices as they came. */
#include <errno.h>

#include "request.h"

enum {
    PICTURE_P = 2,
    PICTURE_B = 3,
    CHROMA_420 = 1,
    MAIN_PROFILE_HIGH_LEVEL = 0x44,
    F_CODE_BITS = 4,
    F_CODE_MASK = 0xf,
    NUM_CONTROLS = 3,
};

static void fill_picture(const struct request_ctx *rq, struct v4l2_ctrl_mpeg2_picture *picture,
                         const VAPictureParameterBufferMPEG2 *pp)
{
    const typeof(pp->picture_coding_extension.bits) *ext = &pp->picture_coding_extension.bits;
    *picture = (struct v4l2_ctrl_mpeg2_picture){
        .picture_coding_type = pp->picture_coding_type,
        .picture_structure = ext->picture_structure,
        .intra_dc_precision = ext->intra_dc_precision,
    };
    if (pp->picture_coding_type == PICTURE_P || pp->picture_coding_type == PICTURE_B)
        picture->forward_ref_ts = request_timestamp(rq, pp->forward_reference_picture);
    if (pp->picture_coding_type == PICTURE_B)
        picture->backward_ref_ts = request_timestamp(rq, pp->backward_reference_picture);
    /* VA packs the four f_codes into one word, [0][0] highest */
    for (unsigned i = 0; i < 4; i++)
        picture->f_code[i / 2][i % 2] = (pp->f_code >> (F_CODE_BITS * (3 - i))) & F_CODE_MASK;
    const struct {
        bool set;
        uint32_t flag;
    } flags[] = {
        { ext->top_field_first, V4L2_MPEG2_PIC_FLAG_TOP_FIELD_FIRST },
        { ext->frame_pred_frame_dct, V4L2_MPEG2_PIC_FLAG_FRAME_PRED_DCT },
        { ext->concealment_motion_vectors, V4L2_MPEG2_PIC_FLAG_CONCEALMENT_MV },
        { ext->q_scale_type, V4L2_MPEG2_PIC_FLAG_Q_SCALE_TYPE },
        { ext->intra_vlc_format, V4L2_MPEG2_PIC_FLAG_INTRA_VLC },
        { ext->alternate_scan, V4L2_MPEG2_PIC_FLAG_ALT_SCAN },
        { ext->repeat_first_field, V4L2_MPEG2_PIC_FLAG_REPEAT_FIRST },
        { ext->progressive_frame, V4L2_MPEG2_PIC_FLAG_PROGRESSIVE },
    };
    for (size_t i = 0; i < sizeof(flags) / sizeof(flags[0]); i++)
        if (flags[i].set)
            picture->flags |= flags[i].flag;
}

/* both in zigzag order; a matrix not loaded keeps MPEG-2's default */
static void fill_quantisation(struct v4l2_ctrl_mpeg2_quantisation *q,
                              const VAIQMatrixBufferMPEG2 *iq)
{
    static const uint8_t default_intra[64] = {
        8,  16, 16, 19, 16, 19, 22, 22, 22, 22, 22, 22, 26, 24, 26, 27, 27, 27, 26, 26, 26, 26,
        27, 27, 27, 29, 29, 29, 34, 34, 34, 29, 29, 29, 27, 27, 29, 29, 32, 32, 34, 34, 37, 38,
        37, 35, 35, 34, 35, 38, 38, 40, 40, 40, 48, 48, 46, 46, 56, 56, 58, 69, 69, 83,
    };
    for (unsigned i = 0; i < 64; i++) {
        q->intra_quantiser_matrix[i] =
            iq && iq->load_intra_quantiser_matrix ? iq->intra_quantiser_matrix[i] : default_intra[i];
        q->non_intra_quantiser_matrix[i] = iq && iq->load_non_intra_quantiser_matrix
                                               ? iq->non_intra_quantiser_matrix[i]
                                               : 16;
        q->chroma_intra_quantiser_matrix[i] = iq && iq->load_chroma_intra_quantiser_matrix
                                                  ? iq->chroma_intra_quantiser_matrix[i]
                                                  : q->intra_quantiser_matrix[i];
        q->chroma_non_intra_quantiser_matrix[i] = iq && iq->load_chroma_non_intra_quantiser_matrix
                                                      ? iq->chroma_non_intra_quantiser_matrix[i]
                                                      : q->non_intra_quantiser_matrix[i];
    }
}

static int mpeg2_submit(struct request_ctx *rq, const struct picture *pic)
{
    const VAPictureParameterBufferMPEG2 *pp = pic->picture_param;
    struct v4l2_ctrl_mpeg2_sequence sequence = {
        .horizontal_size = pp ? pp->horizontal_size : 0,
        .vertical_size = pp ? pp->vertical_size : 0,
        .profile_and_level_indication = MAIN_PROFILE_HIGH_LEVEL,
        .chroma_format = CHROMA_420,
    };
    struct v4l2_ctrl_mpeg2_picture picture;
    struct v4l2_ctrl_mpeg2_quantisation quantisation;
    struct annexb data = { 0 };
    int ret = 0;

    if (!pp || !pic->num_slices)
        return -EINVAL;
    fill_picture(rq, &picture, pp);
    fill_quantisation(&quantisation, pic->iq_matrix);
    request_dump(rq, "horizontal_size_value", sequence.horizontal_size);
    request_dump(rq, "picture_coding_type", picture.picture_coding_type);
    request_dump(rq, "intra_dc_precision", picture.intra_dc_precision);
    request_dump(rq, "picture_structure", picture.picture_structure);
    request_dump(rq, "f_code[0][0]", picture.f_code[0][0]);
    request_dump(rq, "f_code[1][1]", picture.f_code[1][1]);
    request_dump(rq, "alternate_scan", !!(picture.flags & V4L2_MPEG2_PIC_FLAG_ALT_SCAN));
    for (unsigned i = 0; i < pic->num_slices && !ret; i++)
        ret = annexb_append_raw(&data, pic->slices[i].data, pic->slices[i].size);
    struct v4l2_ext_control controls[NUM_CONTROLS] = {
        { .id = V4L2_CID_STATELESS_MPEG2_SEQUENCE, .size = sizeof(sequence), .ptr = &sequence },
        { .id = V4L2_CID_STATELESS_MPEG2_PICTURE, .size = sizeof(picture), .ptr = &picture },
        { .id = V4L2_CID_STATELESS_MPEG2_QUANTISATION,
          .size = sizeof(quantisation),
          .ptr = &quantisation },
    };
    if (!ret)
        ret = request_queue(rq, controls, NUM_CONTROLS, &data, true, true);
    annexb_free(&data);
    return ret;
}

const struct request_codec request_mpeg2 = {
    .kind = CODEC_MPEG2,
    .pixelformat = V4L2_PIX_FMT_MPEG2_SLICE,
    .state_size = 1,
    .submit = mpeg2_submit,
};
