// Downloads: the profile's request, accepting to a chosen path, progress, completion and cancelling
#include "webtest.h"

#include <QFile>
#include <QTemporaryDir>
#include <QWebEngineDownloadRequest>
#include <QWebEngineProfile>

static const QByteArray fileData = QByteArray(256 * 1024, 'x') + "end";

class tst_Downloads : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_server = std::make_unique<TestServer>();
        m_server->route("/file.bin", HttpReply { fileData, "application/octet-stream", 200,
                                         { { "Content-Disposition", "attachment; filename=\"file.bin\"" } } });
        m_server->route("/page", "<a id=link href=/file.bin download>file</a>");
        m_profile = std::make_unique<QWebEngineProfile>();
    }

    void cleanup()
    {
        m_profile.reset();
        m_server.reset();
    }

    void accepted_data()
    {
        QTest::addColumn<QString>("trigger");
        QTest::newRow("page download") << QStringLiteral("download");
        QTest::newRow("navigation to attachment") << QStringLiteral("navigate");
        QTest::newRow("download link") << QStringLiteral("link");
    }

    void accepted()
    {
        QFETCH(QString, trigger);
        QTemporaryDir directory;
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/page")));

        QPointer<QWebEngineDownloadRequest> download;
        QList<QWebEngineDownloadRequest::DownloadState> states;
        int progressSignals = 0;
        connect(m_profile.get(), &QWebEngineProfile::downloadRequested, this, [&](QWebEngineDownloadRequest* request) {
            download = request;
            connect(request, &QWebEngineDownloadRequest::stateChanged, this, [&](auto state) { states.append(state); });
            connect(request, &QWebEngineDownloadRequest::receivedBytesChanged, this, [&] { ++progressSignals; });
            QCOMPARE(request->state(), QWebEngineDownloadRequest::DownloadRequested);
            request->setDownloadDirectory(directory.path());
            request->setDownloadFileName(QStringLiteral("saved.bin"));
            request->accept();
        });
        if (trigger == QLatin1String("download"))
            page->download(m_server->url("/file.bin"));
        else if (trigger == QLatin1String("navigate"))
            page->load(m_server->url("/file.bin"));
        else
            evaluate(page, QStringLiteral("document.getElementById('link').click()"));

        QTRY_VERIFY_WITH_TIMEOUT(download && download->isFinished(), asyncTimeout);
        QCOMPARE(download->state(), QWebEngineDownloadRequest::DownloadCompleted);
        QCOMPARE(states.last(), QWebEngineDownloadRequest::DownloadCompleted);
        QCOMPARE(download->url(), m_server->url("/file.bin"));
        QCOMPARE(download->suggestedFileName(), QStringLiteral("file.bin"));
        QCOMPARE(download->mimeType(), QStringLiteral("application/octet-stream"));
        QCOMPARE(download->downloadDirectory(), directory.path());
        QCOMPARE(download->downloadFileName(), QStringLiteral("saved.bin"));
        QCOMPARE(download->totalBytes(), fileData.size());
        QCOMPARE(download->receivedBytes(), fileData.size());
        QVERIFY(progressSignals > 0);
        QCOMPARE(download->page(), page);
        QFile saved(directory.filePath(QStringLiteral("saved.bin")));
        QVERIFY(saved.open(QIODevice::ReadOnly));
        QCOMPARE(saved.readAll(), fileData);
        QCOMPARE(page->url(), m_server->url("/page"));
    }

    void notAccepted_data()
    {
        QTest::addColumn<bool>("cancel");
        QTest::newRow("ignored") << false;
        QTest::newRow("cancelled") << true;
    }

    // QtWebEngine cancels a request left unanswered, and may delete it right away
    void notAccepted()
    {
        QFETCH(bool, cancel);
        QTemporaryDir directory;
        m_profile->setDownloadPath(directory.path());
        QCOMPARE(m_profile->downloadPath(), directory.path());
        ShownView shown(new QWebEnginePage(m_profile.get()));
        bool requested = false;
        connect(m_profile.get(), &QWebEngineProfile::downloadRequested, this, [&](QWebEngineDownloadRequest* request) {
            requested = true;
            QCOMPARE(request->downloadDirectory(), directory.path());
            if (cancel) {
                request->cancel();
                QCOMPARE(request->state(), QWebEngineDownloadRequest::DownloadCancelled);
                QVERIFY(request->isFinished());
            }
        });
        shown.page()->download(m_server->url("/file.bin"));
        QTRY_VERIFY_WITH_TIMEOUT(requested, asyncTimeout);
        QTest::qWait(500);
        QVERIFY(QDir(directory.path()).isEmpty());
    }

    void failed()
    {
        QTemporaryDir directory;
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QPointer<QWebEngineDownloadRequest> download;
        connect(m_profile.get(), &QWebEngineProfile::downloadRequested, this, [&](QWebEngineDownloadRequest* request) {
            download = request;
            request->setDownloadDirectory(directory.path());
            request->accept();
        });
        shown.page()->download(m_server->url("/missing.bin"));
        QTRY_VERIFY_WITH_TIMEOUT(download && download->isFinished(), asyncTimeout);
        QCOMPARE(download->state(), QWebEngineDownloadRequest::DownloadInterrupted);
        QVERIFY(download->interruptReason() != QWebEngineDownloadRequest::NoReason);
        QVERIFY(!download->interruptReasonString().isEmpty());
    }

    // Save Page keeps the page as shown, not as served: an MHTML archive of its document after its scripts ran
    void savePage()
    {
        QTemporaryDir directory;
        ShownView shown(new QWebEnginePage(m_profile.get()));
        QWebEnginePage* page = shown.page();
        QVERIFY(loadsOk(page, m_server->url("/page")));
        evaluate(page, QStringLiteral("document.body.append('changed after load')"));
        QPointer<QWebEngineDownloadRequest> download;
        connect(m_profile.get(), &QWebEngineProfile::downloadRequested, this, [&](QWebEngineDownloadRequest* request) {
            download = request;
            QVERIFY(request->isSavePageDownload());
            QCOMPARE(request->savePageFormat(), QWebEngineDownloadRequest::MimeHtmlSaveFormat);
            request->setDownloadDirectory(directory.path());
            request->setDownloadFileName(QStringLiteral("page.mhtml"));
            request->accept();
        });
        page->triggerAction(QWebEnginePage::SavePage);
        QTRY_VERIFY_WITH_TIMEOUT(download && download->isFinished(), asyncTimeout);
        QCOMPARE(download->state(), QWebEngineDownloadRequest::DownloadCompleted);
        QFile saved(directory.filePath(QStringLiteral("page.mhtml")));
        QVERIFY(saved.open(QIODevice::ReadOnly));
        const QByteArray archive = saved.readAll();
        QVERIFY2(archive.contains("MIME-Version: 1.0"), archive.left(200).constData());
        QVERIFY2(archive.contains("changed after load"), archive.left(400).constData());
    }

private:
    std::unique_ptr<TestServer> m_server;
    std::unique_ptr<QWebEngineProfile> m_profile;
};

QTEST_MAIN(tst_Downloads)
#include "tst_downloads.moc"
