#ifndef VAAPI_VP9_HEADER_H
#define VAAPI_VP9_HEADER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <linux/v4l2-controls.h>

/* What a VP9 frame header leaves to the frames before it: loop filter deltas, segment features,
 * and an inter frame its colour config. */
struct vp9_persistent {
    uint8_t bit_depth;
    uint32_t color_flags;
    int8_t ref_deltas[4];
    int8_t mode_deltas[2];
    int16_t feature_data[8][4];
    uint8_t feature_enabled[8];
    bool abs_or_delta_update;
};

/* The uncompressed header, read into the frame control; size the frame's when a reference's. */
int vp9_parse_uncompressed(struct vp9_persistent *st, const uint8_t *data, size_t size,
                           unsigned width, unsigned height, struct v4l2_ctrl_vp9_frame *f);

/* The compressed header's probability deltas, and its reference mode into the frame control. */
int vp9_parse_compressed(const uint8_t *data, size_t size, struct v4l2_ctrl_vp9_frame *f,
                         struct v4l2_ctrl_vp9_compressed_hdr *h);

#endif
