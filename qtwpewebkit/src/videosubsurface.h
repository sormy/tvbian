#pragma once

#include "videoplaneprotocol.h"

#include <QRect>
#include <QRectF>
#include <memory>
#include <vector>

struct wl_buffer;
struct wl_subsurface;
struct wl_surface;
struct wp_viewport;

namespace QtWpeWebKit {

class VideoConnection;

// A web process's video stream on a surface of its own beneath the page, where the page's hole shows it:
// the compositor may scan its frames out on a display plane
class VideoSubsurface {
public:
    VideoSubsurface(wl_surface* parent, wl_surface* page);
    ~VideoSubsurface();
    VideoSubsurface(const VideoSubsurface&) = delete;
    VideoSubsurface& operator=(const VideoSubsurface&) = delete;

    // takes the frame's file descriptors; false where it cannot be shown yet or imported, the frame then released
    bool show(std::shared_ptr<VideoConnection> connection, const VideoPlaneMessage& frame, const int* fds);
    void setHole(const QRect& hole) { m_hole = hole; }
    // the page's hole, in the page buffer's pixels
    QRect hole() const { return m_hole; }
    // where the hole lies in the window, and the part of the frame that shows through it, in fractions of the frame
    void place(const QRect& destination, const QRectF& source);
    void hide();

    struct Frame;

private:
    void applySource();
    Frame* frameFor(const VideoPlaneMessage& message, const int* fds);

    wl_surface* m_surface;
    wl_subsurface* m_subsurface;
    wp_viewport* m_viewport;
    QRect m_hole;
    QRect m_destination;
    QRectF m_source;
    QSize m_frameSize;
    // the decoder's buffers, as it recycles them: the compositor imports each once
    std::vector<std::unique_ptr<Frame>> m_frames;
};

} // namespace QtWpeWebKit
