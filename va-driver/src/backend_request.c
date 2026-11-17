/*
 * Cedrus, stateless: VA's parameters onto the V4L2 stateless controls, through the media
 * request API. Each surface decoded into gets a CAPTURE buffer of its own for the context's life,
 * lent to it as its own memory: the picture lands where export, derive and images read it.
 * Linear NV12 or P010, which Panfrost samples, or AFBC.
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <linux/media.h>

#include "request.h"
#include "v4l2.h"
/* after request.h: they need videodev2.h's types */
#include "mpeg4-ctrls.h"
#include "vc1-ctrls.h"

#define MEDIA_NODES "/sys/bus/media/devices"
#define CODED_BUFFER_SIZE (4 << 20)
#define REQUEST_TIMEOUT_MS 1000
#define USEC_TO_NSEC 1000
#define DUMP_ENV "VAAPI_REQUEST_DUMP"
#define TEN_BIT_DEPTH_MINUS8 2
#define VP9_PROFILE_2 2
#define TEN_BITS 10

/* linux-sunxi 0058: Cedrus's AFBC, for a client whose GPU samples it */
#ifndef V4L2_PIX_FMT_YUV420_8_AFBC_16X16_SPLIT
#define V4L2_PIX_FMT_YUV420_8_AFBC_16X16_SPLIT v4l2_fourcc('A', 'S', '1', '2')
#define V4L2_PIX_FMT_YUV420_10_AFBC_16X16_SPLIT v4l2_fourcc('A', 'S', '0', '1')
#endif
#define CEDRUS_AFBC                                                                                \
    DRM_FORMAT_MOD_ARM_AFBC(AFBC_FORMAT_MOD_BLOCK_SIZE_16x16 | AFBC_FORMAT_MOD_SPARSE |            \
                            AFBC_FORMAT_MOD_SPLIT)

#define VLD VAEntrypointVLD
#define H264_PROFILE V4L2_CID_MPEG_VIDEO_H264_PROFILE

/* what Cedrus may take; init keeps what its nodes do. The stateful nodes decode JPEG and encode. */
static const struct v4l2_candidate request_candidates[] = {
    { VAProfileH264ConstrainedBaseline, VLD, V4L2_PIX_FMT_H264_SLICE, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_CONSTRAINED_BASELINE, false },
    { VAProfileH264Main, VLD, V4L2_PIX_FMT_H264_SLICE, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_MAIN, false },
    { VAProfileH264High, VLD, V4L2_PIX_FMT_H264_SLICE, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_HIGH, false },
    { VAProfileHEVCMain, VLD, V4L2_PIX_FMT_HEVC_SLICE, V4L2_CID_MPEG_VIDEO_HEVC_PROFILE,
      V4L2_MPEG_VIDEO_HEVC_PROFILE_MAIN, false },
    { VAProfileHEVCMain10, VLD, V4L2_PIX_FMT_HEVC_SLICE, V4L2_CID_MPEG_VIDEO_HEVC_PROFILE,
      V4L2_MPEG_VIDEO_HEVC_PROFILE_MAIN_10, true },
    { VAProfileVP8Version0_3, VLD, V4L2_PIX_FMT_VP8_FRAME, 0, 0, false },
    { VAProfileVP9Profile0, VLD, V4L2_PIX_FMT_VP9_FRAME, V4L2_CID_MPEG_VIDEO_VP9_PROFILE,
      V4L2_MPEG_VIDEO_VP9_PROFILE_0, false },
    { VAProfileVP9Profile2, VLD, V4L2_PIX_FMT_VP9_FRAME, V4L2_CID_MPEG_VIDEO_VP9_PROFILE,
      V4L2_MPEG_VIDEO_VP9_PROFILE_2, true },
    { VAProfileMPEG2Simple, VLD, V4L2_PIX_FMT_MPEG2_SLICE, 0, 0, false },
    { VAProfileMPEG2Main, VLD, V4L2_PIX_FMT_MPEG2_SLICE, 0, 0, false },
    { VAProfileMPEG4Simple, VLD, V4L2_PIX_FMT_MPEG4_SLICE, 0, 0, false },
    { VAProfileMPEG4AdvancedSimple, VLD, V4L2_PIX_FMT_MPEG4_SLICE, 0, 0, false },
    { VAProfileH263Baseline, VLD, V4L2_PIX_FMT_MPEG4_SLICE, 0, 0, false },
    /* linux-sunxi 0065: no Main profile */
    { VAProfileVC1Simple, VLD, V4L2_PIX_FMT_VC1_SLICE, 0, 0, false },
    { VAProfileVC1Advanced, VLD, V4L2_PIX_FMT_VC1_SLICE, 0, 0, false },
    { VAProfileJPEGBaseline, VLD, V4L2_PIX_FMT_MJPEG, 0, 0, false },
    { VAProfileH264ConstrainedBaseline, VAEntrypointEncSlice, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_CONSTRAINED_BASELINE, false },
    { VAProfileH264Main, VAEntrypointEncSlice, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_MAIN, false },
    /* a Main stream is a High one: clients ask High first */
    { VAProfileH264High, VAEntrypointEncSlice, V4L2_PIX_FMT_H264, H264_PROFILE,
      V4L2_MPEG_VIDEO_H264_PROFILE_MAIN, false },
    { VAProfileJPEGBaseline, VAEntrypointEncPicture, V4L2_PIX_FMT_MJPEG, 0, 0, false },
};

