/*
 * V4L2 stateful mem2mem, the Amlogic decoder and encoders: the rebuilt bitstream queued as
 * OUTPUT, the pictures dequeued from CAPTURE. Every access unit is stamped with its surface
 * and carries its own parameter sets, which the meson decoder needs ahead of the first one;
 * a resolution change reallocates CAPTURE while surfaces still hold the old pictures.
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <linux/videodev2.h>

#include "driver.h"
#include "settings.h"
#include "v4l2.h"

#define MAX_BUFFERS 32
#define OUTPUT_BUFFERS 8
#define CODED_BUFFER_SIZE (4 << 20)
/* pictures surfaces hold beyond the decoder's own: VA has no call that hands one back, so a
 * picture stays bound to its surface until the surface is decoded into again */
#define EXTRA_CAPTURE 16
/* what those pictures may take in all, at 4K a dozen of them */
#define CAPTURE_BUDGET (192u << 20)
#define OUTPUT_WAIT_MS 200
#define SYNC_WAIT_MS 1000
/* a decoder hands a picture out in a few ms: one quiet for longer holds it */
#define QUIET_MS 20
#define ENCODE_WAIT_MS 2000
#define PERCENT 100
/* a raw picture's bytesused: every plane full */
#define WHOLE_PLANES ((size_t)-1)

struct m2m_buffer {
    void *map[PICTURE_PLANES];
    size_t length[PICTURE_PLANES];
    int fds[PICTURE_PLANES];
    bool queued;
};

struct m2m_queue {
    enum v4l2_buf_type type;
    struct v4l2_format format;
    struct m2m_buffer buffers[MAX_BUFFERS];
    unsigned count;
    bool streaming;
};

/* shared with the pictures it handed out, which may outlive the context */
struct m2m {
    int fd;
    /* multi-planar, as meson's are; Cedrus's stateful nodes are single-planar */
    bool mplane;
    /* the decoder tells its picture size by event; one that cannot has it read after a packet */
    bool dynamic_resolution;
    /* CAPTURE got fewer buffers than surfaces can hold: pictures are copied out at once */
    bool copies_out;
    /* when the decoder last took a packet or gave anything back */
    uint64_t active_ms;
    /* opened after a drain: the old session's references are gone */
    bool lost_references;
    bool announces_size;
    unsigned refs;
    unsigned generation;
    int num_targets;
    /* the scaled CAPTURE asked (meson-codecs 0017), set as CAPTURE is next allocated */
    unsigned scaled_width;
    unsigned scaled_height;
    struct m2m_queue output;
    struct m2m_queue capture;
};

struct m2m_picture {
    struct engine_picture base;
    struct m2m *m;
    unsigned index;
    unsigned generation;
};

#define VLD VAEntrypointVLD
#define ENC VAEntrypointEncSlice

#define H264_PROFILE V4L2_CID_MPEG_VIDEO_H264_PROFILE
#define HEVC_PROFILE V4L2_CID_MPEG_VIDEO_HEVC_PROFILE

/* what a stateful device may take; init keeps what it does. A 10-bit stream an engine writes as
 * 8 bits is widened into the client's 10-bit surface. */
static const struct v4l2_candidate m2m_candidates[] = {
    { VAProfileH264ConstrainedBaseline, VLD, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_CONSTRAINED_BASELINE, false },
    { VAProfileH264Main, VLD, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_MAIN, false },
    { VAProfileH264High, VLD, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_HIGH, false },
    { VAProfileHEVCMain, VLD, V4L2_PIX_FMT_HEVC, HEVC_PROFILE,
      V4L2_MPEG_VIDEO_HEVC_PROFILE_MAIN, false },
    { VAProfileHEVCMain10, VLD, V4L2_PIX_FMT_HEVC, HEVC_PROFILE,
      V4L2_MPEG_VIDEO_HEVC_PROFILE_MAIN_10, false },
    { VAProfileVP9Profile0, VLD, V4L2_PIX_FMT_VP9, V4L2_CID_MPEG_VIDEO_VP9_PROFILE,
      V4L2_MPEG_VIDEO_VP9_PROFILE_0, false },
    { VAProfileVP9Profile2, VLD, V4L2_PIX_FMT_VP9, V4L2_CID_MPEG_VIDEO_VP9_PROFILE,
      V4L2_MPEG_VIDEO_VP9_PROFILE_2, false },
    { VAProfileVP8Version0_3, VLD, V4L2_PIX_FMT_VP8, 0, 0, false },
    { VAProfileMPEG2Simple, VLD, V4L2_PIX_FMT_MPEG2, 0, 0, false },
    { VAProfileMPEG2Main, VLD, V4L2_PIX_FMT_MPEG2, 0, 0, false },
    { VAProfileJPEGBaseline, VLD, V4L2_PIX_FMT_MJPEG, 0, 0, false },
    { VAProfileMPEG4Simple, VLD, V4L2_PIX_FMT_MPEG4, 0, 0, false },
    { VAProfileMPEG4AdvancedSimple, VLD, V4L2_PIX_FMT_MPEG4, 0, 0, false },
    { VAProfileVC1Advanced, VLD, V4L2_PIX_FMT_VC1_ANNEX_G, 0, 0, false },
    { VAProfileH264ConstrainedBaseline, ENC, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_CONSTRAINED_BASELINE, false },
    { VAProfileH264Main, ENC, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_MAIN, false },
    /* a Main stream is a High one: clients ask High first */
    { VAProfileH264High, ENC, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_MAIN, false },
    { VAProfileHEVCMain, ENC, V4L2_PIX_FMT_HEVC, HEVC_PROFILE,
      V4L2_MPEG_VIDEO_HEVC_PROFILE_MAIN, false },
};

