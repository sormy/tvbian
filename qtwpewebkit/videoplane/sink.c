// tvbvideoplanesink: hands decoded dma-buf frames and the page's hole to the UI process, which shows them
// on a display plane; a frame stays referenced until the UI process releases it
#include "videoplaneprotocol.h"

#include <errno.h>
#include <gst/allocators/allocators.h>
#include <gst/video/video.h>
#include <gst/video/gstvideosink.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

// The decoder's pool runs dry if the display holds more
#define MAX_HELD_FRAMES 5
#define RELEASE_WAIT_MS 50

GST_DEBUG_CATEGORY_STATIC(tvb_video_plane_sink_debug);
#define GST_CAT_DEFAULT tvb_video_plane_sink_debug

#define TVB_TYPE_VIDEO_PLANE_SINK (tvb_video_plane_sink_get_type())
G_DECLARE_FINAL_TYPE(TvbVideoPlaneSink, tvb_video_plane_sink, TVB, VIDEO_PLANE_SINK, GstVideoSink)

struct _TvbVideoPlaneSink {
    GstVideoSink parent;
    GMutex lock;
    int socket;
    guint32 stream;
    guint64 page;
    guint64 nextFrame;
    gint rectangle[4];
    GstVideoInfoDmaDrm info;
    // frame number → GstBuffer, until released
    GHashTable* held;
};

G_DEFINE_TYPE(TvbVideoPlaneSink, tvb_video_plane_sink, GST_TYPE_VIDEO_SINK)

enum { PROP_0, PROP_PAGE_ID, PROP_RECTANGLE };

static GstStaticPadTemplate sinkTemplate = GST_STATIC_PAD_TEMPLATE("sink", GST_PAD_SINK, GST_PAD_ALWAYS,
    GST_STATIC_CAPS("video/x-raw(memory:DMABuf), format=(string)DMA_DRM"));

static void fillHeader(TvbVideoPlaneSink* sink, struct VideoPlaneMessage* message, enum VideoPlaneMessageType type)
{
    memset(message, 0, sizeof *message);
    message->type = type;
    message->stream = sink->stream;
    message->page = sink->page;
    message->x = sink->rectangle[0];
    message->y = sink->rectangle[1];
    message->width = sink->rectangle[2];
    message->height = sink->rectangle[3];
}

static gboolean sendMessage(TvbVideoPlaneSink* sink, const struct VideoPlaneMessage* message, const int* fds, guint fdCount)
{
    struct iovec data = { (void*)message, sizeof *message };
    char control[CMSG_SPACE(sizeof(int) * VIDEO_PLANE_MAX_PLANES)] = { 0 };
    struct msghdr header = { .msg_iov = &data, .msg_iovlen = 1 };
    if (fdCount) {
        header.msg_control = control;
        header.msg_controllen = CMSG_SPACE(sizeof(int) * fdCount);
        struct cmsghdr* fdsMessage = CMSG_FIRSTHDR(&header);
        fdsMessage->cmsg_level = SOL_SOCKET;
        fdsMessage->cmsg_type = SCM_RIGHTS;
        fdsMessage->cmsg_len = CMSG_LEN(sizeof(int) * fdCount);
        memcpy(CMSG_DATA(fdsMessage), fds, sizeof(int) * fdCount);
    }
    if (sendmsg(sink->socket, &header, MSG_NOSIGNAL) == sizeof *message)
        return TRUE;
    GST_WARNING_OBJECT(sink, "the UI process went away: %s", g_strerror(errno));
    close(sink->socket);
    sink->socket = -1;
    return FALSE;
}

// Takes back the frames the UI process released, waiting for one at most timeout ms
static void takeReleased(TvbVideoPlaneSink* sink, int timeout)
{
    struct pollfd pending = { sink->socket, POLLIN, 0 };
    while (sink->socket >= 0 && poll(&pending, 1, timeout) > 0) {
        struct VideoPlaneMessage message;
        if (recv(sink->socket, &message, sizeof message, MSG_DONTWAIT) != sizeof message)
            break;
        if (message.type == VIDEO_PLANE_RELEASE) {
            GST_DEBUG_OBJECT(sink, "released %" G_GUINT64_FORMAT, message.frame);
            g_hash_table_remove(sink->held, &message.frame);
        }
        timeout = 0;
    }
}

static gboolean tvb_video_plane_sink_start(GstBaseSink* base)
{
    TvbVideoPlaneSink* sink = TVB_VIDEO_PLANE_SINK(base);
    static guint32 lastStream;
    const char* path = g_getenv(QTWPEWEBKIT_VIDEO_PLANE_SOCKET);
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    if (!path || strlen(path) >= sizeof address.sun_path) {
        GST_ELEMENT_ERROR(sink, RESOURCE, NOT_FOUND, ("No video plane socket in %s", QTWPEWEBKIT_VIDEO_PLANE_SOCKET), (NULL));
        return FALSE;
    }
    strcpy(address.sun_path, path);
    int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0 || connect(fd, (struct sockaddr*)&address, sizeof address)) {
        GST_ELEMENT_ERROR(sink, RESOURCE, OPEN_WRITE, ("Cannot reach the video plane socket %s", path), GST_ERROR_SYSTEM);
        if (fd >= 0)
            close(fd);
        return FALSE;
    }
    g_mutex_lock(&sink->lock);
    sink->socket = fd;
    sink->stream = g_atomic_int_add(&lastStream, 1) + 1;
    g_mutex_unlock(&sink->lock);
    return TRUE;
}