#define NUM_CANDIDATES (sizeof(request_candidates) / sizeof(request_candidates[0]))

extern const struct backend backend_v4l2m2m;

static bool is_stateful(const struct context *ctx)
{
    return ctx->config->codec->kind == CODEC_JPEG;
}

static const struct request_codec *codec_for(enum codec_kind kind)
{
    switch (kind) {
    case CODEC_H264:
        return &request_h264;
    case CODEC_MPEG2:
        return &request_mpeg2;
    case CODEC_HEVC:
        return &request_hevc;
    case CODEC_VP8:
        return &request_vp8;
    case CODEC_VP9:
        return &request_vp9;
    case CODEC_MPEG4:
        return &request_mpeg4;
    case CODEC_VC1:
        return &request_vc1;
    default:
        return NULL;
    }
}

/* the surface's CAPTURE buffer; -1 for none yet */
static int capture_of(const struct request_ctx *rq, VASurfaceID surface)
{
    for (unsigned i = 0; i < rq->num_captures; i++)
        if (rq->captures[i].surface == surface)
            return i;
    return -1;
}

/* the buffer holding the surface's latest picture; -1 for none */
static int latest_of(const struct request_ctx *rq, VASurfaceID surface)
{
    int index = capture_of(rq, surface);
    return index < 0 ? -1 : rq->captures[index].latest;
}

/* decoded into again: no surface's latest picture is there any more */
static void forget_buffer(struct request_ctx *rq, unsigned index)
{
    for (unsigned i = 0; i < rq->num_captures; i++)
        if (rq->captures[i].latest == (int)index)
            rq->captures[i].latest = -1;
}

uint64_t request_timestamp(const struct request_ctx *rq, VASurfaceID surface)
{
    int latest = latest_of(rq, surface);
    return latest < 0 ? 0 : rq->captures[latest].timestamp * USEC_TO_NSEC;
}

void request_dump(struct request_ctx *rq, const char *name, long value)
{
    if (rq->dump)
        fprintf(rq->dump, "%u %s %ld\n", rq->dump_picture, name, value);
}

static int try_media(const char *path, void *arg)
{
    const struct v4l2_capability *cap = arg;
    struct media_device_info info;
    int fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0)
        return -1;
    if (!ioctl(fd, MEDIA_IOC_DEVICE_INFO, &info) &&
        !strncmp(info.bus_info, (const char *)cap->bus_info, sizeof(info.bus_info)))
        return fd;
    close(fd);
    return -1;
}

/* the video device taking this coded format, and the media device sharing its bus */
static int open_devices(struct request_ctx *rq, uint32_t pixelformat)
{
    struct v4l2_capability cap;
    bool mplane;
    uint32_t flags;
    rq->video_fd = v4l2_open_coded(pixelformat, true, &mplane, &flags);
    if (rq->video_fd < 0)
        return -ENODEV;
    if (ioctl(rq->video_fd, VIDIOC_QUERYCAP, &cap) < 0)
        return -errno;
    rq->media_fd = v4l2_each_node(MEDIA_NODES, "media", try_media, &cap);
    return rq->media_fd >= 0 ? 0 : -ENODEV;
}