#define NUM_CANDIDATES (sizeof(m2m_candidates) / sizeof(m2m_candidates[0]))

static uint32_t coded_format(enum codec_kind codec)
{
    switch (codec) {
    case CODEC_H264:
        return V4L2_PIX_FMT_H264;
    case CODEC_HEVC:
        return V4L2_PIX_FMT_HEVC;
    case CODEC_VP9:
        return V4L2_PIX_FMT_VP9;
    case CODEC_VP8:
        return V4L2_PIX_FMT_VP8;
    case CODEC_MPEG2:
        return V4L2_PIX_FMT_MPEG2;
    case CODEC_JPEG:
        return V4L2_PIX_FMT_MJPEG;
    case CODEC_MPEG4:
        return V4L2_PIX_FMT_MPEG4;
    case CODEC_VC1:
        return V4L2_PIX_FMT_VC1_ANNEX_G;
    }
    return 0;
}

/* the stateful device whose coded queue takes the format: OUTPUT to decode, CAPTURE to encode */
static int open_device(struct m2m *m, bool coded_output, uint32_t pixelformat)
{
    uint32_t flags = 0;
    int fd = v4l2_open_coded(pixelformat, coded_output, &m->mplane, &flags);
    m->output.type = m->mplane ? V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE : V4L2_BUF_TYPE_VIDEO_OUTPUT;
    m->capture.type = m->mplane ? V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE : V4L2_BUF_TYPE_VIDEO_CAPTURE;
    m->dynamic_resolution = flags & V4L2_FMT_FLAG_DYN_RESOLUTION;
    return fd < 0 ? -ENODEV : fd;
}

static unsigned num_planes(const struct m2m *m, const struct m2m_queue *q)
{
    return m->mplane ? q->format.fmt.pix_mp.num_planes : 1;
}

static unsigned bytes_per_line(const struct m2m *m, const struct m2m_queue *q, unsigned plane)
{
    return m->mplane ? q->format.fmt.pix_mp.plane_fmt[plane].bytesperline
                     : q->format.fmt.pix.bytesperline;
}

static unsigned format_width(const struct m2m *m, const struct m2m_queue *q)
{
    return m->mplane ? q->format.fmt.pix_mp.width : q->format.fmt.pix.width;
}

static uint32_t pixel_format(const struct m2m *m, const struct m2m_queue *q)
{
    return m->mplane ? q->format.fmt.pix_mp.pixelformat : q->format.fmt.pix.pixelformat;
}

static unsigned format_height(const struct m2m *m, const struct m2m_queue *q)
{
    return m->mplane ? q->format.fmt.pix_mp.height : q->format.fmt.pix.height;
}

/* a format of either kind: the coded one with its buffer size, or a raw one */
static void set_format(const struct m2m *m, struct m2m_queue *q, uint32_t pixelformat,
                       unsigned width, unsigned height, unsigned sizeimage)
{
    q->format = (struct v4l2_format){ .type = q->type };
    if (m->mplane) {
        q->format.fmt.pix_mp = (struct v4l2_pix_format_mplane){
            .pixelformat = pixelformat, .width = width, .height = height,
            .num_planes = sizeimage ? 1 : 2, .plane_fmt[0].sizeimage = sizeimage };
    } else {
        q->format.fmt.pix = (struct v4l2_pix_format){
            .pixelformat = pixelformat, .width = width, .height = height, .sizeimage = sizeimage };
    }
}

