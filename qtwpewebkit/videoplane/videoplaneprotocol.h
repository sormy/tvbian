// The messages a web process's video sink and the UI process exchange over a SOCK_SEQPACKET socket
#pragma once

#include <stdint.h>

#define QTWPEWEBKIT_VIDEO_PLANE_SOCKET "QTWPEWEBKIT_VIDEO_PLANE_SOCKET"
#define VIDEO_PLANE_MAX_PLANES 4

enum VideoPlaneMessageType {
    // From the sink: a frame, its planes' file descriptors attached
    VIDEO_PLANE_FRAME = 1,
    // From the sink: the hole moved while no frame came
    VIDEO_PLANE_RECTANGLE,
    // From the sink: the stream ended, its frames are taken back
    VIDEO_PLANE_STOP,
    // From the UI process: a frame is no longer read
    VIDEO_PLANE_RELEASE,
};

struct VideoPlaneMessage {
    uint32_t type;
    // A sink's stream, unique within its connection
    uint32_t stream;
    // webkit_web_view_get_page_id() of the page the video plays in
    uint64_t page;
    uint64_t frame;
    // The hole, in the pixels of the page's buffer
    int32_t x, y, width, height;
    uint32_t frameWidth, frameHeight, fourcc, planes;
    uint64_t modifier;
    uint32_t offsets[VIDEO_PLANE_MAX_PLANES];
    uint32_t strides[VIDEO_PLANE_MAX_PLANES];
};