int request_get_control(struct request_ctx *rq, uint32_t id, int *value)
{
    struct v4l2_ext_control control = { .id = id };
    struct v4l2_ext_controls controls = { .count = 1, .controls = &control };
    if (rq->dump)
        return -ENODEV;
    if (ioctl(rq->video_fd, VIDIOC_G_EXT_CTRLS, &controls) < 0)
        return -errno;
    *value = control.value;
    return 0;
}

static int stream(int fd, enum v4l2_buf_type type, bool on)
{
    return ioctl(fd, on ? VIDIOC_STREAMON : VIDIOC_STREAMOFF, &type) < 0 ? -errno : 0;
}

/* CAPTURE buffer index exported, for no surface yet */
static int setup_capture(struct request_ctx *rq, unsigned index)
{
    struct v4l2_exportbuffer exported = { .type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .index = index,
                                          .flags = O_RDWR | O_CLOEXEC };
    struct capture_buffer *c = &rq->captures[index];
    struct stat st;
    *c = (struct capture_buffer){ .surface = VA_INVALID_SURFACE, .fd = -1, .latest = -1 };
    rq->num_captures = index + 1;
    if (rq->dump)
        return 0;
    if (ioctl(rq->video_fd, VIDIOC_EXPBUF, &exported) < 0)
        return -errno;
    c->fd = exported.fd;
    /* the dma-buf's own size, whole pages, as importers check it */
    off_t size = lseek(c->fd, 0, SEEK_END);
    if (size < 0 || fstat(c->fd, &st) < 0)
        return -errno;
    c->size = size;
    c->inode = st.st_ino;
    return 0;
}

/* the surface's CAPTURE buffer: its own already, a destroyed surface's, or a new one */
static int assign_capture(struct request_ctx *rq, VASurfaceID surface)
{
    int index = capture_of(rq, surface);
    for (unsigned i = 0; i < rq->num_captures && index < 0; i++)
        if (!surface_of(rq->drv, rq->captures[i].surface))
            index = i;
    if (index < 0) {
        struct v4l2_create_buffers create = { .count = 1, .memory = V4L2_MEMORY_MMAP,
                                              .format = rq->capture };
        if (rq->num_captures == REQUEST_MAX_CAPTURES)
            return -ENOBUFS;
        if (!rq->dump && ioctl(rq->video_fd, VIDIOC_CREATE_BUFS, &create) < 0)
            return -errno;
        index = rq->dump ? (int)rq->num_captures : (int)create.index;
        int ret = setup_capture(rq, index);
        if (ret < 0)
            return ret;
    }
    if (rq->captures[index].surface != surface)
        rq->captures[index] = (struct capture_buffer){ .surface = surface,
                                                       .fd = rq->captures[index].fd,
                                                       .inode = rq->captures[index].inode,
                                                       .size = rq->captures[index].size,
                                                       .latest = -1 };
    return index;
}

static uint32_t surface_fourcc_of_capture(const struct request_ctx *rq)
{
    switch (rq->capture.fmt.pix.pixelformat) {
    case V4L2_PIX_FMT_NV12:
        return VA_FOURCC_NV12;
    case V4L2_PIX_FMT_P010:
        return VA_FOURCC_P010;
    default:
        return 0;
    }
}

/* the buffer as the surface's own memory, where it has none and takes the layout; whether the
 * buffer is the surface's memory now */
static int lend_capture(struct request_ctx *rq, const struct capture_buffer *c, struct surface *s)
{
    const struct v4l2_pix_format *f = &rq->capture.fmt.pix;
    const struct backing_layout layout = { f->bytesperline, f->bytesperline * f->height, c->size };
    struct stat st;
    int ret;
    if (!s->backing && s->fourcc == surface_fourcc_of_capture(rq) &&
        (ret = surface_adopt_backing(s, dup(c->fd), &layout)) < 0)
        return ret;
    return s->backing && !fstat(s->backing->fd, &st) && st.st_ino == c->inode;
}

static int wait_request(int request_fd)
{
    struct pollfd pfd = { .fd = request_fd, .events = POLLPRI };
    int ready = poll(&pfd, 1, REQUEST_TIMEOUT_MS);
    return ready > 0 ? 0 : ready ? -errno : -ETIMEDOUT;
}

