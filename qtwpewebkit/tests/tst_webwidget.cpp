// QtWpeWebKit::WebWidget on its own, without the QtWebEngine layer: loading, its signals and its frames
#include "webtest.h"
#include "webwidget.h"

class tst_WebWidget : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_server = std::make_unique<TestServer>();
        m_server->route("/page", "<title>widget page</title><body style=\"margin: 0; background: rgb(0, 255, 0)\">");
        m_widget = std::make_unique<QtWpeWebKit::WebWidget>();
        m_widget->resize(300, 200);
        m_widget->show();
        QVERIFY(QTest::qWaitForWindowExposed(m_widget.get()));
    }

    void cleanup()
    {
        m_widget.reset();
        m_server.reset();
    }

    void loads()
    {
        QSignalSpy title(m_widget.get(), &QtWpeWebKit::WebWidget::titleChanged);
        QSignalSpy url(m_widget.get(), &QtWpeWebKit::WebWidget::urlChanged);
        QSignalSpy progress(m_widget.get(), &QtWpeWebKit::WebWidget::loadProgress);
        QSignalSpy finished(m_widget.get(), &QtWpeWebKit::WebWidget::loadFinished);
        m_widget->load(m_server->url("/page"));
        QVERIFY(finished.wait(asyncTimeout));
        QTest::qWait(200);
        QCOMPARE(finished.count(), 1);
        QCOMPARE(finished.first().first().toBool(), true);
        QCOMPARE(progress.last().first().toInt(), 100);
        QCOMPARE(url.last().first().toUrl(), m_server->url("/page"));
        QTRY_COMPARE(m_widget->title(), QStringLiteral("widget page"));
        QCOMPARE(title.last().first().toString(), QStringLiteral("widget page"));
        QCOMPARE(m_widget->url(), m_server->url("/page"));
        QVERIFY(m_widget->webView());
    }

    void loadFailure()
    {
        QSignalSpy finished(m_widget.get(), &QtWpeWebKit::WebWidget::loadFinished);
        QTcpServer closed;
        closed.listen(QHostAddress::LocalHost);
        const QUrl refused(QStringLiteral("http://127.0.0.1:%1/").arg(closed.serverPort()));
        closed.close();
        m_widget->load(refused);
        QVERIFY(finished.wait(asyncTimeout));
        QTest::qWait(300);
        QCOMPARE(finished.count(), 1);
        QCOMPARE(finished.first().first().toBool(), false);
    }

    void sharesWebView()
    {
        QtWpeWebKit::WebWidget other(m_widget->webView());
        QCOMPARE(other.webView(), m_widget->webView());
        QSignalSpy title(&other, &QtWpeWebKit::WebWidget::titleChanged);
        m_widget->load(m_server->url("/page"));
        QTRY_COMPARE(other.title(), QStringLiteral("widget page"));
        QVERIFY(!title.isEmpty());
    }

    void frames()
    {
        QSignalSpy finished(m_widget.get(), &QtWpeWebKit::WebWidget::loadFinished);
        m_widget->load(m_server->url("/page"));
        QVERIFY(finished.wait(asyncTimeout));
        auto centre = [this] { return m_widget->grabFramebuffer().pixelColor(150, 100); };
        QTRY_COMPARE_WITH_TIMEOUT(centre(), QColor(0, 255, 0), asyncTimeout);
    }

    void keySent()
    {
        QSignalSpy sent(m_widget.get(), &QtWpeWebKit::WebWidget::keySent);
        QTest::keyClick(m_widget.get(), Qt::Key_A);
        QCOMPARE(sent.count(), 2);
    }

private:
    std::unique_ptr<TestServer> m_server;
    std::unique_ptr<QtWpeWebKit::WebWidget> m_widget;
};

QTEST_MAIN(tst_WebWidget)
#include "tst_webwidget.moc"
