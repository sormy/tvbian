/* VP9: VA hands over the whole frame, uncompressed header included: nothing to rebuild. */
#include <errno.h>

#include "bitstream.h"
#include "driver.h"

#define SUPERFRAME_MARKER 0xc0
#define SUPERFRAME_SIZE_BYTES 4
#define SUPERFRAME_FRAMES 2
#define BYTE_BITS 8

static int append_le(struct annexb *out, uint32_t value)
{
    uint8_t bytes[SUPERFRAME_SIZE_BYTES];
    for (unsigned i = 0; i < SUPERFRAME_SIZE_BYTES; i++)
        bytes[i] = value >> (i * BYTE_BITS);
    return annexb_append_raw(out, bytes, sizeof(bytes));
}

int vp9_superframe(struct annexb *out, const struct annexb *hidden, const struct annexb *shown)
{
    const uint8_t marker = SUPERFRAME_MARKER | (SUPERFRAME_SIZE_BYTES - 1) << 3 |
                           (SUPERFRAME_FRAMES - 1);
    out->size = 0;
    int ret = annexb_append_raw(out, hidden->data, hidden->size);
    if (!ret)
        ret = annexb_append_raw(out, shown->data, shown->size);
    if (!ret)
        ret = annexb_append_raw(out, &marker, 1);
    if (!ret)
        ret = append_le(out, hidden->size);
    if (!ret)
        ret = append_le(out, shown->size);
    return ret ? ret : annexb_append_raw(out, &marker, 1);
}

static int vp9_build_packet(void *state, const struct picture *pic, struct annexb *out,
                            struct packet_info *info)
{
    const VADecPictureParameterBufferVP9 *pp = pic->picture_param;
    int ret;

    if (!pp || !pic->num_slices)
        return -EINVAL;
    for (unsigned i = 0; i < pic->num_slices; i++)
        if ((ret = annexb_append_raw(out, pic->slices[i].data, pic->slices[i].size)))
            return ret;
    info->hidden = !pp->pic_fields.bits.show_frame;
    return 0;
}

const struct codec codec_vp9 = {
    .kind = CODEC_VP9,
    .build_packet = vp9_build_packet,
};
