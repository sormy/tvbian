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
#include "settings.h"

#define MEDIA_NODES "/sys/bus/media/devices"
#define CODED_BUFFER_SIZE (4 << 20)
#define REQUEST_TIMEOUT_MS 1000
#define USEC_TO_NSEC 1000
#define DUMP_ENV "VAAPI_REQUEST_DUMP"
#define TEN_BIT_DEPTH_MINUS8 2
#define CHROMA_420 1
#define MB_SIZE 16
#ifndef V4L2_PIX_FMT_NV15
#define V4L2_PIX_FMT_NV15 v4l2_fourcc('N', 'V', '1', '5')
#endif
#ifndef DRM_FORMAT_NV15
#define DRM_FORMAT_NV15 fourcc_code('N', 'V', '1', '5')
#endif
#define VP9_PROFILE_2 2
#define TEN_BITS 10

/* linux-sunxi 0058: Cedrus's AFBC, for a client whose GPU samples it */
#ifndef V4L2_PIX_FMT_YUV420_8_AFBC_16X16_SPLIT
#define V4L2_PIX_FMT_YUV420_8_AFBC_16X16_SPLIT v4l2_fourcc('A', 'S', '1', '2')
#define V4L2_PIX_FMT_YUV420_10_AFBC_16X16_SPLIT v4l2_fourcc('A', 'S', '0', '1')
#endif
/* rkvdec's AFBC, which VOP2 scans out */
#ifndef V4L2_PIX_FMT_AFBC_YUV420_16x16
#define V4L2_PIX_FMT_AFBC_YUV420_16x16 v4l2_fourcc('A', 'N', '6', '8')
#define V4L2_PIX_FMT_AFBC_YUV420_16x16_10 v4l2_fourcc('A', 'N', '6', 'a')
#endif
#define AFBC_16X16_SPARSE (AFBC_FORMAT_MOD_BLOCK_SIZE_16x16 | AFBC_FORMAT_MOD_SPARSE)

/* an AFBC a decoder may write, and its modifier */
struct afbc_layout {
    uint32_t eight_bit;
    uint32_t ten_bit;
    uint64_t modifier;
};

static const struct afbc_layout afbc_layouts[] = {
    { V4L2_PIX_FMT_YUV420_8_AFBC_16X16_SPLIT, V4L2_PIX_FMT_YUV420_10_AFBC_16X16_SPLIT,
      DRM_FORMAT_MOD_ARM_AFBC(AFBC_16X16_SPARSE | AFBC_FORMAT_MOD_SPLIT) },
    { V4L2_PIX_FMT_AFBC_YUV420_16x16, V4L2_PIX_FMT_AFBC_YUV420_16x16_10,
      DRM_FORMAT_MOD_ARM_AFBC(AFBC_16X16_SPARSE) },
};
#define NUM_AFBC_LAYOUTS (sizeof(afbc_layouts) / sizeof(afbc_layouts[0]))

static const struct afbc_layout *afbc_layout_of(uint64_t modifier)
{
    for (unsigned i = 0; i < NUM_AFBC_LAYOUTS; i++)
        if (afbc_layouts[i].modifier == modifier)
            return &afbc_layouts[i];
    return NULL;
}

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
    { VAProfileJPEGBaseline, VLD, V4L2_PIX_FMT_JPEG, 0, 0, false },
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
    rq->mplane = mplane;
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

int request_set_control(struct request_ctx *rq, uint32_t id, int value)
{
    struct v4l2_ext_control control = { .id = id, .value = value };
    struct v4l2_ext_controls controls = { .count = 1, .controls = &control };
    if (rq->dump)
        return 0;
    return ioctl(rq->video_fd, VIDIOC_S_EXT_CTRLS, &controls) < 0 ? -errno : 0;
}

static int stream(int fd, enum v4l2_buf_type type, bool on)
{
    return ioctl(fd, on ? VIDIOC_STREAMON : VIDIOC_STREAMOFF, &type) < 0 ? -errno : 0;
}

static enum v4l2_buf_type output_type(const struct request_ctx *rq)
{
    return rq->mplane ? V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE : V4L2_BUF_TYPE_VIDEO_OUTPUT;
}

static enum v4l2_buf_type capture_type(const struct request_ctx *rq)
{
    return rq->mplane ? V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE : V4L2_BUF_TYPE_VIDEO_CAPTURE;
}

static void stream_both(const struct request_ctx *rq, bool on)
{
    stream(rq->video_fd, output_type(rq), on);
    stream(rq->video_fd, capture_type(rq), on);
}

