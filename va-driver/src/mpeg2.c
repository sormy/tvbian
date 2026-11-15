/* MPEG-2: sequence, picture and matrix headers rebuilt ahead of the slices as they came. */
#include <errno.h>
#include <string.h>

#include "driver.h"

enum {
    START_PICTURE = 0x00,
    START_SEQUENCE = 0xb3,
    START_EXTENSION = 0xb5,
    EXT_SEQUENCE = 1,
    EXT_QUANT_MATRIX = 3,
    EXT_PICTURE_CODING = 8,
    PICTURE_I = 1,
    PICTURE_P = 2,
    PICTURE_B = 3,
    PICTURE_FRAME = 3,
    SQUARE_PIXELS = 1,
    FRAME_RATE_25 = 3,
    BIT_RATE_UNSPECIFIED = 0x3ffff,
    VBV_DELAY_UNSPECIFIED = 0xffff,
    VBV_BUFFER_SIZE = 112,
    MAIN_PROFILE_HIGH_LEVEL = 0x44,
    CHROMA_420 = 1,
    MPEG1_F_CODE = 7,
    SIZE_BITS = 12,
};

struct mpeg2_state {
    struct bit_writer sent_sequence;
};

static void start_code(struct bit_writer *bw, unsigned code)
{
    bw_bits(bw, 24, 1);
    bw_bits(bw, 8, code);
}

static void byte_align(struct bit_writer *bw)
{
    while (bw->bits % 8)
        bw_flag(bw, 0);
}

static void write_sequence(struct bit_writer *bw, const VAPictureParameterBufferMPEG2 *pp)
{
    bw_init(bw);
    start_code(bw, START_SEQUENCE);
    bw_bits(bw, SIZE_BITS, pp->horizontal_size & 0xfff);
    bw_bits(bw, SIZE_BITS, pp->vertical_size & 0xfff);
    bw_bits(bw, 4, SQUARE_PIXELS);
    bw_bits(bw, 4, FRAME_RATE_25);
    bw_bits(bw, 18, BIT_RATE_UNSPECIFIED);
    bw_flag(bw, 1);
    bw_bits(bw, 10, VBV_BUFFER_SIZE);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    bw_flag(bw, 0);
    byte_align(bw);
    start_code(bw, START_EXTENSION);
    bw_bits(bw, 4, EXT_SEQUENCE);
    bw_bits(bw, 8, MAIN_PROFILE_HIGH_LEVEL);
    /* VA does not say whether the sequence is progressive: a progressive frame declares it so,
     * an interlaced one sends the sequence again, interlaced allowed */
    bw_flag(bw, pp->picture_coding_extension.bits.progressive_frame &&
                    pp->picture_coding_extension.bits.picture_structure == PICTURE_FRAME);
    bw_bits(bw, 2, CHROMA_420);
    bw_bits(bw, 2, pp->horizontal_size >> SIZE_BITS);
    bw_bits(bw, 2, pp->vertical_size >> SIZE_BITS);
    bw_bits(bw, 12, 0);
    bw_flag(bw, 1);
    bw_bits(bw, 8, 0);
    /* not low delay: VA does not say whether B-pictures come, and a decoder told there are none
     * manages its references otherwise */
    bw_flag(bw, 0);
    bw_bits(bw, 2, 0);
    bw_bits(bw, 5, 0);
    byte_align(bw);
}

static void write_matrix(struct bit_writer *bw, bool load, const uint8_t *zigzag)
{
    bw_flag(bw, load);
    for (unsigned i = 0; load && i < 64; i++)
        bw_bits(bw, 8, zigzag[i]);
}

