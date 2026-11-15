/* VP9: VA hands over the whole frame, uncompressed header included: nothing to rebuild. */
#include <errno.h>

#include "driver.h"

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