/* a size past the engine's comes back clamped */
static bool clamped(const struct m2m *m, const struct m2m_queue *q, unsigned width, unsigned height)
{
    return format_width(m, q) < width || format_height(m, q) < height;
}

static void unmap_queue(struct m2m_queue *q)
{
    for (unsigned i = 0; i < q->count; i++) {
        for (unsigned p = 0; p < PICTURE_PLANES; p++) {
            if (q->buffers[i].map[p])
                munmap(q->buffers[i].map[p], q->buffers[i].length[p]);
            if (q->buffers[i].fds[p] > 0)
                close(q->buffers[i].fds[p]);
        }
    }
    memset(q->buffers, 0, sizeof(q->buffers));
    q->count = 0;
}

/* buffers requested, mapped, and for CAPTURE exported, so pictures go out as dma-bufs */
static int setup_queue(const struct m2m *m, struct m2m_queue *q, unsigned count, bool export)
{
    int fd = m->fd;
    struct v4l2_requestbuffers request = { .count = count, .type = q->type,
                                           .memory = V4L2_MEMORY_MMAP };
    if (ioctl(fd, VIDIOC_REQBUFS, &request) < 0)
        return -errno;
    q->count = request.count < MAX_BUFFERS ? request.count : MAX_BUFFERS;
    for (unsigned i = 0; i < q->count; i++) {
        struct v4l2_plane planes[VIDEO_MAX_PLANES] = { 0 };
        struct v4l2_buffer buffer = { .index = i, .type = q->type, .memory = V4L2_MEMORY_MMAP,
                                      .length = VIDEO_MAX_PLANES, .m.planes = planes };
        if (!m->mplane)
            buffer = (struct v4l2_buffer){ .index = i, .type = q->type, .memory = V4L2_MEMORY_MMAP };
        if (ioctl(fd, VIDIOC_QUERYBUF, &buffer) < 0)
            return -errno;
        if (!m->mplane)
            planes[0] = (struct v4l2_plane){ .length = buffer.length,
                                             .m.mem_offset = buffer.m.offset };
        unsigned count_planes = m->mplane ? buffer.length : 1;
        for (unsigned p = 0; p < count_planes && p < PICTURE_PLANES; p++) {
            struct m2m_buffer *b = &q->buffers[i];
            b->length[p] = planes[p].length;
            b->map[p] = mmap(NULL, planes[p].length, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
                             planes[p].m.mem_offset);
            if (b->map[p] == MAP_FAILED)
                return b->map[p] = NULL, -errno;
            struct v4l2_exportbuffer exported = { .type = q->type, .index = i, .plane = p,
                                                  .flags = O_RDONLY | O_CLOEXEC };
            if (export && ioctl(fd, VIDIOC_EXPBUF, &exported) < 0)
                return -errno;
            b->fds[p] = export ? exported.fd : -1;
        }
    }
    return 0;
}

static int queue_buffer(const struct m2m *m, struct m2m_queue *q, unsigned index, size_t bytes,
                        unsigned timestamp)
{
    unsigned planes_used = num_planes(m, q);
    struct v4l2_plane planes[VIDEO_MAX_PLANES] = { 0 };
    struct v4l2_buffer buffer = { .index = index, .type = q->type, .memory = V4L2_MEMORY_MMAP,
                                  .timestamp = { .tv_usec = timestamp } };
    const struct m2m_buffer *b = &q->buffers[index];
    if (m->mplane) {
        buffer.length = planes_used;
        buffer.m.planes = planes;
        for (unsigned p = 0; p < planes_used; p++)
            planes[p].bytesused = bytes == WHOLE_PLANES ? b->length[p] : p ? 0 : bytes;
    } else {
        buffer.bytesused = bytes == WHOLE_PLANES ? b->length[0] : bytes;
    }
    if (ioctl(m->fd, VIDIOC_QBUF, &buffer) < 0)
        return -errno;
    q->buffers[index].queued = true;
    return 0;
}

/* planes[0].bytesused says what came back, single-planar or not */
static int dequeue_buffer(const struct m2m *m, struct m2m_queue *q, struct v4l2_buffer *buffer,
                          struct v4l2_plane *planes)
{
    *buffer = (struct v4l2_buffer){ .type = q->type, .memory = V4L2_MEMORY_MMAP };
    if (m->mplane) {
        buffer->length = VIDEO_MAX_PLANES;
        buffer->m.planes = planes;
    }
    if (ioctl(m->fd, VIDIOC_DQBUF, buffer) < 0)
        return -errno;
    if (!m->mplane)
        planes[0].bytesused = buffer->bytesused;
    q->buffers[buffer->index].queued = false;
    return 0;
}