static void write_picture(struct bit_writer *bw, const VAPictureParameterBufferMPEG2 *pp,
                          const VAIQMatrixBufferMPEG2 *iq)
{
    bw_init(bw);
    start_code(bw, START_PICTURE);
    bw_bits(bw, 10, 0);
    bw_bits(bw, 3, pp->picture_coding_type);
    bw_bits(bw, 16, VBV_DELAY_UNSPECIFIED);
    if (pp->picture_coding_type == PICTURE_P || pp->picture_coding_type == PICTURE_B) {
        bw_flag(bw, 0);
        bw_bits(bw, 3, MPEG1_F_CODE);
    }
    if (pp->picture_coding_type == PICTURE_B) {
        bw_flag(bw, 0);
        bw_bits(bw, 3, MPEG1_F_CODE);
    }
    bw_flag(bw, 0);
    byte_align(bw);
    start_code(bw, START_EXTENSION);
    bw_bits(bw, 4, EXT_PICTURE_CODING);
    bw_bits(bw, 16, pp->f_code);
    bw_bits(bw, 2, pp->picture_coding_extension.bits.intra_dc_precision);
    bw_bits(bw, 2, pp->picture_coding_extension.bits.picture_structure);
    bw_flag(bw, pp->picture_coding_extension.bits.top_field_first);
    bw_flag(bw, pp->picture_coding_extension.bits.frame_pred_frame_dct);
    bw_flag(bw, pp->picture_coding_extension.bits.concealment_motion_vectors);
    bw_flag(bw, pp->picture_coding_extension.bits.q_scale_type);
    bw_flag(bw, pp->picture_coding_extension.bits.intra_vlc_format);
    bw_flag(bw, pp->picture_coding_extension.bits.alternate_scan);
    bw_flag(bw, pp->picture_coding_extension.bits.repeat_first_field);
    bw_flag(bw, pp->picture_coding_extension.bits.progressive_frame);
    bw_flag(bw, pp->picture_coding_extension.bits.progressive_frame);
    bw_flag(bw, 0);
    byte_align(bw);
    if (iq) {
        start_code(bw, START_EXTENSION);
        bw_bits(bw, 4, EXT_QUANT_MATRIX);
        write_matrix(bw, iq->load_intra_quantiser_matrix, iq->intra_quantiser_matrix);
        write_matrix(bw, iq->load_non_intra_quantiser_matrix, iq->non_intra_quantiser_matrix);
        /* 4:2:0 shares the luma matrices: its chroma load flags must be 0 */
        write_matrix(bw, false, NULL);
        write_matrix(bw, false, NULL);
        byte_align(bw);
    }
}

static int mpeg2_build_packet(void *state, const struct picture *pic, struct annexb *out,
                              struct packet_info *info)
{
    struct mpeg2_state *st = state;
    const VAPictureParameterBufferMPEG2 *pp = pic->picture_param;
    struct bit_writer bw;
    int ret;

    if (!pp || !pic->num_slices)
        return -EINVAL;
    info->predicted = pp->picture_coding_type != PICTURE_I;
    if (pp->picture_coding_extension.bits.is_first_field) {
        write_sequence(&bw, pp);
    if (pp->picture_coding_type == PICTURE_I || bw.bits != st->sent_sequence.bits ||
            memcmp(bw.data, st->sent_sequence.data, bw_bytes(&bw))) {
            if ((ret = annexb_append_raw(out, bw.data, bw_bytes(&bw))))
                return ret;
            st->sent_sequence = bw;
        }
    }
    write_picture(&bw, pp, pic->iq_matrix);
    if ((ret = annexb_append_raw(out, bw.data, bw_bytes(&bw))))
        return ret;
    for (unsigned i = 0; i < pic->num_slices; i++) {
        const struct slice *s = &pic->slices[i];
        const VASliceParameterBufferMPEG2 *sp = s->param;
        bool has_start_code = s->size > 3 && !s->data[0] && !s->data[1] && s->data[2] == 1;
        if (!has_start_code && sp) {
            uint8_t slice_start[] = { 0, 0, 1, sp->slice_vertical_position + 1 };
            if ((ret = annexb_append_raw(out, slice_start, sizeof(slice_start))))
                return ret;
        }
        if ((ret = annexb_append_raw(out, s->data, s->size)))
            return ret;
    }
    info->hidden = false;
    return 0;
}

static void mpeg2_restart(void *state)
{
    struct mpeg2_state *st = state;
    st->sent_sequence.bits = 0;
}

const struct codec codec_mpeg2 = {
    .kind = CODEC_MPEG2,
    .state_size = sizeof(struct mpeg2_state),
    .build_packet = mpeg2_build_packet,
    .restart = mpeg2_restart,
};
