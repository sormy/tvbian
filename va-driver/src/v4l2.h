/* What a V4L2 memory-to-memory device says it takes: formats, sizes, profiles. */
#ifndef VAAPI_V4L2_H
#define VAAPI_V4L2_H

#include <stdbool.h>
#include <stdint.h>

#include "driver.h"

/* A profile an engine may offer: the coded format carrying it, where the device has a profile
 * menu the item it must list, and whether its CAPTURE must take a 10-bit layout. */
struct v4l2_candidate {
    VAProfile profile;
    VAEntrypoint entrypoint;
    uint32_t pixelformat;
    uint32_t menu;
    unsigned item;
    bool ten_bit;
};

/* the first device whose coded queue takes the format: OUTPUT to decode, CAPTURE to encode; -1
 * for none. flags are the format's V4L2_FMT_FLAG_*. */
int v4l2_open_coded(uint32_t pixelformat, bool decode, bool *mplane, uint32_t *flags);
/* the candidates some device takes, as offers sized as it reports: out has room for count */
unsigned v4l2_offers(const struct v4l2_candidate *candidates, unsigned count, struct offer *out);

#endif