/* a format to set, in the queue's API: one plane where it is multi-planar */
static struct v4l2_format format_of(const struct request_ctx *rq, enum v4l2_buf_type type,
                                    uint32_t pixelformat, unsigned width, unsigned height,
                                    unsigned sizeimage)
{
    struct v4l2_format f = { .type = type };
    if (rq->mplane)
        f.fmt.pix_mp = (struct v4l2_pix_format_mplane){
            .width = width, .height = height, .pixelformat = pixelformat, .num_planes = 1,
            .plane_fmt = { { .sizeimage = sizeimage } }
        };
    else
        f.fmt.pix = (struct v4l2_pix_format){ .width = width, .height = height,
                                              .pixelformat = pixelformat, .sizeimage = sizeimage };
    return f;
}

/* a format as set, as one plane; -ENOTSUP for a layout of more */
static int one_plane(const struct request_ctx *rq, const struct v4l2_format *f,
                     struct v4l2_pix_format *out)
{
    const struct v4l2_pix_format_mplane *mp = &f->fmt.pix_mp;
    if (!rq->mplane) {
        *out = f->fmt.pix;
        return 0;
    }
    if (mp->num_planes != 1)
        return -ENOTSUP;
    *out = (struct v4l2_pix_format){ .width = mp->width, .height = mp->height,
                                     .pixelformat = mp->pixelformat,
                                     .bytesperline = mp->plane_fmt[0].bytesperline,
                                     .sizeimage = mp->plane_fmt[0].sizeimage };
    return 0;
}

/* a buffer of the queue, its one plane given where the queue is multi-planar */
static struct v4l2_buffer buffer_of(const struct request_ctx *rq, enum v4l2_buf_type type,
                                    unsigned index, struct v4l2_plane *plane)
{
    struct v4l2_buffer b = { .index = index, .type = type, .memory = V4L2_MEMORY_MMAP };
    if (rq->mplane) {
        *plane = (struct v4l2_plane){ 0 };
        b.m.planes = plane;
        b.length = 1;
    }
    return b;
}