static int stream(int fd, struct m2m_queue *q, bool on)
{
    enum v4l2_buf_type type = q->type;
    if (ioctl(fd, on ? VIDIOC_STREAMON : VIDIOC_STREAMOFF, &type) < 0)
        return -errno;
    q->streaming = on;
    return 0;
}

static void m2m_put(struct m2m *m)
{
    if (--m->refs)
        return;
    unmap_queue(&m->output);
    unmap_queue(&m->capture);
    close(m->fd);
    free(m);
}

/* what becomes of the codecs whose decoder holds its last pictures until more stream comes, when
 * a client syncs on one first: the drain that frees it costs the next pictures their references */
enum held_pictures {
    /* offered; a picture that lost its references is refused */
    HELD_REFUSE,
    /* not offered */
    HELD_OFF,
    /* offered; every picture handed out as decoded */
    HELD_DECODED,
};

#define HELD_ENV "VAAPI_HELD_PICTURES"
#define HELD_KEY "held-pictures"

static enum held_pictures held_pictures = HELD_REFUSE;

static enum held_pictures held_setting(void)
{
    const char *value = setting(HELD_ENV, HELD_KEY);
    if (value && !strcmp(value, "off"))
        return HELD_OFF;
    if (value && !strcmp(value, "decoded"))
        return HELD_DECODED;
    return HELD_REFUSE;
}

static bool holds_pictures(uint32_t pixelformat)
{
    return pixelformat == V4L2_PIX_FMT_MPEG2 || pixelformat == V4L2_PIX_FMT_MPEG4 ||
           pixelformat == V4L2_PIX_FMT_VC1_ANNEX_G;
}

static int m2m_init(struct driver *drv)
{
    static struct v4l2_candidate kept[NUM_CANDIDATES];
    static struct offer offers[NUM_CANDIDATES];
    unsigned count = 0;
    held_pictures = held_setting();
    for (unsigned i = 0; i < NUM_CANDIDATES; i++)
        if (held_pictures != HELD_OFF || !holds_pictures(m2m_candidates[i].pixelformat))
            kept[count++] = m2m_candidates[i];
    drv->offers = offers;
    drv->num_offers = v4l2_offers(kept, count, offers);
    return drv->num_offers ? 0 : -ENODEV;
}

static void m2m_uninit(struct driver *drv)
{
}

/* a COMPOSE rectangle on CAPTURE: the decoder scales by 1, 2 or 4 to fit it */
static int request_scaling(const struct m2m *m)
{
    struct v4l2_selection compose = {
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .target = V4L2_SEL_TGT_COMPOSE,
        .flags = V4L2_SEL_FLAG_LE,
        .r = { .width = m->scaled_width, .height = m->scaled_height },
    };
    if (!m->scaled_width)
        return 0;
    if (ioctl(m->fd, VIDIOC_S_SELECTION, &compose) < 0)
        return -errno;
    return compose.r.width == m->scaled_width && compose.r.height == m->scaled_height ? 0
                                                                                      : -ENOTSUP;
}

/* one CAPTURE buffer's bytes, every plane */
static size_t picture_bytes(const struct m2m *m)
{
    const struct v4l2_format *f = &m->capture.format;
    size_t bytes = 0;
    for (unsigned p = 0; m->mplane && p < f->fmt.pix_mp.num_planes; p++)
        bytes += f->fmt.pix_mp.plane_fmt[p].sizeimage;
    return m->mplane ? (bytes ? bytes : 1) : (f->fmt.pix.sizeimage ? f->fmt.pix.sizeimage : 1);
}

/* the DRM format of CAPTURE's pictures, 0 for one the driver does not read */
static uint32_t drm_format_of_capture(const struct m2m *m)
{
    switch (pixel_format(m, &m->capture)) {
    case V4L2_PIX_FMT_NV12M:
    case V4L2_PIX_FMT_NV12:
        return DRM_FORMAT_NV12;
    case V4L2_PIX_FMT_YUV420M:
        return DRM_FORMAT_YUV420;
    default:
        return 0;
    }
}

