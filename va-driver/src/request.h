#ifndef VAAPI_REQUEST_H
#define VAAPI_REQUEST_H

#include <stdio.h>

#include <linux/videodev2.h>

#include "driver.h"

#define REQUEST_MAX_CAPTURES 32
#define REQUEST_MAX_SURFACES 64

/* A CAPTURE buffer, Cedrus's own, exported: kept while it holds a surface's latest picture, which
 * VA may name as a reference, and while pictures handed out hold it. */
struct capture_buffer {
    int fd;
    size_t size;
    uint64_t timestamp;
    unsigned held;
    bool queued;
};

/* A surface's latest picture: the buffer holding it, shared by a picture that repeats another. */
struct latest_picture {
    VASurfaceID surface;
    unsigned index;
};

/* The stateless engine's session: one decoder device, the media device its requests go to.
 * Shared with the pictures it handed out, which may outlive the context. */
struct request_ctx {
    struct driver *drv;
    unsigned refs;
    int video_fd;
    int media_fd;
    int request_fd;
    void *output_map;
    size_t output_length;
    struct v4l2_format capture;
    struct capture_buffer captures[REQUEST_MAX_CAPTURES];
    unsigned num_captures;
    struct latest_picture latest[REQUEST_MAX_SURFACES];
    unsigned num_latest;
    /* the buffer this picture decodes into, and the timestamp its requests carry */
    unsigned target;
    uint64_t last_timestamp;
    /* the buffer of a picture this one repeats, decoding nothing; -1 for none */
    int repeated;
    /* CAPTURE in Cedrus's AFBC, its DRM modifier; 0 for linear NV12 and P010 */
    uint64_t compressed_modifier;
    /* the controls go to a text file instead of a device: the host's mapping test */
    FILE *dump;
    unsigned dump_picture;
    void *codec_state;
};

/* One codec's VA parameters onto its stateless controls. */
struct request_codec {
    enum codec_kind kind;
    uint32_t pixelformat;
    size_t state_size;
    int (*init)(struct request_ctx *rq);
    int (*submit)(struct request_ctx *rq, const struct picture *pic);
};

extern const struct request_codec request_h264, request_hevc, request_vp8, request_vp9,
    request_mpeg2, request_mpeg4, request_vc1;

/* the timestamp of the picture a reference names, by surface; 0 for none */
uint64_t request_timestamp(const struct request_ctx *rq, VASurfaceID surface);
/* one OUTPUT buffer and its controls as one request; the last of a picture releases CAPTURE */
int request_queue(struct request_ctx *rq, struct v4l2_ext_control *controls, unsigned count,
                  const struct annexb *data, bool first, bool last);
/* the target's picture is the reference's own, with no request: a VC-1 skipped picture */
int request_repeat_reference(struct request_ctx *rq, VASurfaceID reference);
int request_get_control(struct request_ctx *rq, uint32_t id, int *value);
/* a control field as the host's mapping test reads it */
void request_dump(struct request_ctx *rq, const char *name, long value);

#endif
