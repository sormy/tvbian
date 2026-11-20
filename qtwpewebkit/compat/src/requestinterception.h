// The UI process's side of request interception: answers the web processes' requests (webprocess/requests.cpp)
#pragma once

#include <QHash>
#include <QObject>
#include <QTemporaryDir>
#include <QThread>

class QLocalServer;
class QLocalSocket;
class QWebEnginePage;

namespace QtWpeWebKit {

class RequestInterception : public QObject {
public:
    // Must exist before the first web process starts; never destroyed, so a page outliving the application
    // leaves nothing dangling
    static RequestInterception& instance();

    void addPage(QWebEnginePage* page);
    void removePage(QWebEnginePage* page);

private:
    RequestInterception();
    void serve(QLocalSocket* socket);
    QByteArray answer(const QByteArray& request);

    QTemporaryDir m_serverDirectory;
    // Serves the web processes, which wait on each answer; the interceptors run on the UI thread, as QtWebEngine's
    QThread m_thread;
    QLocalServer* m_server;
    // By WebKit's page id, which changes when a navigation moves the page to another web process
    QHash<quint64, QWebEnginePage*> m_pages;
};

} // namespace QtWpeWebKit
