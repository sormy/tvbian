#include "v4l2.h"

#include <fcntl.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <linux/videodev2.h>

#define MAX_DEVICES 64
/* asked of TRY_FMT, which clamps it to the largest the queue takes */
#define LARGEST_ASKED 65535
/* a device states the picture's size; VA sizes a context in whole macroblocks */
#define MACROBLOCK 16
#define TO_MACROBLOCKS(x) (((x) + MACROBLOCK - 1) / MACROBLOCK * MACROBLOCK)

static enum v4l2_buf_type coded_queue(bool decode, bool mplane)
{
    if (decode)
        return mplane ? V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE : V4L2_BUF_TYPE_VIDEO_OUTPUT;
    return mplane ? V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE : V4L2_BUF_TYPE_VIDEO_CAPTURE;
}

static bool queue_takes(int fd, enum v4l2_buf_type type, uint32_t pixelformat, uint32_t *flags)
{
    struct v4l2_fmtdesc desc = { .type = type };
    for (; !ioctl(fd, VIDIOC_ENUM_FMT, &desc); desc.index++)
        if (desc.pixelformat == pixelformat)
            return *flags = desc.flags, true;
    return false;
}

int v4l2_open_coded(uint32_t pixelformat, bool decode, bool *mplane, uint32_t *flags)
{
    for (int i = 0; i < MAX_DEVICES; i++) {
        char path[32];
        struct v4l2_capability cap;
        snprintf(path, sizeof(path), "/dev/video%d", i);
        int fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0)
            continue;
        bool multi = !ioctl(fd, VIDIOC_QUERYCAP, &cap) &&
                     cap.device_caps & V4L2_CAP_VIDEO_M2M_MPLANE;
        bool single = !multi && cap.device_caps & V4L2_CAP_VIDEO_M2M;
        if ((multi || single) && queue_takes(fd, coded_queue(decode, multi), pixelformat, flags)) {
            *mplane = multi;
            return fd;
        }
        close(fd);
    }
    return -1;
}

/* the largest size the device lists for the format; false when it lists none */
static bool largest_size(int fd, uint32_t pixelformat, unsigned *width, unsigned *height)
{
    struct v4l2_frmsizeenum size = { .pixel_format = pixelformat };
    *width = *height = 0;
    for (; !ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &size); size.index++) {
        if (size.type != V4L2_FRMSIZE_TYPE_DISCRETE) {
            *width = size.stepwise.max_width;
            *height = size.stepwise.max_height;
            break;
        }
        if (size.discrete.width * size.discrete.height > *width * *height) {
            *width = size.discrete.width;
            *height = size.discrete.height;
        }
    }
    return *width && *height;
}

/* the size TRY_FMT clamps the largest ask to; false when it fails */
static bool clamped_size(int fd, enum v4l2_buf_type type, uint32_t pixelformat, unsigned *width,
                         unsigned *height)
{
    struct v4l2_format f = { .type = type };
    bool mplane = type == V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE ||
                  type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    if (mplane)
        f.fmt.pix_mp = (struct v4l2_pix_format_mplane){
            .width = LARGEST_ASKED, .height = LARGEST_ASKED, .pixelformat = pixelformat
        };
    else
        f.fmt.pix = (struct v4l2_pix_format){
            .width = LARGEST_ASKED, .height = LARGEST_ASKED, .pixelformat = pixelformat
        };
    if (ioctl(fd, VIDIOC_TRY_FMT, &f) < 0)
        return false;
    *width = mplane ? f.fmt.pix_mp.width : f.fmt.pix.width;
    *height = mplane ? f.fmt.pix_mp.height : f.fmt.pix.height;
    return *width && *height && *width < LARGEST_ASKED && *height < LARGEST_ASKED;
}

/* frame sizes where the device lists them, an encoder's maybe on its raw queue alone, else the
 * clamp; 0 when nothing says */
static void size_limit(int fd, bool decode, bool mplane, uint32_t pixelformat, unsigned *width,
                       unsigned *height)
{
    if (largest_size(fd, pixelformat, width, height) ||
        (!decode && (largest_size(fd, V4L2_PIX_FMT_NV12M, width, height) ||
                     largest_size(fd, V4L2_PIX_FMT_NV12, width, height))))
        return;
    if (!clamped_size(fd, coded_queue(decode, mplane), pixelformat, width, height))
        *width = *height = 0;
}

#ifndef V4L2_PIX_FMT_NV15
#define V4L2_PIX_FMT_NV15 v4l2_fourcc('N', 'V', '1', '5')
#endif

static bool captures_ten_bit(int fd, bool mplane)
{
    uint32_t flags;
    enum v4l2_buf_type type = coded_queue(false, mplane);
    return queue_takes(fd, type, V4L2_PIX_FMT_P010, &flags) ||
           queue_takes(fd, type, V4L2_PIX_FMT_NV15, &flags);
}

/* a device without the menu says nothing against the item */
static bool menu_lists(int fd, uint32_t id, unsigned item)
{
    struct v4l2_queryctrl control = { .id = id };
    if (!id || ioctl(fd, VIDIOC_QUERYCTRL, &control) < 0 || control.type != V4L2_CTRL_TYPE_MENU)
        return true;
    struct v4l2_querymenu entry = { .id = id, .index = item };
    return (int)item >= control.minimum && (int)item <= control.maximum &&
           !ioctl(fd, VIDIOC_QUERYMENU, &entry);
}

unsigned v4l2_offers(const struct v4l2_candidate *candidates, unsigned count, struct offer *out)
{
    unsigned kept = 0;
    for (unsigned i = 0; i < count; i++) {
        const struct v4l2_candidate *c = &candidates[i];
        bool mplane, decode = c->entrypoint == VAEntrypointVLD;
        uint32_t flags;
        int fd = v4l2_open_coded(c->pixelformat, decode, &mplane, &flags);
        if (fd < 0)
            continue;
        if (menu_lists(fd, c->menu, c->item) && (!c->ten_bit || captures_ten_bit(fd, mplane))) {
            out[kept] = (struct offer){ .profile = c->profile, .entrypoint = c->entrypoint };
            struct offer *o = &out[kept++];
            size_limit(fd, decode, mplane, c->pixelformat, &o->max_width, &o->max_height);
            o->max_width = TO_MACROBLOCKS(o->max_width);
            o->max_height = TO_MACROBLOCKS(o->max_height);
        }
        close(fd);
    }
    return kept;
}