static gboolean tvb_video_plane_sink_stop(GstBaseSink* base)
{
    TvbVideoPlaneSink* sink = TVB_VIDEO_PLANE_SINK(base);
    g_mutex_lock(&sink->lock);
    if (sink->socket >= 0) {
        struct VideoPlaneMessage message;
        fillHeader(sink, &message, VIDEO_PLANE_STOP);
        if (sendMessage(sink, &message, NULL, 0))
            close(sink->socket);
        sink->socket = -1;
    }
    g_hash_table_remove_all(sink->held);
    g_mutex_unlock(&sink->lock);
    return TRUE;
}

static gboolean tvb_video_plane_sink_set_caps(GstBaseSink* base, GstCaps* caps)
{
    TvbVideoPlaneSink* sink = TVB_VIDEO_PLANE_SINK(base);
    if (!gst_video_info_dma_drm_from_caps(&sink->info, caps)) {
        GST_WARNING_OBJECT(sink, "not a DRM format: %" GST_PTR_FORMAT, caps);
        return FALSE;
    }
    return GST_BASE_SINK_CLASS(tvb_video_plane_sink_parent_class)->set_caps(base, caps);
}

static gboolean tvb_video_plane_sink_propose_allocation(GstBaseSink*, GstQuery* query)
{
    gst_query_add_allocation_meta(query, GST_VIDEO_META_API_TYPE, NULL);
    return TRUE;
}

static GstFlowReturn tvb_video_plane_sink_show_frame(GstVideoSink* videoSink, GstBuffer* buffer)
{
    TvbVideoPlaneSink* sink = TVB_VIDEO_PLANE_SINK(videoSink);
    const GstVideoInfo* info = &sink->info.vinfo;
    GstVideoMeta* meta = gst_buffer_get_video_meta(buffer);
    struct VideoPlaneMessage message;
    int fds[VIDEO_PLANE_MAX_PLANES];

    g_mutex_lock(&sink->lock);
    fillHeader(sink, &message, VIDEO_PLANE_FRAME);
    message.frame = ++sink->nextFrame;
    message.frameWidth = GST_VIDEO_INFO_WIDTH(info);
    message.frameHeight = GST_VIDEO_INFO_HEIGHT(info);
    message.fourcc = sink->info.drm_fourcc;
    message.modifier = sink->info.drm_modifier;
    message.planes = meta ? meta->n_planes : GST_VIDEO_INFO_N_PLANES(info);
    GST_LOG_OBJECT(sink, "frame %" G_GUINT64_FORMAT " %ux%u, page %" G_GUINT64_FORMAT, message.frame, message.frameWidth, message.frameHeight, sink->page);
    for (guint plane = 0; plane < message.planes && plane < VIDEO_PLANE_MAX_PLANES; plane++) {
        gsize offset = meta ? meta->offset[plane] : GST_VIDEO_INFO_PLANE_OFFSET(info, plane);
        guint memoryIndex, memoryCount;
        gsize skip;
        if (!gst_buffer_find_memory(buffer, offset, 1, &memoryIndex, &memoryCount, &skip)
            || !gst_is_dmabuf_memory(gst_buffer_peek_memory(buffer, memoryIndex))) {
            g_mutex_unlock(&sink->lock);
            GST_ELEMENT_ERROR(sink, STREAM, FORMAT, ("A frame not in dma-buf memory"), (NULL));
            return GST_FLOW_ERROR;
        }
        fds[plane] = gst_dmabuf_memory_get_fd(gst_buffer_peek_memory(buffer, memoryIndex));
        message.offsets[plane] = skip;
        message.strides[plane] = meta ? meta->stride[plane] : GST_VIDEO_INFO_PLANE_STRIDE(info, plane);
    }

    if (sink->socket >= 0) {
        takeReleased(sink, 0);
        if (g_hash_table_size(sink->held) >= MAX_HELD_FRAMES) {
            gint64 start = g_get_monotonic_time();
            takeReleased(sink, RELEASE_WAIT_MS);
            GST_INFO_OBJECT(sink, "waited %" G_GINT64_FORMAT " us for a release, %u held", g_get_monotonic_time() - start, g_hash_table_size(sink->held));
        }
        struct stat file;
        fstat(fds[0], &file);
        GST_DEBUG_OBJECT(sink, "sent %" G_GUINT64_FORMAT " inode %lu", message.frame, (unsigned long)file.st_ino);
        if (sendMessage(sink, &message, fds, message.planes))
            g_hash_table_insert(sink->held, g_memdup2(&message.frame, sizeof message.frame), gst_buffer_ref(buffer));
    }
    g_mutex_unlock(&sink->lock);
    return GST_FLOW_OK;
}

