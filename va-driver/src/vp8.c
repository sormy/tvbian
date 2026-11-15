/* VP8: the frame tag and key frame header VA strips, rebuilt ahead of the first partition. */
#include <errno.h>

#include "driver.h"

#define FRAME_TAG_BYTES 3
#define SHOW_FRAME_BIT 4
#define VERSION_SHIFT 1
#define FIRST_PART_SIZE_SHIFT 5

static int vp8_build_packet(void *state, const struct picture *pic, struct annexb *out,
                            struct packet_info *info)
{
    const VAPictureParameterBufferVP8 *pp = pic->picture_param;
    const VASliceParameterBufferVP8 *sp = pic->num_slices ? pic->slices[0].param : NULL;
    int ret;

    if (!pp || !sp)
        return -EINVAL;
    /* VA's first partition size leaves out the header bits the client already read */
    uint32_t first_part_size = sp->partition_size[0] + (sp->macroblock_offset + 7) / 8;
    bool key_frame = !pp->pic_fields.bits.key_frame;
    /* VA has no show_frame: a hidden frame is output too, bound to a surface nobody shows */
    uint32_t tag = pp->pic_fields.bits.key_frame | pp->pic_fields.bits.version << VERSION_SHIFT |
                   1u << SHOW_FRAME_BIT | first_part_size << FIRST_PART_SIZE_SHIFT;
    uint8_t header[] = {
        tag & 0xff,
        (tag >> 8) & 0xff,
        (tag >> 16) & 0xff,
        0x9d,
        0x01,
        0x2a,
        pp->frame_width & 0xff,
        (pp->frame_width >> 8) & 0x3f,
        pp->frame_height & 0xff,
        (pp->frame_height >> 8) & 0x3f,
    };
    if ((ret = annexb_append_raw(out, header, key_frame ? sizeof(header) : FRAME_TAG_BYTES)))
        return ret;
    for (unsigned i = 0; i < pic->num_slices; i++)
        if ((ret = annexb_append_raw(out, pic->slices[i].data, pic->slices[i].size)))
            return ret;
    info->hidden = false;
    return 0;
}

const struct codec codec_vp8 = {
    .kind = CODEC_VP8,
    .build_packet = vp8_build_packet,
};