static int dequeue(int fd, enum v4l2_buf_type type)
{
    struct v4l2_buffer buffer = { .type = type, .memory = V4L2_MEMORY_MMAP };
    if (ioctl(fd, VIDIOC_DQBUF, &buffer) < 0)
        return -errno;
    return buffer.flags & V4L2_BUF_FLAG_ERROR ? -EIO : 0;
}

/* after a request that failed or never completed: both queues stopped, which cancels it, and
 * started again; the pictures already decoded keep their buffers */
static void reset_queues(struct request_ctx *rq)
{
    stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_OUTPUT, false);
    stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, false);
    ioctl(rq->request_fd, MEDIA_REQUEST_IOC_REINIT);
    stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_OUTPUT, true);
    stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, true);
}

static int queue_capture(struct request_ctx *rq)
{
    struct v4l2_buffer buffer = { .index = rq->target, .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
                                  .memory = V4L2_MEMORY_MMAP };
    return ioctl(rq->video_fd, VIDIOC_QBUF, &buffer) < 0 ? -errno : 0;
}

static int submit_request(struct request_ctx *rq, struct v4l2_ext_control *controls,
                          unsigned count, const struct annexb *data, bool first, bool last)
{
    struct v4l2_ext_controls set = { .which = V4L2_CTRL_WHICH_REQUEST_VAL,
                                     .request_fd = rq->request_fd, .count = count,
                                     .controls = controls };
    struct v4l2_buffer output = {
        .index = 0,
        .type = V4L2_BUF_TYPE_VIDEO_OUTPUT,
        .memory = V4L2_MEMORY_MMAP,
        .bytesused = data->size,
        .timestamp = { .tv_usec = rq->captures[rq->target].timestamp },
        .flags = V4L2_BUF_FLAG_REQUEST_FD | (last ? 0 : V4L2_BUF_FLAG_M2M_HOLD_CAPTURE_BUF),
        .request_fd = rq->request_fd,
    };
    int ret;
    memcpy(rq->output_map, data->data, data->size);
    if ((count && ioctl(rq->video_fd, VIDIOC_S_EXT_CTRLS, &set) < 0) ||
        ioctl(rq->video_fd, VIDIOC_QBUF, &output) < 0)
        return -errno;
    if (first && (ret = queue_capture(rq)) < 0)
        return ret;
    if (ioctl(rq->request_fd, MEDIA_REQUEST_IOC_QUEUE) < 0)
        return -errno;
    if ((ret = wait_request(rq->request_fd)) < 0 ||
        (ret = dequeue(rq->video_fd, V4L2_BUF_TYPE_VIDEO_OUTPUT)) < 0)
        return ret;
    return last ? dequeue(rq->video_fd, V4L2_BUF_TYPE_VIDEO_CAPTURE) : 0;
}

/* synchronous: each request waited for, so a picture is whole when vaEndPicture returns */
int request_queue(struct request_ctx *rq, struct v4l2_ext_control *controls, unsigned count,
                  const struct annexb *data, bool first, bool last)
{
    if (rq->dump) {
        request_dump(rq, "request_bytes", data->size);
        return 0;
    }
    if (data->size > rq->output_length)
        return -E2BIG;
    int ret = submit_request(rq, controls, count, data, first, last);
    if (ret < 0)
        reset_queues(rq);
    else
        ioctl(rq->request_fd, MEDIA_REQUEST_IOC_REINIT);
    return ret;
}

int request_repeat_reference(struct request_ctx *rq, VASurfaceID reference)
{
    rq->repeated = latest_of(rq, reference);
    return rq->repeated < 0 && !rq->dump ? -EINVAL : 0;
}

/* the side a probe holds still while the other grows */
#define PROBE_SIDE 64
#define PROBE_STEP 16

/* whether Cedrus takes a 10-bit stream's header at this size: it checks 10-bit sizes there, which
 * TRY_FMT cannot know. A fresh context, as a header taken sets the context's depth. */
