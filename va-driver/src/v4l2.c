/* versionsort */
#define _GNU_SOURCE
#include "v4l2.h"

#include <dirent.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <linux/videodev2.h>

/* the numbers tried where /sys cannot be listed */
#define MAX_DEVICES 64
#define VIDEO_NODES "/sys/class/video4linux"
/* /dev/ and the longest name a directory lists */
#define PATH_BYTES (sizeof("/dev/") + NAME_MAX)
/* asked of TRY_FMT, which clamps it to the largest the queue takes; the other side kept small */
#define LARGEST_ASKED 65535
#define SMALL_SIDE 64
/* a device states the picture's size; VA sizes a context in whole macroblocks */
#define MACROBLOCK 16
#define TO_MACROBLOCKS(x) (((x) + MACROBLOCK - 1) / MACROBLOCK * MACROBLOCK)

static enum v4l2_buf_type coded_queue(bool decode, bool mplane)
{
    if (decode)
        return mplane ? V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE : V4L2_BUF_TYPE_VIDEO_OUTPUT;
    return mplane ? V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE : V4L2_BUF_TYPE_VIDEO_CAPTURE;
}

bool v4l2_queue_takes(int fd, enum v4l2_buf_type type, uint32_t pixelformat, uint32_t *flags)
{
    struct v4l2_fmtdesc desc = { .type = type };
    for (; !ioctl(fd, VIDIOC_ENUM_FMT, &desc); desc.index++)
        if (desc.pixelformat == pixelformat) {
            if (flags)
                *flags = desc.flags;
            return true;
        }
    return false;
}

int v4l2_each_node(const char *sysfs_dir, const char *prefix, v4l2_node_try try, void *arg)
{
    struct dirent **listed;
    char path[PATH_BYTES];
    int fd = -1;
    int n = scandir(sysfs_dir, &listed, NULL, versionsort);
    if (n < 0) {
        for (int i = 0; i < MAX_DEVICES && fd < 0; i++) {
            snprintf(path, sizeof(path), "/dev/%s%d", prefix, i);
            fd = try(path, arg);
        }
        return fd;
    }
    for (int i = 0; i < n; i++) {
        if (fd < 0 && !strncmp(listed[i]->d_name, prefix, strlen(prefix))) {
            snprintf(path, sizeof(path), "/dev/%s", listed[i]->d_name);
            fd = try(path, arg);
        }
        free(listed[i]);
    }
    free(listed);
    return fd;
}

struct coded_ask {
    uint32_t pixelformat;
    bool decode;
    bool *mplane;
    uint32_t *flags;
    /* the node kept so far and the size it takes */
    int fd;
    unsigned long area;
};

static bool largest_size(int fd, uint32_t pixelformat, unsigned *width, unsigned *height);

/* every node taking the format looked at, the one taking the largest size kept, as two engines
 * may decode one codec */
static int try_coded(const char *path, void *arg)
{
    struct coded_ask *ask = arg;
    struct v4l2_capability cap;
    int fd = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0)
        return -1;
    bool multi = !ioctl(fd, VIDIOC_QUERYCAP, &cap) && cap.device_caps & V4L2_CAP_VIDEO_M2M_MPLANE;
    bool single = !multi && cap.device_caps & V4L2_CAP_VIDEO_M2M;
    unsigned width, height;
    uint32_t flags = 0;
    if ((multi || single) &&
        v4l2_queue_takes(fd, coded_queue(ask->decode, multi), ask->pixelformat, &flags)) {
        unsigned long area = largest_size(fd, ask->pixelformat, &width, &height)
                                 ? (unsigned long)width * height
                                 : 1;
        if (area > ask->area) {
            if (ask->fd >= 0)
                close(ask->fd);
            *ask->mplane = multi;
            if (ask->flags)
                *ask->flags = flags;
            ask->fd = fd;
            ask->area = area;
            return -1;
        }
    }
    close(fd);
    return -1;
}

