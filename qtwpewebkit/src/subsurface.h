#pragma once

#include "videoplaneprotocol.h"

#include <QSize>
#include <map>
#include <memory>

class QWidget;
struct wl_callback;
struct wl_subsurface;
struct wl_surface;
struct wp_viewport;
typedef struct _WPEBuffer WPEBuffer;
typedef struct _WPEView WPEView;

namespace QtWpeWebKit {

class VideoConnection;
class VideoSubsurface;

// WebKit's GPU frames handed to the compositor as they are, on a surface of their own above the
// widget, so neither the widget nor Qt copies them
class Subsurface {
public:
    // null where the compositor cannot take WebKit's frames this way
    static std::unique_ptr<Subsurface> create(QWidget* widget, WPEView* view);
    ~Subsurface();

    // false where this frame cannot go this way: the caller draws it instead
    bool present(WPEBuffer* buffer);
    // follows the widget within its window
    void place();
    void hide();
    // the compositor showed the frame: WebKit may draw the next
    void frameShown();

    // a web process's video of this page, beneath it where its hole is; takes the frame's file descriptors
    void showVideoFrame(std::shared_ptr<VideoConnection> connection, const VideoPlaneMessage& frame, const int* fds);
    void moveVideo(const VideoConnection* connection, const VideoPlaneMessage& rectangle);
    void stopVideo(const VideoConnection* connection, uint32_t stream);
    void stopVideos(const VideoConnection* connection);

private:
    Subsurface(QWidget* widget, WPEView* view);
    bool attachToWindow();
    void destroy();
    void placeVideos();

    using VideoKey = std::pair<const VideoConnection*, uint32_t>;

    QWidget* m_widget;
    WPEView* m_view;
    wl_surface* m_parent = nullptr;
    wl_surface* m_surface = nullptr;
    wl_subsurface* m_subsurface = nullptr;
    wp_viewport* m_viewport = nullptr;
    wl_callback* m_frame = nullptr;
    WPEBuffer* m_frameBuffer = nullptr;
    QSize m_size;
    QSize m_bufferSize;
    std::map<VideoKey, std::unique_ptr<VideoSubsurface>> m_videos;
};

} // namespace QtWpeWebKit