/* CAPTURE buffer index exported, for no surface yet */
static int setup_capture(struct request_ctx *rq, unsigned index)
{
    struct v4l2_exportbuffer exported = { .type = capture_type(rq), .index = index,
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
                                              .flags = V4L2_MEMORY_FLAG_NON_COHERENT,
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
    const struct afbc_layout *afbc = afbc_layout_of(rq->compressed_modifier);
    if (afbc)
        return rq->picture.pixelformat == afbc->ten_bit ? VA_FOURCC_P010 : VA_FOURCC_NV12;
    switch (rq->picture.pixelformat) {
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
static bool gpu_imports(unsigned pitch, size_t chroma_offset)
{
    return pitch % GPU_PLANE_ALIGN == 0 && chroma_offset % GPU_PLANE_ALIGN == 0;
}

static int lend_capture(struct request_ctx *rq, const struct capture_buffer *c, struct surface *s)
{
    const struct v4l2_pix_format *f = &rq->picture;
    const struct backing_layout layout = { .pitch = f->bytesperline,
                                           .chroma_offset = f->bytesperline * f->height,
                                           .size = c->size,
                                           .modifier = rq->compressed_modifier };
    struct stat st;
    int ret;
    surface_drop_unseen_backing(s);
    /* Panfrost's pitch rule is for linear planes; AFBC goes to the display */
    if (!s->backing && s->fourcc == surface_fourcc_of_capture(rq) &&
        (layout.modifier || gpu_imports(layout.pitch, layout.chroma_offset)) &&
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

static int dequeue(const struct request_ctx *rq, enum v4l2_buf_type type)
{
    struct v4l2_plane plane;
    struct v4l2_buffer buffer = buffer_of(rq, type, 0, &plane);
    if (ioctl(rq->video_fd, VIDIOC_DQBUF, &buffer) < 0)
        return -errno;
    return buffer.flags & V4L2_BUF_FLAG_ERROR ? -EIO : 0;
}

/* after a request that failed or never completed: both queues stopped, which cancels it, and
 * started again; the pictures already decoded keep their buffers */
static void reset_queues(struct request_ctx *rq)
{
    stream_both(rq, false);
    for (unsigned i = 0; i < REQUEST_SLOTS; i++) {
        ioctl(rq->slots[i].request_fd, MEDIA_REQUEST_IOC_REINIT);
        rq->slots[i].busy = false;
    }
    rq->oldest_slot = rq->next_slot;
    stream_both(rq, true);
}

static int queue_capture(struct request_ctx *rq)
{
    struct v4l2_plane plane;
    struct v4l2_buffer buffer = buffer_of(rq, capture_type(rq), rq->target, &plane);
    /* a picture goes to the GPU unread; a CPU read syncs the dma-buf itself */
    buffer.flags = V4L2_BUF_FLAG_NO_CACHE_INVALIDATE | V4L2_BUF_FLAG_NO_CACHE_CLEAN;
    return ioctl(rq->video_fd, VIDIOC_QBUF, &buffer) < 0 ? -errno : 0;
}

static int submit_request(struct request_ctx *rq, struct request_slot *slot,
                          struct v4l2_ext_control *controls, unsigned count,
                          const struct annexb *data, bool first, bool last)
{
    struct v4l2_ext_controls set = { .which = V4L2_CTRL_WHICH_REQUEST_VAL,
                                     .request_fd = slot->request_fd, .count = count,
                                     .controls = controls };
    struct v4l2_plane plane;
    struct v4l2_buffer output = buffer_of(rq, output_type(rq), (unsigned)(slot - rq->slots), &plane);
    output.timestamp.tv_usec = rq->captures[rq->target].timestamp;
    output.flags = V4L2_BUF_FLAG_REQUEST_FD |
                   (last || !rq->holds_capture ? 0 : V4L2_BUF_FLAG_M2M_HOLD_CAPTURE_BUF);
    output.request_fd = slot->request_fd;
    if (rq->mplane)
        plane.bytesused = data->size;
    else
        output.bytesused = data->size;
    int ret;
    memcpy(slot->map, data->data, data->size);
    if ((count && ioctl(rq->video_fd, VIDIOC_S_EXT_CTRLS, &set) < 0) ||
        ioctl(rq->video_fd, VIDIOC_QBUF, &output) < 0)
        return -errno;
    if (first && (ret = queue_capture(rq)) < 0)
        return ret;
    if (ioctl(slot->request_fd, MEDIA_REQUEST_IOC_QUEUE) < 0)
        return -errno;
    *slot = (struct request_slot){ .request_fd = slot->request_fd, .map = slot->map,
                                   .length = slot->length, .busy = true, .last = last,
                                   .surface = VA_INVALID_ID, .capture = rq->target,
                                   .timestamp = rq->captures[rq->target].timestamp };
    return 0;
}

static struct engine_picture *picture_of(struct request_ctx *rq, unsigned index);

/* a picture whose last request is done, onto its surface, unless the surface's buffer has a newer
 * picture coming */
static void deliver(struct request_ctx *rq, const struct request_slot *slot)
{
    const struct capture_buffer *c = &rq->captures[slot->capture];
    struct surface *s = surface_of(rq->drv, slot->surface);
    if (!s || c->surface != slot->surface || c->timestamp != slot->timestamp)
        return;
    if (slot->picture < 0) {
        surface_mark_decoded(s);
        return;
    }
    struct engine_picture *p = picture_of(rq, (unsigned)slot->picture);
    if (p)
        surface_bind_picture(s, p);
}

/* the oldest request in flight waited for, and its picture delivered if it ends one */
static int complete_oldest(struct request_ctx *rq)
{
    struct request_slot *slot = &rq->slots[rq->oldest_slot];
    int ret = wait_request(slot->request_fd);
    if (!ret)
        ret = dequeue(rq, output_type(rq));
    if (!ret && slot->last)
        ret = dequeue(rq, capture_type(rq));
    if (ret < 0) {
        reset_queues(rq);
        return ret;
    }
    ioctl(slot->request_fd, MEDIA_REQUEST_IOC_REINIT);
    slot->busy = false;
    rq->oldest_slot = (rq->oldest_slot + 1) % REQUEST_SLOTS;
    if (slot->last)
        deliver(rq, slot);
    return 0;
}

/* every request in flight that writes this buffer done, and those before it */
static int complete_capture(struct request_ctx *rq, unsigned capture)
{
    int newest = -1;
    for (unsigned i = 0; i < REQUEST_SLOTS; i++) {
        const struct request_slot *slot = &rq->slots[(rq->oldest_slot + i) % REQUEST_SLOTS];
        if (slot->busy && slot->capture == capture)
            newest = (int)i;
    }
    int ret = 0;
    for (int done = 0; !ret && done <= newest; done++)
        ret = complete_oldest(rq);
    return ret;
}

static int complete_all(struct request_ctx *rq)
{
    int ret = 0;
    while (!ret && rq->slots[rq->oldest_slot].busy)
        ret = complete_oldest(rq);
    return ret;
}

static void release_buffers(struct request_ctx *rq);
static int configure_session(struct request_ctx *rq, const struct request_codec *codec,
                             const struct context *ctx, unsigned width, unsigned height);

static int set_compound(const struct request_ctx *rq, uint32_t id, const void *value, uint32_t size)
{
    struct v4l2_ext_control control = { .id = id, .size = size, .ptr = (void *)value };
    struct v4l2_ext_controls controls = { .count = 1, .controls = &control };
    return ioctl(rq->video_fd, VIDIOC_S_EXT_CTRLS, &controls) < 0 ? -errno : 0;
}

int request_set_compound(struct request_ctx *rq, uint32_t id, const void *value, uint32_t size)
{
    if (rq->dump)
        return 0;
    int ret = set_compound(rq, id, value, size);
    if (ret != -EBUSY)
        return ret;
    release_buffers(rq);
    if ((ret = set_compound(rq, id, value, size)) < 0)
        return ret;
    return configure_session(rq, codec_for(rq->ctx->config->codec->kind), rq->ctx, rq->width,
                             rq->height);
}

/* queued without waiting: the engine decodes while the client readies the next picture, which
 * vaSyncSurface waits for */
int request_queue(struct request_ctx *rq, struct v4l2_ext_control *controls, unsigned count,
                  const struct annexb *data, bool first, bool last)
{
    if (rq->dump) {
        request_dump(rq, "request_bytes", data->size);
        return 0;
    }
    struct request_slot *slot = &rq->slots[rq->next_slot];
    int ret = slot->busy ? complete_oldest(rq) : 0;
    if (ret < 0)
        return ret;
    if (data->size > slot->length)
        return -E2BIG;
    if ((ret = submit_request(rq, slot, controls, count, data, first, last)) < 0) {
        reset_queues(rq);
        return ret;
    }
    rq->next_slot = (rq->next_slot + 1) % REQUEST_SLOTS;
    return 0;
}

int request_repeat_reference(struct request_ctx *rq, VASurfaceID reference)
{
    rq->repeated = latest_of(rq, reference);
    return rq->repeated < 0 && !rq->dump ? -EINVAL : 0;
}

/* the side a probe holds still while the other grows */
#define PROBE_SIDE 64
#define PROBE_STEP 16

/* a fresh decoder of the coded format, its OUTPUT set to that size; -1 where none takes it */
static int open_coded_at(uint32_t pixelformat, unsigned width, unsigned height, bool *mplane)
{
    uint32_t flags;
    int fd = v4l2_open_coded(pixelformat, true, mplane, &flags);
    if (fd < 0)
        return -1;
    struct v4l2_format format = { .type = *mplane ? V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE
                                                  : V4L2_BUF_TYPE_VIDEO_OUTPUT };
    if (*mplane)
        format.fmt.pix_mp = (struct v4l2_pix_format_mplane){ .width = width, .height = height,
                                                             .pixelformat = pixelformat };
    else
        format.fmt.pix = (struct v4l2_pix_format){ .width = width, .height = height,
                                                   .pixelformat = pixelformat };
    if (!ioctl(fd, VIDIOC_S_FMT, &format))
        return fd;
    close(fd);
    return -1;
}

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
    /* the context checks the headers of the codec it is set to */
    int fd = open_coded_at(hevc ? V4L2_PIX_FMT_HEVC_SLICE : V4L2_PIX_FMT_VP9_FRAME, width, height,
                           &mplane);
    if (fd < 0)
        return false;
    bool taken = !ioctl(fd, VIDIOC_TRY_EXT_CTRLS, &controls);
    close(fd);
    return taken;
}

/* a size every decoder here takes, for asking what it writes */
#define AFBC_PROBE_WIDTH 1920
#define AFBC_PROBE_HEIGHT 1080

/* the AFBC the HEVC decoder lists, by its modifier; 0 for none */
static uint64_t afbc_listed(void)
{
    bool mplane;
    uint32_t flags;
    uint64_t found = 0;
    int fd = open_coded_at(V4L2_PIX_FMT_HEVC_SLICE, AFBC_PROBE_WIDTH, AFBC_PROBE_HEIGHT, &mplane);
    if (fd < 0)
        return 0;
    enum v4l2_buf_type capture =
        mplane ? V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE : V4L2_BUF_TYPE_VIDEO_CAPTURE;
    for (unsigned i = 0; !found && i < NUM_AFBC_LAYOUTS; i++)
        if (v4l2_queue_takes(fd, capture, afbc_layouts[i].eight_bit, &flags))
            found = afbc_layouts[i].modifier;
    close(fd);
    return found;
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
    /* the AFBC the decoder lists: kept by a context whose targets all list its modifier and
     * whose CAPTURE lists its format for the stream */
    drv->compressed_modifier = afbc_listed();
    drv->offers = offers;
    drv->num_offers = v4l2_offers(request_candidates, NUM_CANDIDATES, offers);
    /* a dump without the device: the controls written are under test, not the decode */
    if (!drv->num_offers && getenv(DUMP_ENV))
        for (const struct v4l2_candidate *c = request_candidates; drv->num_offers < NUM_CANDIDATES;
             c++)
            offers[drv->num_offers++] = (struct offer){ .profile = c->profile,
                                                        .entrypoint = c->entrypoint };
    bool stateless = false;
    for (unsigned i = 0; i < drv->num_offers; i++) {
        if (offers[i].profile == VAProfileHEVCMain10 || offers[i].profile == VAProfileVP9Profile2)
            size_ten_bit(&offers[i]);
        stateless |= offers[i].entrypoint == VLD && offers[i].profile != VAProfileJPEGBaseline;
    }
    /* stateful nodes alone are the stateful backend's box */
    return stateless ? 0 : -ENODEV;
}

static void request_uninit(struct driver *drv)
{
}

/* the stream's size and depth as the device's own value, before its buffers: Cedrus lists 10-bit
 * formats only once told, and rkvdec sets its buffers up from it and takes a new one only with
 * none, so an SPS of the same format at the first picture frees no buffer a surface holds */
static int announce_format(struct request_ctx *rq, enum codec_kind kind, unsigned width,
                           unsigned height, bool ten_bit)
{
    unsigned depth_minus8 = ten_bit ? TEN_BIT_DEPTH_MINUS8 : 0;
    struct v4l2_ctrl_hevc_sps hevc = {
        .pic_width_in_luma_samples = width,
        .pic_height_in_luma_samples = height,
        .bit_depth_luma_minus8 = depth_minus8,
        .bit_depth_chroma_minus8 = depth_minus8,
        .chroma_format_idc = CHROMA_420,
    };
    struct v4l2_ctrl_h264_sps h264 = {
        .pic_width_in_mbs_minus1 = (width + MB_SIZE - 1) / MB_SIZE - 1,
        .pic_height_in_map_units_minus1 = (height + MB_SIZE - 1) / MB_SIZE - 1,
        .bit_depth_luma_minus8 = depth_minus8,
        .bit_depth_chroma_minus8 = depth_minus8,
        .chroma_format_idc = CHROMA_420,
        .flags = V4L2_H264_SPS_FLAG_FRAME_MBS_ONLY,
    };
    struct v4l2_ctrl_vp9_frame vp9 = {
        .frame_width_minus_1 = width - 1,
        .frame_height_minus_1 = height - 1,
        .bit_depth = TEN_BITS,
        .profile = VP9_PROFILE_2,
        .flags = V4L2_VP9_FRAME_FLAG_X_SUBSAMPLING | V4L2_VP9_FRAME_FLAG_Y_SUBSAMPLING,
    };
    struct v4l2_ext_control control;
    if (kind == CODEC_HEVC)
        control = (struct v4l2_ext_control){ .id = V4L2_CID_STATELESS_HEVC_SPS,
                                             .size = sizeof(hevc), .ptr = &hevc };
    else if (kind == CODEC_H264)
        control = (struct v4l2_ext_control){ .id = V4L2_CID_STATELESS_H264_SPS,
                                             .size = sizeof(h264), .ptr = &h264 };
    else if (kind == CODEC_VP9 && ten_bit)
        control = (struct v4l2_ext_control){ .id = V4L2_CID_STATELESS_VP9_FRAME,
                                             .size = sizeof(vp9), .ptr = &vp9 };
    else
        return 0;
    struct v4l2_ext_controls set = { .which = V4L2_CTRL_WHICH_CUR_VAL, .count = 1,
                                     .controls = &control };
    return ioctl(rq->video_fd, VIDIOC_S_EXT_CTRLS, &set) < 0 ? -errno : 0;
}

static uint32_t capture_format(const struct request_ctx *rq, bool ten_bit)
{
    const struct afbc_layout *afbc = afbc_layout_of(rq->compressed_modifier);
    if (afbc)
        return ten_bit ? afbc->ten_bit : afbc->eight_bit;
    if (!ten_bit)
        return V4L2_PIX_FMT_NV12;
    /* Cedrus writes P010, rkvdec NV15 */
    uint32_t flags;
    return v4l2_queue_takes(rq->video_fd, capture_type(rq), V4L2_PIX_FMT_P010, &flags)
               ? V4L2_PIX_FMT_P010
               : V4L2_PIX_FMT_NV15;
}

/* a request of its own and OUTPUT buffer i, mapped */
static int setup_slot(struct request_ctx *rq, unsigned i)
{
    struct request_slot *slot = &rq->slots[i];
    struct v4l2_plane plane;
    struct v4l2_buffer mapped = buffer_of(rq, output_type(rq), i, &plane);
    if (ioctl(rq->video_fd, VIDIOC_QUERYBUF, &mapped) < 0 ||
        ioctl(rq->media_fd, MEDIA_IOC_REQUEST_ALLOC, &slot->request_fd) < 0)
        return -errno;
    slot->length = rq->mplane ? plane.length : mapped.length;
    slot->map = mmap(NULL, slot->length, PROT_READ | PROT_WRITE, MAP_SHARED, rq->video_fd,
                     rq->mplane ? plane.m.mem_offset : mapped.m.offset);
    return slot->map == MAP_FAILED ? (slot->map = NULL, -errno) : 0;
}

/* the formats for pictures of this size, and the buffers and requests for them, streaming */
static int configure_session(struct request_ctx *rq, const struct request_codec *codec,
                             const struct context *ctx, unsigned width, unsigned height)
{
    struct v4l2_format output =
        format_of(rq, output_type(rq), codec->pixelformat, width, height, CODED_BUFFER_SIZE);
    struct v4l2_requestbuffers outputs = { .count = REQUEST_SLOTS, .type = output_type(rq),
                                           .memory = V4L2_MEMORY_MMAP };
    /* one a render target the client named, made before streaming as rkvdec readies its buffers
     * then; one where it named none, more as surfaces come */
    unsigned targets = ctx->num_targets > 0 ? (unsigned)ctx->num_targets : 1;
    struct v4l2_requestbuffers captures = {
        .count = targets < REQUEST_MAX_CAPTURES ? targets : REQUEST_MAX_CAPTURES,
        .type = capture_type(rq), .memory = V4L2_MEMORY_MMAP,
        /* cached where the queue allows it: a CPU read of uncached memory costs a 1080p frame
         * 30 ms on Cedrus */
        .flags = V4L2_MEMORY_FLAG_NON_COHERENT };
    struct v4l2_pix_format set;
    bool ten_bit = ctx->config->rt_format == VA_RT_FORMAT_YUV420_10;
    int ret;

    if (ioctl(rq->video_fd, VIDIOC_S_FMT, &output) < 0)
        return -errno;
    if ((ret = one_plane(rq, &output, &set)) < 0)
        return ret;
    /* a size past the engine's comes back clamped */
    if (set.width < width || set.height < height)
        return -ERANGE;
    /* a 10-bit stream needs it; to an 8-bit one it is a hint an engine may refuse */
    if ((ret = announce_format(rq, codec->kind, width, height, ten_bit)) < 0 && ten_bit)
        return ret;
    /* compressed only where the decoder lists its format for this stream */
    if (rq->compressed_modifier &&
        !v4l2_queue_takes(rq->video_fd, capture_type(rq), capture_format(rq, ten_bit),
                          NULL))
        rq->compressed_modifier = 0;
    uint32_t wanted = capture_format(rq, ten_bit);
    rq->capture = format_of(rq, capture_type(rq), wanted, width, height, 0);
    if (ioctl(rq->video_fd, VIDIOC_S_FMT, &rq->capture) < 0)
        return -errno;
    if ((ret = one_plane(rq, &rq->capture, &rq->picture)) < 0)
        return ret;
    /* a format the driver did not keep would be read as one it is not */
    if (rq->picture.pixelformat != wanted)
        return -ENOTSUP;
    if (rq->picture.width < width || rq->picture.height < height)
        return -ERANGE;
    rq->width = width;
    rq->height = height;
    if (ioctl(rq->video_fd, VIDIOC_REQBUFS, &outputs) < 0 ||
        ioctl(rq->video_fd, VIDIOC_REQBUFS, &captures) < 0 ||
        outputs.count < REQUEST_SLOTS)
        return outputs.count < REQUEST_SLOTS ? -ENOBUFS : -errno;
    rq->holds_capture = outputs.capabilities & V4L2_BUF_CAP_SUPPORTS_M2M_HOLD_CAPTURE_BUF;
    for (unsigned i = 0; i < captures.count; i++)
        if ((ret = setup_capture(rq, i)) < 0)
            return ret;
    for (unsigned i = 0; i < REQUEST_SLOTS; i++)
        if ((ret = setup_slot(rq, i)) < 0)
            return ret;
    if ((ret = stream(rq->video_fd, output_type(rq), true)) < 0)
        return ret;
    return stream(rq->video_fd, capture_type(rq), true);
}

static int open_session(struct request_ctx *rq, const struct request_codec *codec,
                        const struct context *ctx)
{
    int ret = open_devices(rq, codec->pixelformat);
    if (ret < 0 || (codec->init && (ret = codec->init(rq)) < 0))
        return ret;
    return configure_session(rq, codec, ctx, ctx->width, ctx->height);
}

/* every buffer and request let go, the pictures in flight finished first; surfaces keep the
 * dma-bufs they were lent */
static void release_buffers(struct request_ctx *rq)
{
    complete_all(rq);
    stream_both(rq, false);
    for (unsigned i = 0; i < rq->num_captures; i++)
        if (rq->captures[i].fd >= 0)
            close(rq->captures[i].fd);
    rq->num_captures = 0;
    for (unsigned i = 0; i < REQUEST_SLOTS; i++) {
        struct request_slot *slot = &rq->slots[i];
        if (slot->map)
            munmap(slot->map, slot->length);
        if (slot->request_fd >= 0)
            close(slot->request_fd);
        *slot = (struct request_slot){ .request_fd = -1 };
    }
    rq->next_slot = rq->oldest_slot = 0;
    enum v4l2_buf_type types[] = { output_type(rq), capture_type(rq) };
    for (unsigned i = 0; i < 2; i++) {
        struct v4l2_requestbuffers none = { .count = 0, .type = types[i],
                                            .memory = V4L2_MEMORY_MMAP };
        ioctl(rq->video_fd, VIDIOC_REQBUFS, &none);
    }
}

static void session_close(struct request_ctx *rq)
{
    for (unsigned i = 0; i < rq->num_captures; i++)
        if (rq->captures[i].fd >= 0)
            close(rq->captures[i].fd);
    for (unsigned i = 0; i < REQUEST_SLOTS; i++) {
        if (rq->slots[i].map)
            munmap(rq->slots[i].map, rq->slots[i].length);
        if (rq->slots[i].request_fd >= 0)
            close(rq->slots[i].request_fd);
    }
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
    /* the engine reads and writes the session's buffers until its requests are done */
    if (!rq->dump)
        complete_all(rq);
    if (rq->video_fd >= 0)
        stream_both(rq, false);
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
    *rq = (struct request_ctx){ .drv = drv, .video_fd = -1, .media_fd = -1 };
    for (unsigned i = 0; i < REQUEST_SLOTS; i++)
        rq->slots[i].request_fd = -1;
    rq->profile = ctx->config->offer->profile;
    rq->ctx = ctx;
    if (!(rq->codec_state = calloc(1, codec->state_size)))
        return -ENOMEM;
    if (ctx->targets_take_compressed || setting_is_on(setting(AFBC_ENV, AFBC_KEY)))
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
    const struct v4l2_pix_format *f = &rq->picture;
    const struct capture_buffer *c = &rq->captures[index];
    struct engine_picture *p = calloc(1, sizeof(*p));
    const struct afbc_layout *afbc = afbc_layout_of(rq->compressed_modifier);
    bool ten_bit = f->pixelformat == V4L2_PIX_FMT_P010 || f->pixelformat == V4L2_PIX_FMT_NV15 ||
                   (afbc && f->pixelformat == afbc->ten_bit);
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
        p->plane_pitch[0] = f->bytesperline;
    } else {
        p->drm_format = f->pixelformat == V4L2_PIX_FMT_NV15 ? DRM_FORMAT_NV15
                        : ten_bit                              ? DRM_FORMAT_P010
                                                               : DRM_FORMAT_NV12;
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
    /* a key frame of another size, as a VP9 stream may send in one context: a session anew at it,
     * as a new context gets */
    unsigned width = 0, height = 0;
    const struct request_codec *codec = codec_for(ctx->config->codec->kind);
    if (codec->picture_size)
        codec->picture_size(pic, &width, &height);
    if (!rq->dump && width && (width != rq->width || height != rq->height)) {
        request_decoder_close(ctx);
        ctx->width = width;
        ctx->height = height;
        if ((ret = request_decoder_open(drv, ctx)) < 0)
            return ret;
        rq = ctx->engine;
    }
    if (codec->prepare && !rq->dump && (ret = codec->prepare(rq, pic)) < 0)
        return ret;
    /* a buffer given to a surface anew may be a destroyed one's, still read as a reference */
    if (!rq->dump && capture_of(rq, ctx->target) < 0 && (ret = complete_all(rq)) < 0)
        return ret;
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
    /* the buffer's earlier picture finished first: its timestamp no longer delivers it */
    if (!rq->dump && (ret = complete_capture(rq, rq->target)) < 0)
        return ret;
    ret = codec_for(ctx->config->codec->kind)->submit(rq, pic);
    rq->dump_picture++;
    if (ret < 0)
        return ret;
    c->latest = rq->repeated >= 0 ? rq->repeated : (int)rq->target;
    if (rq->dump)
        return 0;
    if (rq->repeated < 0) {
        struct request_slot *last = &rq->slots[(rq->next_slot + REQUEST_SLOTS - 1) % REQUEST_SLOTS];
        last->surface = ctx->target;
        last->picture = in_place ? -1 : c->latest;
        return 0;
    }
    /* a repeated picture is an older buffer's, which may still be decoding */
    if ((ret = complete_all(rq)) < 0)
        return ret;
    struct engine_picture *p = picture_of(rq, c->latest);
    return p ? surface_bind_picture(target, p) : -ENOMEM;
}

/* a decode context's buffer for a surface it will decode into, which GStreamer exports before
 * the first picture */
static int request_lend_backing(struct driver *drv, VASurfaceID id, struct surface *s)
{
    for (unsigned i = 0; i < drv->contexts.capacity; i++) {
        const struct context *ctx = drv->contexts.items[i];
        struct request_ctx *rq = ctx && ctx->config->offer->entrypoint == VAEntrypointVLD &&
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
/* requests done in order until the surface has its picture or none is in flight */
static int request_sync(struct driver *drv, struct context *ctx, VASurfaceID id, bool last)
{
    if (is_stateful(ctx))
        return backend_v4l2m2m.sync(drv, ctx, id, last);
    struct request_ctx *rq = ctx->engine;
    const struct surface *s = surface_of(drv, id);
    int ret = 0;
    while (!ret && s && !s->delivered && rq->slots[rq->oldest_slot].busy)
        ret = complete_oldest(rq);
    return ret;
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

/* the layout the decoder writes a picture of this size in, asked of the device on a handle of its
 * own with OUTPUT at that size: a client may read one surface's layout and take it for all */
static bool plan_request_layout(VAProfile decoding, uint32_t fourcc, unsigned width,
                                unsigned height, struct backing_layout *out)
{
    static struct {
        VAProfile profile;
        unsigned width, height;
        struct backing_layout layout;
    } last = { .profile = VAProfileNone };
    if (fourcc != VA_FOURCC_NV12 || decoding == VAProfileNone)
        return false;
    if (last.profile == decoding && last.width == width && last.height == height) {
        *out = last.layout;
        return last.layout.size != 0;
    }
    uint32_t coded = 0;
    for (size_t i = 0; i < sizeof(request_candidates) / sizeof(request_candidates[0]); i++)
        if (request_candidates[i].profile == decoding && request_candidates[i].entrypoint == VLD)
            coded = request_candidates[i].pixelformat;
    bool mplane;
    uint32_t flags;
    int fd = coded ? v4l2_open_coded(coded, true, &mplane, &flags) : -1;
    struct backing_layout layout = { 0 };
    if (fd >= 0) {
        struct v4l2_format output = { .type = mplane ? V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE
                                                     : V4L2_BUF_TYPE_VIDEO_OUTPUT };
        struct v4l2_format capture = { .type = mplane ? V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE
                                                      : V4L2_BUF_TYPE_VIDEO_CAPTURE };
        if (mplane) {
            output.fmt.pix_mp = (struct v4l2_pix_format_mplane){
                .width = width, .height = height, .pixelformat = coded, .num_planes = 1 };
            capture.fmt.pix_mp = (struct v4l2_pix_format_mplane){
                .width = width, .height = height, .pixelformat = V4L2_PIX_FMT_NV12,
                .num_planes = 1 };
        } else {
            output.fmt.pix = (struct v4l2_pix_format){ .width = width, .height = height,
                                                       .pixelformat = coded };
            capture.fmt.pix = (struct v4l2_pix_format){ .width = width, .height = height,
                                                        .pixelformat = V4L2_PIX_FMT_NV12 };
        }
        if (!ioctl(fd, VIDIOC_S_FMT, &output) && !ioctl(fd, VIDIOC_TRY_FMT, &capture)) {
            unsigned pitch = mplane ? capture.fmt.pix_mp.plane_fmt[0].bytesperline
                                    : capture.fmt.pix.bytesperline;
            unsigned rows = mplane ? capture.fmt.pix_mp.height : capture.fmt.pix.height;
            unsigned size = mplane ? capture.fmt.pix_mp.plane_fmt[0].sizeimage
                                   : capture.fmt.pix.sizeimage;
            bool nv12 = (mplane ? capture.fmt.pix_mp.pixelformat : capture.fmt.pix.pixelformat) ==
                        V4L2_PIX_FMT_NV12;
            if (nv12 && rows >= height && pitch >= width && gpu_imports(pitch, pitch * rows))
                layout = (struct backing_layout){ .pitch = pitch, .chroma_offset = pitch * rows,
                                                  .size = size };
        }
        close(fd);
    }
    last.profile = decoding;
    last.width = width;
    last.height = height;
    last.layout = layout;
    *out = layout;
    return layout.size != 0;
}

const struct backend backend_request = {
    .name = "v4l2-request",
    .init = request_init,
    .uninit = request_uninit,
    .decoder_open = request_decoder_open,
    .decode_picture = request_decode_picture,
    .decoder_close = request_decoder_close,
    .lend_backing = request_lend_backing,
    .plan_layout = plan_request_layout,
    .sync = request_sync,
    /* Cedrus's H.264 encoder takes a fixed quantiser only */
    .encoder_open = request_encoder_open,
    .encode = request_encode,
    .encoder_close = request_encoder_close,
};