/* the decoder told its picture size: CAPTURE again, held pictures orphaned, not waited for */
static int setup_capture(struct m2m *m)
{
    struct v4l2_control min_buffers = { .id = V4L2_CID_MIN_BUFFERS_FOR_CAPTURE };
    if (m->capture.streaming)
        stream(m->fd, &m->capture, false);
    unmap_queue(&m->capture);
    struct v4l2_requestbuffers release = { .type = m->capture.type, .memory = V4L2_MEMORY_MMAP };
    ioctl(m->fd, VIDIOC_REQBUFS, &release);
    m->generation++;
    int ret = request_scaling(m);
    if (ret < 0)
        return ret;
    m->capture.format.type = m->capture.type;
    if (ioctl(m->fd, VIDIOC_G_FMT, &m->capture.format) < 0)
        return -errno;
    /* NV12 asked for; a decoder that writes three planes alone, as meson's MJPEG, is taken so,
     * and anything else refused */
    uint32_t nv12 = m->mplane ? V4L2_PIX_FMT_NV12M : V4L2_PIX_FMT_NV12;
    if (pixel_format(m, &m->capture) != nv12) {
        if (m->mplane)
            m->capture.format.fmt.pix_mp.pixelformat = nv12;
        else
            m->capture.format.fmt.pix.pixelformat = nv12;
        if (ioctl(m->fd, VIDIOC_S_FMT, &m->capture.format) < 0)
            return -errno;
    }
    if (!drm_format_of_capture(m))
        return -ENOTSUP;
    ioctl(m->fd, VIDIOC_G_CTRL, &min_buffers);
    unsigned needed = min_buffers.value + m->num_targets;
    unsigned budget = CAPTURE_BUDGET / picture_bytes(m);
    unsigned count = needed + (budget > needed + EXTRA_CAPTURE ? EXTRA_CAPTURE
                               : budget > needed             ? budget - needed
                                                             : 1);
    count = count < MAX_BUFFERS ? count : MAX_BUFFERS;
    ret = setup_queue(m, &m->capture, count, true);
    m->copies_out = m->capture.count < count;
    for (unsigned i = 0; !ret && i < m->capture.count; i++)
        ret = queue_buffer(m, &m->capture, i, 0, 0);
    return ret ? ret : stream(m->fd, &m->capture, true);
}

static void release_m2m_picture(struct engine_picture *picture)
{
    struct m2m_picture *p = (struct m2m_picture *)picture;
    struct m2m *m = p->m;
    if (p->generation == m->generation && m->capture.streaming)
        queue_buffer(m, &m->capture, p->index, 0, 0);
    for (unsigned i = 0; i < p->base.num_objects; i++)
        close(p->base.fds[i]);
    free(p);
    m2m_put(m);
}

static struct engine_picture *picture_of(struct m2m *m, unsigned index)
{
    const struct m2m_queue *q = &m->capture;
    const struct m2m_buffer *b = &q->buffers[index];
    struct m2m_picture *p = calloc(1, sizeof(*p));
    unsigned objects = num_planes(m, q);
    unsigned height = format_height(m, q);
    if (!p)
        return NULL;
    *p = (struct m2m_picture){ .m = m, .index = index, .generation = m->generation };
    p->base = (struct engine_picture){
        .drm_format = drm_format_of_capture(m),
        .modifier = DRM_FORMAT_MOD_LINEAR,
        .width = format_width(m, q),
        .height = height,
        .num_objects = objects,
        .release = release_m2m_picture,
    };
    if (objects == 1) {
        /* single-plane NV12: chroma follows luma in the one buffer */
        p->base.plane_offset[1] = bytes_per_line(m, q, 0) * height;
        p->base.plane_pitch[0] = p->base.plane_pitch[1] = bytes_per_line(m, q, 0);
    } else {
        for (unsigned i = 0; i < objects; i++) {
            p->base.plane_object[i] = i;
            p->base.plane_pitch[i] = bytes_per_line(m, q, i);
        }
    }
    for (unsigned i = 0; i < p->base.num_objects; i++) {
        p->base.fds[i] = dup(b->fds[i]);
        p->base.sizes[i] = b->length[i];
    }
    m->refs++;
    return &p->base;
}

/* one decoded picture onto the surface it was stamped with; a picture for none goes back */
static int deliver(struct driver *drv, struct m2m *m, const struct v4l2_buffer *buffer,
                   size_t bytesused)
{
    struct surface *s = surface_of(drv, buffer->timestamp.tv_usec);
    if (!bytesused || buffer->flags & V4L2_BUF_FLAG_ERROR || !s)
        return queue_buffer(m, &m->capture, buffer->index, 0, 0);
    struct engine_picture *p = picture_of(m, buffer->index);
    int ret = p ? surface_bind_picture(s, p) : -ENOMEM;
    return ret || !m->copies_out ? ret : surface_ensure_backing(s);
}

/* every decoded picture ready, onto its surface: 1 if the wanted surface's came, -EPIPE at the
 * last of a drain */