static void tvb_video_plane_sink_set_property(GObject* object, guint id, const GValue* value, GParamSpec* spec)
{
    TvbVideoPlaneSink* sink = TVB_VIDEO_PLANE_SINK(object);
    g_mutex_lock(&sink->lock);
    switch (id) {
    case PROP_PAGE_ID:
        sink->page = g_value_get_uint64(value);
        break;
    case PROP_RECTANGLE: {
        gint rectangle[4];
        const char* text = g_value_get_string(value);
        if (!text || sscanf(text, "%d,%d,%d,%d", &rectangle[0], &rectangle[1], &rectangle[2], &rectangle[3]) != 4
            || !memcmp(rectangle, sink->rectangle, sizeof rectangle))
            break;
        memcpy(sink->rectangle, rectangle, sizeof rectangle);
        GST_DEBUG_OBJECT(sink, "hole %d,%d %dx%d", rectangle[0], rectangle[1], rectangle[2], rectangle[3]);
        if (sink->socket >= 0) {
            struct VideoPlaneMessage message;
            fillHeader(sink, &message, VIDEO_PLANE_RECTANGLE);
            sendMessage(sink, &message, NULL, 0);
        }
        break;
    }
    default:
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, id, spec);
    }
    g_mutex_unlock(&sink->lock);
}

static void tvb_video_plane_sink_get_property(GObject* object, guint id, GValue* value, GParamSpec* spec)
{
    TvbVideoPlaneSink* sink = TVB_VIDEO_PLANE_SINK(object);
    g_mutex_lock(&sink->lock);
    switch (id) {
    case PROP_PAGE_ID:
        g_value_set_uint64(value, sink->page);
        break;
    case PROP_RECTANGLE:
        g_value_take_string(value, g_strdup_printf("%d,%d,%d,%d", sink->rectangle[0], sink->rectangle[1], sink->rectangle[2], sink->rectangle[3]));
        break;
    default:
        G_OBJECT_WARN_INVALID_PROPERTY_ID(object, id, spec);
    }
    g_mutex_unlock(&sink->lock);
}

static void tvb_video_plane_sink_finalize(GObject* object)
{
    TvbVideoPlaneSink* sink = TVB_VIDEO_PLANE_SINK(object);
    g_hash_table_destroy(sink->held);
    g_mutex_clear(&sink->lock);
    G_OBJECT_CLASS(tvb_video_plane_sink_parent_class)->finalize(object);
}

static void tvb_video_plane_sink_init(TvbVideoPlaneSink* sink)
{
    g_mutex_init(&sink->lock);
    sink->socket = -1;
    sink->held = g_hash_table_new_full(g_int64_hash, g_int64_equal, g_free, (GDestroyNotify)gst_buffer_unref);
}

static void tvb_video_plane_sink_class_init(TvbVideoPlaneSinkClass* klass)
{
    GObjectClass* objectClass = G_OBJECT_CLASS(klass);
    GstElementClass* elementClass = GST_ELEMENT_CLASS(klass);
    GstBaseSinkClass* baseSinkClass = GST_BASE_SINK_CLASS(klass);

    objectClass->set_property = tvb_video_plane_sink_set_property;
    objectClass->get_property = tvb_video_plane_sink_get_property;
    objectClass->finalize = tvb_video_plane_sink_finalize;
    g_object_class_install_property(objectClass, PROP_PAGE_ID,
        g_param_spec_uint64("page-id", "Page ID", "The page the video plays in", 0, G_MAXUINT64, 0, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
    g_object_class_install_property(objectClass, PROP_RECTANGLE,
        g_param_spec_string("rectangle", "Rectangle", "The page's hole: x,y,width,height in the page buffer's pixels", "0,0,0,0",
            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));

    gst_element_class_add_static_pad_template(elementClass, &sinkTemplate);
    gst_element_class_set_static_metadata(elementClass, "Video plane sink", "Sink/Video",
        "Hands dma-buf frames to the UI process for a display plane", "TVBian");

    baseSinkClass->start = tvb_video_plane_sink_start;
    baseSinkClass->stop = tvb_video_plane_sink_stop;
    baseSinkClass->set_caps = tvb_video_plane_sink_set_caps;
    baseSinkClass->propose_allocation = tvb_video_plane_sink_propose_allocation;
    GST_VIDEO_SINK_CLASS(klass)->show_frame = tvb_video_plane_sink_show_frame;
}

static gboolean plugin_init(GstPlugin* plugin)
{
    GST_DEBUG_CATEGORY_INIT(tvb_video_plane_sink_debug, "tvbvideoplanesink", 0, "Video plane sink");
    return gst_element_register(plugin, "tvbvideoplanesink", GST_RANK_NONE, TVB_TYPE_VIDEO_PLANE_SINK);
}

#define PACKAGE "qtwpewebkit"
GST_PLUGIN_DEFINE(GST_VERSION_MAJOR, GST_VERSION_MINOR, tvbvideoplane, "Video frames for the UI process's display planes",
    plugin_init, "0.1.0", "LGPL", PACKAGE, "https://tvbian.com")