static bool takes_ten_bit(VAProfile profile, unsigned width, unsigned height)
{
    bool hevc = profile == VAProfileHEVCMain10, mplane;
    struct v4l2_ctrl_hevc_sps sps = { .pic_width_in_luma_samples = width,
                                      .pic_height_in_luma_samples = height,
                                      .bit_depth_luma_minus8 = 2,
                                      .bit_depth_chroma_minus8 = 2,
                                      .chroma_format_idc = 1 };
    struct v4l2_ctrl_vp9_frame frame = { .frame_width_minus_1 = width - 1,
                                         .frame_height_minus_1 = height - 1,
                                         .flags = V4L2_VP9_FRAME_FLAG_X_SUBSAMPLING |
                                                  V4L2_VP9_FRAME_FLAG_Y_SUBSAMPLING,
                                         .bit_depth = 10,
                                         .profile = 2 };
    struct v4l2_ext_control control = {
        .id = hevc ? V4L2_CID_STATELESS_HEVC_SPS : V4L2_CID_STATELESS_VP9_FRAME,
        .size = hevc ? sizeof(sps) : sizeof(frame),
        .ptr = hevc ? (void *)&sps : (void *)&frame,
    };
    struct v4l2_ext_controls controls = { .which = V4L2_CTRL_WHICH_CUR_VAL, .count = 1,
                                          .controls = &control };
    uint32_t flags, pixelformat = hevc ? V4L2_PIX_FMT_HEVC_SLICE : V4L2_PIX_FMT_VP9_FRAME;
    int fd = v4l2_open_coded(pixelformat, true, &mplane, &flags);
    if (fd < 0)
        return false;
    /* the context checks the headers of the codec it is set to */
    struct v4l2_format format = { .type = mplane ? V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE
                                                 : V4L2_BUF_TYPE_VIDEO_OUTPUT };
    if (mplane)
        format.fmt.pix_mp = (struct v4l2_pix_format_mplane){ .width = width, .height = height,
                                                             .pixelformat = pixelformat };
    else
        format.fmt.pix = (struct v4l2_pix_format){ .width = width, .height = height,
                                                   .pixelformat = pixelformat };
    bool taken = !ioctl(fd, VIDIOC_S_FMT, &format) && !ioctl(fd, VIDIOC_TRY_EXT_CTRLS, &controls);
    close(fd);
    return taken;
}

/* the largest side up to max, in steps, a 10-bit header is taken at */
static unsigned ten_bit_side(VAProfile profile, unsigned max, bool width)
{
    unsigned low = PROBE_SIDE / PROBE_STEP, high = max / PROBE_STEP;
    while (low < high) {
        unsigned mid = (low + high + 1) / 2, side = mid * PROBE_STEP;
        bool taken = width ? takes_ten_bit(profile, side, PROBE_SIDE)
                           : takes_ten_bit(profile, PROBE_SIDE, side);
        if (taken)
            low = mid;
        else
            high = mid - 1;
    }
    return low * PROBE_STEP;
}

/* a 10-bit offer sized by the headers Cedrus takes; one taken at no size says nothing */
static void size_ten_bit(struct offer *o)
{
    if (!takes_ten_bit(o->profile, PROBE_SIDE, PROBE_SIDE))
        return;
    o->max_width = ten_bit_side(o->profile, o->max_width, true);
    o->max_height = ten_bit_side(o->profile, o->max_height, false);
}

static int request_init(struct driver *drv)
{
    static struct offer offers[NUM_CANDIDATES];
    /* the AFBC a decoder may list, as Cedrus does: kept by a context whose targets all list its
     * modifier and whose CAPTURE lists its format */
    drv->compressed_modifier = CEDRUS_AFBC;
    drv->offers = offers;
    drv->num_offers = v4l2_offers(request_candidates, NUM_CANDIDATES, offers);
    /* a dump without the device: the controls written are under test, not the decode */
    if (!drv->num_offers && getenv(DUMP_ENV))
        for (const struct v4l2_candidate *c = request_candidates; drv->num_offers < NUM_CANDIDATES;
             c++)
            offers[drv->num_offers++] = (struct offer){ .profile = c->profile,
                                                        .entrypoint = c->entrypoint };
    for (unsigned i = 0; i < drv->num_offers; i++)
        if (offers[i].profile == VAProfileHEVCMain10 || offers[i].profile == VAProfileVP9Profile2)
            size_ten_bit(&offers[i]);
    return drv->num_offers ? 0 : -ENODEV;
}

static void request_uninit(struct driver *drv)
{
}

