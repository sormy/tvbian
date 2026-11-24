#pragma once

#include "videoplaneprotocol.h"

#include <QHash>
#include <QLoggingCategory>
#include <QObject>
#include <memory>

class QSocketNotifier;
typedef struct _WebKitWebView WebKitWebView;

namespace QtWpeWebKit {

Q_DECLARE_LOGGING_CATEGORY(videoPlanes)

class Subsurface;

// A web process's connection: its sinks' frames come in, their releases go out
class VideoConnection {
public:
    explicit VideoConnection(int fd)
        : m_fd(fd)
    {
    }
    ~VideoConnection();
    int fd() const { return m_fd; }
    void release(uint32_t stream, uint64_t frame);
    void close();

private:
    int m_fd;
};

// Video frames of the web processes shown beneath their pages' holes: WebKit is told to punch the holes
// and where to send the frames, which go to the page's subsurface
class VideoPlanes : public QObject {
public:
    // before the first web process starts; false where the compositor cannot take the frames
    static bool listen();
    static void add(Subsurface* subsurface, WebKitWebView* webView);
    static void remove(Subsurface* subsurface);

private:
    explicit VideoPlanes(int socket);
    static VideoPlanes* instance;
    void accept();
    void receive(std::shared_ptr<VideoConnection> connection, QSocketNotifier* notifier);
    Subsurface* subsurfaceOf(uint64_t page) const;

    int m_socket;
    QHash<Subsurface*, WebKitWebView*> m_pages;
};

} // namespace QtWpeWebKit