static int take_pictures(struct driver *drv, struct m2m *m, VASurfaceID wanted)
{
    struct v4l2_plane planes[VIDEO_MAX_PLANES];
    struct v4l2_buffer buffer;
    int got = 0, ret;
    while (m->capture.streaming && !(ret = dequeue_buffer(m, &m->capture, &buffer, planes))) {
        if ((ret = deliver(drv, m, &buffer, planes[0].bytesused)) < 0)
            return ret;
        got |= buffer.timestamp.tv_usec == wanted && planes[0].bytesused;
        if (buffer.flags & V4L2_BUF_FLAG_LAST)
            return got ? 1 : -EPIPE;
    }
    return !m->capture.streaming || ret == -EAGAIN ? got : ret;
}

/* events, finished OUTPUT buffers and decoded pictures: 1 once the wanted surface has its
 * picture, -EPIPE once a drain has ended, 0 when nothing came for timeout_ms. Pictures of the old
 * size come out before CAPTURE is set up for a new one. */
static int service(struct driver *drv, struct m2m *m, VASurfaceID wanted, int timeout_ms)
{
    struct pollfd pfd = { .fd = m->fd, .events = POLLIN | POLLPRI };
    while (poll(&pfd, 1, timeout_ms) > 0) {
        m->active_ms = monotonic_ms();
        struct v4l2_plane planes[VIDEO_MAX_PLANES];
        struct v4l2_buffer buffer;
        struct v4l2_event event;
        if (pfd.revents & POLLERR)
            return -EIO;
        bool changed = pfd.revents & POLLPRI && !ioctl(m->fd, VIDIOC_DQEVENT, &event) &&
                       event.type == V4L2_EVENT_SOURCE_CHANGE;
        while (!dequeue_buffer(m, &m->output, &buffer, planes))
            ;
        int ret = pfd.revents & POLLIN || changed ? take_pictures(drv, m, wanted) : 0;
        int set_up = changed ? setup_capture(m) : 0;
        if (ret || set_up < 0)
            return set_up < 0 ? set_up : ret;
    }
    return 0;
}

static void set_control(int fd, uint32_t id, int value)
{
    struct v4l2_control control = { .id = id, .value = value };
    ioctl(fd, VIDIOC_S_CTRL, &control);
}

static int m2m_decoder_open(struct driver *drv, struct context *ctx)
{
    uint32_t pixelformat = coded_format(ctx->config->codec->kind);
    struct m2m *m = calloc(1, sizeof(*m));
    struct v4l2_event_subscription changes = { .type = V4L2_EVENT_SOURCE_CHANGE };
    if (!m)
        return -ENOMEM;
    *m = (struct m2m){ .refs = 1, .num_targets = ctx->num_targets };
    ctx->engine = m;
    if ((m->fd = open_device(m, true, pixelformat)) < 0)
        return m->fd;
    set_format(m, &m->output, pixelformat, ctx->width, ctx->height, CODED_BUFFER_SIZE);
    if (ioctl(m->fd, VIDIOC_S_FMT, &m->output.format) < 0)
        return -errno;
    if (clamped(m, &m->output, ctx->width, ctx->height))
        return -ERANGE;
    /* a format the decoder cannot size itself, as meson's MPEG, waits for CAPTURE to stream */
    m->announces_size = m->dynamic_resolution && !ioctl(m->fd, VIDIOC_SUBSCRIBE_EVENT, &changes);
    int ret = setup_queue(m, &m->output, OUTPUT_BUFFERS, false);
    return ret ? ret : stream(m->fd, &m->output, true);
}

static int free_output(struct m2m *m)
{
    for (unsigned i = 0; i < m->output.count; i++)
        if (!m->output.buffers[i].queued)
            return i;
    return -EAGAIN;
}

static int m2m_decode(struct driver *drv, struct context *ctx, const struct annexb *au)
{
    struct m2m *m = ctx->engine;
    int index, ret;

    /* taken at the next source change: the first picture's, before CAPTURE exists */
    m->scaled_width = ctx->scaled_width;
    m->scaled_height = ctx->scaled_height;
    /* refused rather than decoded wrong, until a picture that predicts from nothing */
    if (m->lost_references && ctx->packet.predicted && held_pictures == HELD_REFUSE)
        return -ENODATA;
    m->lost_references = false;
    while ((index = free_output(m)) < 0)
        if ((ret = service(drv, m, VA_INVALID_ID, OUTPUT_WAIT_MS)) < 0 ||
            (index = free_output(m)) < 0)
            return ret < 0 ? ret : -ETIMEDOUT;
    if (au->size > m->output.buffers[index].length[0])
        return -E2BIG;
    memcpy(m->output.buffers[index].map[0], au->data, au->size);
    /* stamped always: an unstamped packet's pictures all came back at 0 */
    if ((ret = queue_buffer(m, &m->output, index, au->size, ctx->target)) < 0)
        return ret;
    m->active_ms = monotonic_ms();
    if (!m->announces_size && !m->capture.streaming && (ret = setup_capture(m)) < 0)
        return ret;
    /* what is done already; a picture still held is sync's to wait for */
    ret = service(drv, m, ctx->target, 0);
    return ret < 0 ? ret : 0;
}