/* the stream's depth, before CAPTURE's format: Cedrus lists 10-bit formats only once told */
static int announce_ten_bit(struct request_ctx *rq, enum codec_kind kind, unsigned width,
                            unsigned height)
{
    struct v4l2_ctrl_hevc_sps sps = {
        .pic_width_in_luma_samples = width,
        .pic_height_in_luma_samples = height,
        .bit_depth_luma_minus8 = TEN_BIT_DEPTH_MINUS8,
        .bit_depth_chroma_minus8 = TEN_BIT_DEPTH_MINUS8,
        .chroma_format_idc = 1,
    };
    struct v4l2_ctrl_vp9_frame frame = {
        .frame_width_minus_1 = width - 1,
        .frame_height_minus_1 = height - 1,
        .bit_depth = TEN_BITS,
        .profile = VP9_PROFILE_2,
        .flags = V4L2_VP9_FRAME_FLAG_X_SUBSAMPLING | V4L2_VP9_FRAME_FLAG_Y_SUBSAMPLING,
    };
    struct v4l2_ext_control control = kind == CODEC_HEVC
        ? (struct v4l2_ext_control){ .id = V4L2_CID_STATELESS_HEVC_SPS, .size = sizeof(sps),
                                     .ptr = &sps }
        : (struct v4l2_ext_control){ .id = V4L2_CID_STATELESS_VP9_FRAME, .size = sizeof(frame),
                                     .ptr = &frame };
    struct v4l2_ext_controls set = { .which = V4L2_CTRL_WHICH_CUR_VAL, .count = 1,
                                     .controls = &control };
    return ioctl(rq->video_fd, VIDIOC_S_EXT_CTRLS, &set) < 0 ? -errno : 0;
}

static uint32_t capture_format(const struct request_ctx *rq, bool ten_bit)
{
    if (rq->compressed_modifier)
        return ten_bit ? V4L2_PIX_FMT_YUV420_10_AFBC_16X16_SPLIT
                       : V4L2_PIX_FMT_YUV420_8_AFBC_16X16_SPLIT;
    return ten_bit ? V4L2_PIX_FMT_P010 : V4L2_PIX_FMT_NV12;
}

static int open_session(struct request_ctx *rq, const struct request_codec *codec,
                        const struct context *ctx)
{
    struct v4l2_format output = {
        .type = V4L2_BUF_TYPE_VIDEO_OUTPUT,
        .fmt.pix = { .pixelformat = codec->pixelformat, .width = ctx->width,
                     .height = ctx->height, .sizeimage = CODED_BUFFER_SIZE },
    };
    struct v4l2_requestbuffers outputs = { .count = 1, .type = V4L2_BUF_TYPE_VIDEO_OUTPUT,
                                           .memory = V4L2_MEMORY_MMAP };
    /* one to stream with, given a surface at its first picture; more as surfaces come */
    struct v4l2_requestbuffers captures = { .count = 1, .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
                                            .memory = V4L2_MEMORY_MMAP };
    struct v4l2_buffer mapped = { .index = 0, .type = V4L2_BUF_TYPE_VIDEO_OUTPUT,
                                  .memory = V4L2_MEMORY_MMAP };
    bool ten_bit = ctx->config->rt_format == VA_RT_FORMAT_YUV420_10;
    int ret;

    if ((ret = open_devices(rq, codec->pixelformat)) < 0)
        return ret;
    if (ioctl(rq->video_fd, VIDIOC_S_FMT, &output) < 0)
        return -errno;
    /* a size past the engine's comes back clamped */
    if (output.fmt.pix.width < (unsigned)ctx->width || output.fmt.pix.height < (unsigned)ctx->height)
        return -ERANGE;
    if (codec->init && (ret = codec->init(rq)) < 0)
        return ret;
    if (ten_bit && (ret = announce_ten_bit(rq, codec->kind, ctx->width, ctx->height)) < 0)
        return ret;
    /* compressed only where the decoder lists its format for this stream */
    if (rq->compressed_modifier &&
        !v4l2_queue_takes(rq->video_fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, capture_format(rq, ten_bit),
                          NULL))
        rq->compressed_modifier = 0;
    uint32_t wanted = capture_format(rq, ten_bit);
    rq->capture = (struct v4l2_format){
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .fmt.pix = { .pixelformat = wanted, .width = ctx->width, .height = ctx->height },
    };
    if (ioctl(rq->video_fd, VIDIOC_S_FMT, &rq->capture) < 0)
        return -errno;
    /* a format the driver did not keep would be read as one it is not */
    if (rq->capture.fmt.pix.pixelformat != wanted)
        return -ENOTSUP;
    if (rq->capture.fmt.pix.width < (unsigned)ctx->width ||
        rq->capture.fmt.pix.height < (unsigned)ctx->height)
        return -ERANGE;
    if (ioctl(rq->video_fd, VIDIOC_REQBUFS, &outputs) < 0 ||
        ioctl(rq->video_fd, VIDIOC_QUERYBUF, &mapped) < 0 ||
        ioctl(rq->video_fd, VIDIOC_REQBUFS, &captures) < 0 ||
        ioctl(rq->media_fd, MEDIA_IOC_REQUEST_ALLOC, &rq->request_fd) < 0)
        return -errno;
    if ((ret = setup_capture(rq, 0)) < 0)
        return ret;
    rq->output_length = mapped.length;
    rq->output_map = mmap(NULL, mapped.length, PROT_READ | PROT_WRITE, MAP_SHARED, rq->video_fd,
                          mapped.m.offset);
    if (rq->output_map == MAP_FAILED)
        return rq->output_map = NULL, -errno;
    if ((ret = stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_OUTPUT, true)) < 0)
        return ret;
    return stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, true);
}