int v4l2_open_coded(uint32_t pixelformat, bool decode, bool *mplane, uint32_t *flags)
{
    struct coded_ask ask = { pixelformat, decode, mplane, flags, -1, 0 };
    v4l2_each_node(VIDEO_NODES, "video", try_coded, &ask);
    return ask.fd;
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

/* the size TRY_FMT clamps an ask to; false when it fails or clamps nothing */
static bool clamped_size(int fd, enum v4l2_buf_type type, uint32_t pixelformat, unsigned ask_width,
                         unsigned ask_height, unsigned *width, unsigned *height)
{
    struct v4l2_format f = { .type = type };
    bool mplane = type == V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE ||
                  type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    if (mplane)
        f.fmt.pix_mp = (struct v4l2_pix_format_mplane){
            .width = ask_width, .height = ask_height, .pixelformat = pixelformat
        };
    else
        f.fmt.pix = (struct v4l2_pix_format){
            .width = ask_width, .height = ask_height, .pixelformat = pixelformat
        };
    if (ioctl(fd, VIDIOC_TRY_FMT, &f) < 0)
        return false;
    *width = mplane ? f.fmt.pix_mp.width : f.fmt.pix.width;
    *height = mplane ? f.fmt.pix_mp.height : f.fmt.pix.height;
    return *width && *height && *width < LARGEST_ASKED && *height < LARGEST_ASKED;
}

/* frame sizes where the device lists them, an encoder's maybe on its raw queue alone, else the
 * clamp: the widest, the tallest and the largest, which a clamp trimming by area makes smaller
 * than the two; in whole macroblocks, as VA sizes a context. 0 when nothing says. */
static void size_limit(int fd, bool decode, bool mplane, uint32_t pixelformat, struct offer *o)
{
    enum v4l2_buf_type type = coded_queue(decode, mplane);
    unsigned width, height;
    if (largest_size(fd, pixelformat, &o->max_width, &o->max_height) ||
        (!decode && (largest_size(fd, V4L2_PIX_FMT_NV12M, &o->max_width, &o->max_height) ||
                     largest_size(fd, V4L2_PIX_FMT_NV12, &o->max_width, &o->max_height)))) {
        o->max_width = TO_MACROBLOCKS(o->max_width);
        o->max_height = TO_MACROBLOCKS(o->max_height);
        return;
    }
    if (!clamped_size(fd, type, pixelformat, LARGEST_ASKED, SMALL_SIDE, &o->max_width, &height) ||
        !clamped_size(fd, type, pixelformat, SMALL_SIDE, LARGEST_ASKED, &width, &o->max_height) ||
        !clamped_size(fd, type, pixelformat, LARGEST_ASKED, LARGEST_ASKED, &width, &height)) {
        o->max_width = o->max_height = 0;
        return;
    }
    o->max_width = TO_MACROBLOCKS(o->max_width);
    o->max_height = TO_MACROBLOCKS(o->max_height);
    unsigned pixels = TO_MACROBLOCKS(width) * TO_MACROBLOCKS(height);
    if (pixels < o->max_width * o->max_height)
        o->max_pixels = pixels;
}

/* an SPS small and plain enough for any decoder, but 10 bits deep */
#define PROBE_SIZE 64
#define TEN_BIT_DEPTH_MINUS8 2
#define CHROMA_420 1

#ifndef V4L2_PIX_FMT_NV15
#define V4L2_PIX_FMT_NV15 v4l2_fourcc('N', 'V', '1', '5')
#endif

static bool lists_ten_bit(int fd, enum v4l2_buf_type type)
{
    uint32_t flags;
    return v4l2_queue_takes(fd, type, V4L2_PIX_FMT_P010, &flags) ||
           v4l2_queue_takes(fd, type, V4L2_PIX_FMT_NV15, &flags);
}

/* a 10-bit format listed, at once or once the device's SPS says 10 bits, as rkvdec's HEVC wants */
static bool captures_ten_bit(int fd, bool mplane, uint32_t pixelformat)
{
    enum v4l2_buf_type type = coded_queue(false, mplane);
    if (lists_ten_bit(fd, type) || pixelformat != V4L2_PIX_FMT_HEVC_SLICE)
        return lists_ten_bit(fd, type);
    struct v4l2_ctrl_hevc_sps sps = { .pic_width_in_luma_samples = PROBE_SIZE,
                                      .pic_height_in_luma_samples = PROBE_SIZE,
                                      .bit_depth_luma_minus8 = TEN_BIT_DEPTH_MINUS8,
                                      .bit_depth_chroma_minus8 = TEN_BIT_DEPTH_MINUS8,
                                      .chroma_format_idc = CHROMA_420 };
    struct v4l2_ext_control control = { .id = V4L2_CID_STATELESS_HEVC_SPS, .size = sizeof(sps),
                                        .ptr = &sps };
    struct v4l2_ext_controls set = { .which = V4L2_CTRL_WHICH_CUR_VAL, .count = 1,
                                     .controls = &control };
    return !ioctl(fd, VIDIOC_S_EXT_CTRLS, &set) && lists_ten_bit(fd, type);
}

/* whether the device has the menu and lists the item */
static bool menu_has(int fd, uint32_t id, unsigned item)
{
    struct v4l2_queryctrl control = { .id = id };
    struct v4l2_querymenu entry = { .id = id, .index = item };
    return !ioctl(fd, VIDIOC_QUERYCTRL, &control) && control.type == V4L2_CTRL_TYPE_MENU &&
           (int)item >= control.minimum && (int)item <= control.maximum &&
           !ioctl(fd, VIDIOC_QUERYMENU, &entry);
}

/* an encoder takes a fixed QP always, and the bitrate modes its menu lists */
static unsigned rate_controls(int fd)
{
    unsigned controls = VA_RC_CQP;
    if (menu_has(fd, V4L2_CID_MPEG_VIDEO_BITRATE_MODE, V4L2_MPEG_VIDEO_BITRATE_MODE_VBR))
        controls |= VA_RC_VBR;
    if (menu_has(fd, V4L2_CID_MPEG_VIDEO_BITRATE_MODE, V4L2_MPEG_VIDEO_BITRATE_MODE_CBR))
        controls |= VA_RC_CBR;
    return controls;
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

static bool offered(const struct offer *offers, unsigned count, const struct v4l2_candidate *c)
{
    for (unsigned i = 0; i < count; i++)
        if (offers[i].profile == c->profile && offers[i].entrypoint == c->entrypoint)
            return true;
    return false;
}

/* a profile once, from the first candidate a node takes: JPEG comes as MJPG or JPEG */
unsigned v4l2_offers(const struct v4l2_candidate *candidates, unsigned count, struct offer *out)
{
    unsigned kept = 0;
    for (unsigned i = 0; i < count; i++) {
        const struct v4l2_candidate *c = &candidates[i];
        if (offered(out, kept, c))
            continue;
        bool mplane, decode = c->entrypoint == VAEntrypointVLD;
        uint32_t flags;
        int fd = v4l2_open_coded(c->pixelformat, decode, &mplane, &flags);
        if (fd < 0)
            continue;
        if (menu_lists(fd, c->menu, c->item) && (!c->ten_bit || captures_ten_bit(fd, mplane, c->pixelformat))) {
            out[kept] = (struct offer){ .profile = c->profile, .entrypoint = c->entrypoint };
            if (!decode)
                out[kept].rate_controls = rate_controls(fd);
            size_limit(fd, decode, mplane, c->pixelformat, &out[kept++]);
        }
        close(fd);
    }
    return kept;
}
