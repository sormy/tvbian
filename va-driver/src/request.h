#ifndef VAAPI_REQUEST_H
#define VAAPI_REQUEST_H

#include <stdio.h>
#include <sys/types.h>

#include <linux/videodev2.h>

#include "driver.h"

/* vb2's limit on a queue's buffers */
#define REQUEST_MAX_CAPTURES 32
/* requests in flight at once: the engine decodes one while the client readies the next */
#define REQUEST_SLOTS 4

/* A CAPTURE buffer, one surface's for the context's life: vb2 keeps its timestamp, by which later
 * pictures reference it. Cedrus's own memory, exported: lent to the surface as its own where the
 * surface has none, so the picture decodes in place; else bound to the surface as a picture.
 * Cedrus cannot take memory of the surface's: vb2 maps an imported CAPTURE buffer write-only in its
 * IOMMU, and Cedrus reads back what it wrote. */
struct capture_buffer {
    VASurfaceID surface;
    /* the export, and its inode, which a surface lent it shares */
    int fd;
    ino_t inode;
    size_t size;
    uint64_t timestamp;
    /* the buffer holding the surface's latest picture: its own, the reference a repeated
     * picture is, or -1 for none */
    int latest;
};

/* A request and the OUTPUT buffer it carries. A picture's last one, once done, delivers the
 * picture to its surface, unless that surface's buffer was given a newer picture meanwhile. */
struct request_slot {
    int request_fd;
    void *map;
    size_t length;
    bool busy;
    bool last;
    VASurfaceID surface;
    unsigned capture;
    uint64_t timestamp;
    /* the buffer whose picture the surface gets; -1 for one decoded in place */
    int picture;
};

/* The stateless engine's session: one decoder device, the media device its requests go to. */
struct request_ctx {
    struct driver *drv;
    int video_fd;
    int media_fd;
    /* the decoder's queues multi-planar, as rkvdec's and Hantro's are; Cedrus's are single */
    bool mplane;
    /* the profile the client asked for: VA carries no profile_idc, which some engines program */
    VAProfile profile;
    /* the context the session is for, to set it up again */
    const struct context *ctx;
    struct request_slot slots[REQUEST_SLOTS];
    /* the slot the next request takes, and the oldest still in flight */
    unsigned next_slot;
    unsigned oldest_slot;
    struct v4l2_format capture;
    /* CAPTURE's format as set, one plane, whichever API the queue speaks */
    struct v4l2_pix_format picture;
    /* the picture size the session is set up for */
    unsigned width;
    unsigned height;
    struct capture_buffer captures[REQUEST_MAX_CAPTURES];
    unsigned num_captures;
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
    /* the size a key frame sets, where a stream changes it within a context, as VP9's may; 0
     * for a picture that sets none */
    void (*picture_size)(const struct picture *pic, unsigned *width, unsigned *height);
    /* before the picture's buffer is chosen: what the session's buffers depend on, as an SPS */
    int (*prepare)(struct request_ctx *rq, const struct picture *pic);
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
/* a control's value for every request after, as a mode the engine reads once */
int request_set_control(struct request_ctx *rq, uint32_t id, int value);
/* a compound control's value for every request after, as rkvdec sets its pictures up from: a
 * device that refuses it while it has buffers gets it with the session set up again after */
int request_set_compound(struct request_ctx *rq, uint32_t id, const void *value, uint32_t size);
/* a control field as the host's mapping test reads it */
void request_dump(struct request_ctx *rq, const char *name, long value);

#endif