static void session_close(struct request_ctx *rq)
{
    for (unsigned i = 0; i < rq->num_captures; i++)
        if (rq->captures[i].fd >= 0)
            close(rq->captures[i].fd);
    if (rq->output_map)
        munmap(rq->output_map, rq->output_length);
    if (rq->request_fd >= 0)
        close(rq->request_fd);
    if (rq->video_fd >= 0)
        close(rq->video_fd);
    if (rq->media_fd >= 0)
        close(rq->media_fd);
    if (rq->dump)
        fclose(rq->dump);
    free(rq->codec_state);
    free(rq);
}

static void request_decoder_close(struct context *ctx)
{
    struct request_ctx *rq = ctx->engine;
    if (rq && is_stateful(ctx)) {
        backend_v4l2m2m.decoder_close(ctx);
        return;
    }
    if (!rq)
        return;
    if (rq->video_fd >= 0) {
        stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_OUTPUT, false);
        stream(rq->video_fd, V4L2_BUF_TYPE_VIDEO_CAPTURE, false);
    }
    session_close(rq);
    ctx->engine = NULL;
}

static int request_decoder_open(struct driver *drv, struct context *ctx)
{
    const struct request_codec *codec = codec_for(ctx->config->codec->kind);
    const char *dump = getenv(DUMP_ENV);

    if (is_stateful(ctx))
        return backend_v4l2m2m.decoder_open(drv, ctx);
    struct request_ctx *rq = codec ? calloc(1, sizeof(*rq)) : NULL;
    if (!rq)
        return codec ? -ENOMEM : -ENOTSUP;
    ctx->engine = rq;
    *rq = (struct request_ctx){ .drv = drv, .video_fd = -1, .media_fd = -1,
                                .request_fd = -1 };
    if (!(rq->codec_state = calloc(1, codec->state_size)))
        return -ENOMEM;
    if (ctx->targets_take_compressed)
        rq->compressed_modifier = drv->compressed_modifier;
    if (dump)
        return (rq->dump = fopen(dump, "a")) ? 0 : -errno;
    return open_session(rq, codec, ctx);
}

static void release_request_picture(struct engine_picture *picture)
{
    close(picture->fds[0]);
    free(picture);
}

/* a picture in the engine's memory, or a repeated one in its reference's: the surface's, copied
 * where it has memory of its own */
static struct engine_picture *picture_of(struct request_ctx *rq, unsigned index)
{
    const struct v4l2_pix_format *f = &rq->capture.fmt.pix;
    const struct capture_buffer *c = &rq->captures[index];
    struct engine_picture *p = calloc(1, sizeof(*p));
    bool ten_bit = f->pixelformat == V4L2_PIX_FMT_P010 ||
                   f->pixelformat == V4L2_PIX_FMT_YUV420_10_AFBC_16X16_SPLIT;
    if (!p)
        return NULL;
    *p = (struct engine_picture){
        .width = f->width,
        .height = f->height,
        .num_objects = 1,
        .fds = { dup(c->fd) },
        .sizes = { c->size },
        .release = release_request_picture,
    };
    if (rq->compressed_modifier) {
        p->drm_format = ten_bit ? DRM_FORMAT_YUV420_10BIT : DRM_FORMAT_YUV420_8BIT;
        p->modifier = rq->compressed_modifier;
    } else {
        p->drm_format = ten_bit ? DRM_FORMAT_P010 : DRM_FORMAT_NV12;
        p->modifier = DRM_FORMAT_MOD_LINEAR;
        p->plane_offset[1] = f->bytesperline * f->height;
        p->plane_pitch[0] = p->plane_pitch[1] = f->bytesperline;
    }
    return p;
}