static void m2m_close(struct context *ctx)
{
    struct m2m *m = ctx->engine;
    if (!m)
        return;
    if (m->fd >= 0) {
        stream(m->fd, &m->output, false);
        if (m->capture.streaming)
            stream(m->fd, &m->capture, false);
    }
    m->capture.streaming = false;
    m2m_put(m);
    ctx->engine = NULL;
}

static int m2m_encoder_open(struct driver *drv, struct context *ctx, const struct encode_params *p)
{
    uint32_t pixelformat = coded_format(p->codec);
    struct m2m *m = calloc(1, sizeof(*m));
    if (!m)
        return -ENOMEM;
    *m = (struct m2m){ .refs = 1 };
    ctx->engine = m;
    if ((m->fd = open_device(m, false, pixelformat)) < 0)
        return m->fd;
    set_format(m, &m->capture, pixelformat, p->width, p->height, CODED_BUFFER_SIZE);
    set_format(m, &m->output, m->mplane ? V4L2_PIX_FMT_NV12M : V4L2_PIX_FMT_NV12, p->width,
               p->height, 0);
    struct v4l2_streamparm rate = { .type = m->output.type };
    rate.parm.output.timeperframe = (struct v4l2_fract){ p->frame_rate_den, p->frame_rate_num };
    if (ioctl(m->fd, VIDIOC_S_FMT, &m->capture.format) < 0 ||
        ioctl(m->fd, VIDIOC_S_FMT, &m->output.format) < 0)
        return -errno;
    if (clamped(m, &m->output, p->width, p->height))
        return -ERANGE;
    ioctl(m->fd, VIDIOC_S_PARM, &rate);
    if (p->codec == CODEC_JPEG) {
        set_control(m->fd, V4L2_CID_JPEG_COMPRESSION_QUALITY, p->jpeg_quality);
    } else {
        bool cqp = p->rate_control & VA_RC_CQP;
        set_control(m->fd, V4L2_CID_MPEG_VIDEO_GOP_SIZE, p->intra_period);
        set_control(m->fd, V4L2_CID_MPEG_VIDEO_FRAME_RC_ENABLE, !cqp);
        set_control(m->fd, V4L2_CID_MPEG_VIDEO_BITRATE_MODE,
                    p->rate_control & VA_RC_CBR ? V4L2_MPEG_VIDEO_BITRATE_MODE_CBR
                                                : V4L2_MPEG_VIDEO_BITRATE_MODE_VBR);
        set_control(m->fd, V4L2_CID_MPEG_VIDEO_BITRATE,
                    cqp ? 0 : p->bit_rate / PERCENT * p->target_percent);
        set_control(m->fd, V4L2_CID_MPEG_VIDEO_BITRATE_PEAK, p->bit_rate);
        bool hevc = p->codec == CODEC_HEVC;
        set_control(m->fd, hevc ? V4L2_CID_MPEG_VIDEO_HEVC_I_FRAME_QP
                                : V4L2_CID_MPEG_VIDEO_H264_I_FRAME_QP, p->qp);
        set_control(m->fd, hevc ? V4L2_CID_MPEG_VIDEO_HEVC_P_FRAME_QP
                                : V4L2_CID_MPEG_VIDEO_H264_P_FRAME_QP, p->qp);
    }
    int ret = setup_queue(m, &m->output, OUTPUT_BUFFERS, false);
    if (!ret)
        ret = setup_queue(m, &m->capture, OUTPUT_BUFFERS, false);
    for (unsigned i = 0; !ret && i < m->capture.count; i++)
        ret = queue_buffer(m, &m->capture, i, 0, 0);
    if (!ret)
        ret = stream(m->fd, &m->output, true);
    return ret ? ret : stream(m->fd, &m->capture, true);
}

