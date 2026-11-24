#include "videoplanes.h"

#include "subsurface.h"
#include "wayland.h"

#include <QFile>
#include <QSocketNotifier>
#include <QStandardPaths>
#include <cstring>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <wpe/webkit.h>

namespace QtWpeWebKit {

Q_LOGGING_CATEGORY(videoPlanes, "qtwpewebkit.video", QtWarningMsg)

VideoPlanes* VideoPlanes::instance = nullptr;

VideoConnection::~VideoConnection()
{
    close();
}

void VideoConnection::release(uint32_t stream, uint64_t frame)
{
    if (m_fd < 0)
        return;
    VideoPlaneMessage message {};
    message.type = VIDEO_PLANE_RELEASE;
    message.stream = stream;
    message.frame = frame;
    send(m_fd, &message, sizeof message, MSG_NOSIGNAL | MSG_DONTWAIT);
}

void VideoConnection::close()
{
    if (m_fd >= 0)
        ::close(m_fd);
    m_fd = -1;
}

bool VideoPlanes::listen()
{
    if (instance)
        return true;
    if (!waylandGlobals()) {
        qWarning("QtWpeWebKit: video on the GPU: the compositor cannot take its frames");
        return false;
    }
    QByteArray directory = QFile::encodeName(QStandardPaths::writableLocation(QStandardPaths::RuntimeLocation) + QLatin1String("/qtwpewebkit-video-XXXXXX"));
    if (!mkdtemp(directory.data())) {
        qWarning("QtWpeWebKit: video on the GPU: no directory %s", directory.constData());
        return false;
    }
    sockaddr_un address { .sun_family = AF_UNIX };
    const QByteArray path = directory + "/socket";
    const int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd < 0 || path.size() >= qsizetype(sizeof address.sun_path)) {
        qWarning("QtWpeWebKit: video on the GPU: no socket %s", path.constData());
        rmdir(directory.constData());
        return false;
    }
    strcpy(address.sun_path, path.constData());
    if (bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof address) || ::listen(fd, 8)) {
        qWarning("QtWpeWebKit: video on the GPU: cannot listen on %s", path.constData());
        ::close(fd);
        rmdir(directory.constData());
        return false;
    }
    // Sandboxed web processes see a runtime directory of their own
    webkit_web_context_add_path_to_sandbox(webkit_web_context_get_default(), directory.constData(), TRUE);
    qputenv(QTWPEWEBKIT_VIDEO_PLANE_SOCKET, path);
    // one set already, or none to keep video on the GPU, is the user's
    if (!qEnvironmentVariableIsSet("WEBKIT_GST_HOLE_PUNCH_QUIRK"))
        qputenv("WEBKIT_GST_HOLE_PUNCH_QUIRK", "tvbian");
    instance = new VideoPlanes(fd);
    return true;
}

VideoPlanes::VideoPlanes(int socket)
    : m_socket(socket)
{
    auto* notifier = new QSocketNotifier(m_socket, QSocketNotifier::Read, this);
    connect(notifier, &QSocketNotifier::activated, this, &VideoPlanes::accept);
}

void VideoPlanes::add(Subsurface* subsurface, WebKitWebView* webView)
{
    if (instance)
        instance->m_pages.insert(subsurface, webView);
}

void VideoPlanes::remove(Subsurface* subsurface)
{
    if (instance)
        instance->m_pages.remove(subsurface);
}

// A page's identifier changes as it moves to another web process
Subsurface* VideoPlanes::subsurfaceOf(uint64_t page) const
{
    for (auto it = m_pages.cbegin(); it != m_pages.cend(); ++it) {
        if (webkit_web_view_get_page_id(it.value()) == page)
            return it.key();
    }
    return nullptr;
}

void VideoPlanes::accept()
{
    int fd;
    while ((fd = accept4(m_socket, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK)) >= 0) {
        auto connection = std::make_shared<VideoConnection>(fd);
        auto* notifier = new QSocketNotifier(fd, QSocketNotifier::Read, this);
        connect(notifier, &QSocketNotifier::activated, this, [this, connection, notifier] {
            receive(connection, notifier);
        });
    }
}

void VideoPlanes::receive(std::shared_ptr<VideoConnection> connection, QSocketNotifier* notifier)
{
    for (;;) {
        VideoPlaneMessage message;
        iovec data { &message, sizeof message };
        char control[CMSG_SPACE(sizeof(int) * VIDEO_PLANE_MAX_PLANES)];
        msghdr header { .msg_iov = &data, .msg_iovlen = 1, .msg_control = control, .msg_controllen = sizeof control };
        const ssize_t size = recvmsg(connection->fd(), &header, MSG_CMSG_CLOEXEC);
        if (size < 0 && (errno == EAGAIN || errno == EINTR))
            return;
        int fds[VIDEO_PLANE_MAX_PLANES];
        unsigned fdCount = 0;
        for (cmsghdr* part = CMSG_FIRSTHDR(&header); part; part = CMSG_NXTHDR(&header, part)) {
            if (part->cmsg_level == SOL_SOCKET && part->cmsg_type == SCM_RIGHTS) {
                fdCount = (part->cmsg_len - CMSG_LEN(0)) / sizeof(int);
                memcpy(fds, CMSG_DATA(part), sizeof(int) * fdCount);
            }
        }
        if (size != sizeof message || (message.type == VIDEO_PLANE_FRAME && fdCount != message.planes)) {
            for (unsigned i = 0; i < fdCount; i++)
                ::close(fds[i]);
            // the web process went away, or speaks another protocol
            for (Subsurface* subsurface : m_pages.keys())
                subsurface->stopVideos(connection.get());
            connection->close();
            notifier->deleteLater();
            return;
        }
        Subsurface* subsurface = subsurfaceOf(message.page);
        switch (message.type) {
        case VIDEO_PLANE_FRAME:
            if (subsurface)
                subsurface->showVideoFrame(connection, message, fds);
            else {
                qCDebug(videoPlanes, "frame %llu of page %llu: no such page", (unsigned long long)message.frame, (unsigned long long)message.page);
                for (unsigned i = 0; i < fdCount; i++)
                    ::close(fds[i]);
                connection->release(message.stream, message.frame);
            }
            break;
        case VIDEO_PLANE_RECTANGLE:
            if (subsurface)
                subsurface->moveVideo(connection.get(), message);
            break;
        case VIDEO_PLANE_STOP:
            for (Subsurface* other : m_pages.keys())
                other->stopVideo(connection.get(), message.stream);
            break;
        }
    }
}

} // namespace QtWpeWebKit