static int request_decode_picture(struct driver *drv, struct context *ctx,
                                  const struct picture *pic)
{
    struct request_ctx *rq = ctx->engine;
    struct surface *target = surface_of(drv, ctx->target);
    struct packet_info info;
    int ret, in_place = 0;

    if (is_stateful(ctx)) {
        ctx->bitstream.size = 0;
        ret = ctx->config->codec->build_packet(ctx->codec_state, pic, &ctx->bitstream, &info);
        return ret ? ret : backend_v4l2m2m.decode(drv, ctx, &ctx->bitstream);
    }
    if (!target)
        return -EINVAL;
    if ((ret = assign_capture(rq, ctx->target)) < 0)
        return ret;
    rq->target = ret;
    struct capture_buffer *c = &rq->captures[rq->target];
    if (!rq->dump && (in_place = lend_capture(rq, c, target)) < 0)
        return in_place;
    forget_buffer(rq, rq->target);
    c->latest = -1;
    rq->repeated = -1;
    c->timestamp = ++rq->last_timestamp;
    ret = codec_for(ctx->config->codec->kind)->submit(rq, pic);
    rq->dump_picture++;
    if (ret < 0)
        return ret;
    c->latest = rq->repeated >= 0 ? rq->repeated : (int)rq->target;
    if (rq->dump)
        return 0;
    if (in_place && rq->repeated < 0) {
        surface_mark_decoded(target);
        return 0;
    }
    struct engine_picture *p = picture_of(rq, c->latest);
    return p ? surface_bind_picture(target, p) : -ENOMEM;
}

/* a decode context's buffer for a surface it will decode into, which GStreamer exports before
 * the first picture */
static int request_lend_backing(struct driver *drv, VASurfaceID id, struct surface *s)
{
    for (unsigned i = 0; i < drv->contexts.capacity; i++) {
        const struct context *ctx = drv->contexts.items[i];
        struct request_ctx *rq = ctx && !is_encode(ctx->config->offer->entrypoint) &&
                                         !is_stateful(ctx)
                                     ? ctx->engine
                                     : NULL;
        if (rq && !rq->dump && (unsigned)ctx->width == s->width &&
            (unsigned)ctx->height == s->height && surface_fourcc_of_capture(rq) == s->fourcc) {
            int index = assign_capture(rq, id);
            return index < 0 ? index : lend_capture(rq, &rq->captures[index], s) > 0 ? 0 : -EINVAL;
        }
    }
    return -ENOENT;
}

/* a stateless picture is whole at vaEndPicture or lost; a stateful one may come later */
static int request_sync(struct driver *drv, struct context *ctx, VASurfaceID id, bool last)
{
    return is_stateful(ctx) ? backend_v4l2m2m.sync(drv, ctx, id, last) : -EIO;
}

static int request_encoder_open(struct driver *drv, struct context *ctx,
                                const struct encode_params *p)
{
    return backend_v4l2m2m.encoder_open(drv, ctx, p);
}

static int request_encode(struct context *ctx, struct surface *input, bool idr,
                          struct annexb *packet)
{
    return backend_v4l2m2m.encode(ctx, input, idr, packet);
}

static void request_encoder_close(struct context *ctx)
{
    backend_v4l2m2m.encoder_close(ctx);
}

const struct backend backend_request = {
    .name = "v4l2-request",
    .init = request_init,
    .uninit = request_uninit,
    .decoder_open = request_decoder_open,
    .decode_picture = request_decode_picture,
    .decoder_close = request_decoder_close,
    .lend_backing = request_lend_backing,
    .sync = request_sync,
    /* Cedrus's H.264 encoder takes a fixed quantiser only */
    .encoder_open = request_encoder_open,
    .encode = request_encode,
    .encoder_close = request_encoder_close,
};