/* the surface's NV12 into the encoder's buffer, plane for plane at its stride */
static void copy_input(const struct m2m *m, unsigned index, const struct backing *b,
                       unsigned height)
{
    const struct m2m_queue *q = &m->output;
    const struct m2m_buffer *dst = &q->buffers[index];
    bool two_planes = num_planes(m, q) == 2;
    unsigned pitch = bytes_per_line(m, q, 0);
    uint8_t *luma = dst->map[0];
    uint8_t *chroma = two_planes ? dst->map[1] : luma + (size_t)pitch * format_height(m, q);
    unsigned chroma_pitch = bytes_per_line(m, q, two_planes);
    unsigned bytes = pitch < b->pitch ? pitch : b->pitch;
    for (unsigned row = 0; row < height; row++)
        memcpy(luma + (size_t)row * pitch, b->map + (size_t)row * b->pitch, bytes);
    for (unsigned row = 0; row < (height + 1) / 2; row++)
        memcpy(chroma + (size_t)row * chroma_pitch,
               b->map + b->chroma_offset + (size_t)row * b->pitch, bytes);
}

static int m2m_encode(struct context *ctx, struct surface *input, bool idr, struct annexb *out)
{
    struct m2m *m = ctx->engine;
    struct v4l2_plane planes[VIDEO_MAX_PLANES];
    struct v4l2_buffer buffer;
    struct pollfd pfd = { .fd = m->fd, .events = POLLIN };
    int index = free_output(m), ret;

    while (index < 0 && !dequeue_buffer(m, &m->output, &buffer, planes))
        index = buffer.index;
    if (index < 0)
        return -EAGAIN;
    copy_input(m, index, input->backing, input->height);
    if (idr)
        set_control(m->fd, V4L2_CID_MPEG_VIDEO_FORCE_KEY_FRAME, 1);
    if ((ret = queue_buffer(m, &m->output, index, WHOLE_PLANES, 0)) < 0)
        return ret;
    if (poll(&pfd, 1, ENCODE_WAIT_MS) <= 0 || dequeue_buffer(m, &m->capture, &buffer, planes))
        return -ETIMEDOUT;
    ret = annexb_append_raw(out, m->capture.buffers[buffer.index].map[0], planes[0].bytesused);
    queue_buffer(m, &m->capture, buffer.index, 0, 0);
    return ret;
}

static int decoder_command(const struct m2m *m, uint32_t cmd)
{
    struct v4l2_decoder_cmd command = { .cmd = cmd };
    return ioctl(m->fd, VIDIOC_DECODER_CMD, &command) < 0 ? -errno : 0;
}

/* the decoder holds pictures until later packets come, which a client waiting on one never sends:
 * once it is quiet it is drained, every picture it holds comes out, and the stream goes on in a new
 * session, its headers sent again. Meson's ends at a drain: V4L2_DEC_CMD_START does not resume it. */
static int m2m_sync(struct driver *drv, struct context *ctx, VASurfaceID id, bool last)
{
    struct m2m *m = ctx->engine;
    int ret;
    if (!m)
        return -ENODEV;
    if ((ret = service(drv, m, id, 0)) != 0)
        return ret < 0 ? ret : 0;
    if (!last && monotonic_ms() - m->active_ms < QUIET_MS)
        return 0;
    /* a decoder that cannot drain now, as Cedrus's JPEG, may still hand the picture out */
    if (decoder_command(m, V4L2_DEC_CMD_STOP) < 0)
        return (ret = service(drv, m, id, SYNC_WAIT_MS)) > 0 ? 0 : ret ? ret : -ETIMEDOUT;
    ret = service(drv, m, VA_INVALID_ID, SYNC_WAIT_MS);
    /* the old session stays while surfaces hold its pictures */
    m2m_close(ctx);
    int reopened = m2m_decoder_open(drv, ctx);
    if (ctx->engine)
        ((struct m2m *)ctx->engine)->lost_references = true;
    if (ctx->config->codec->restart)
        ctx->config->codec->restart(ctx->codec_state);
    if (ret != -EPIPE)
        return ret < 0 ? ret : -ETIMEDOUT;
    return reopened;
}

const struct backend backend_v4l2m2m = {
    .name = "v4l2m2m",
    .init = m2m_init,
    .uninit = m2m_uninit,
    .decoder_open = m2m_decoder_open,
    .decode = m2m_decode,
    .decoder_close = m2m_close,
    /* meson-codecs 0017: the HEVC and VP9 cores scale; the others have no scaler */
    .scaled_codecs = 1u << CODEC_HEVC | 1u << CODEC_VP9,
    .max_scale_factor = 4,
    .sync = m2m_sync,
    .encoder_open = m2m_encoder_open,
    .encode = m2m_encode,
    .encoder_close = m2m_close,
};
