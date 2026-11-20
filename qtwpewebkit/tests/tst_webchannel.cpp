// QWebChannel between C++ objects and the page's scripts: methods, properties and signals, in either world
#include "webtest.h"

#include <QFile>
#include <QWebChannel>
#include <QWebEngineScript>

class Bridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString text READ text WRITE setText NOTIFY textChanged)
public:
    QString text() const { return m_text; }
    void setText(const QString& text)
    {
        if (text == m_text)
            return;
        m_text = text;
        Q_EMIT textChanged();
    }
    Q_INVOKABLE int add(int a, int b) const { return a + b; }
    Q_INVOKABLE QVariantMap describe(const QVariantList& items) const
    {
        return { { QStringLiteral("count"), items.size() }, { QStringLiteral("first"), items.value(0) } };
    }

Q_SIGNALS:
    void textChanged();
    void pinged(const QString& message);

private:
    QString m_text = QStringLiteral("initial");
};

class tst_WebChannel : public QObject {
    Q_OBJECT

private Q_SLOTS:
    void init()
    {
        m_channel = std::make_unique<QWebChannel>();
        m_bridge = std::make_unique<Bridge>();
        m_channel->registerObject(QStringLiteral("bridge"), m_bridge.get());
    }

    void cleanup()
    {
        m_channel.reset();
        m_bridge.reset();
    }

    void roundTrip_data()
    {
        QTest::addColumn<quint32>("worldId");
        QTest::newRow("main world") << quint32(QWebEngineScript::MainWorld);
        QTest::newRow("application world") << quint32(QWebEngineScript::ApplicationWorld);
    }

    void roundTrip()
    {
        QFETCH(quint32, worldId);
        ShownView shown;
        QWebEnginePage* page = shown.page();
        page->setWebChannel(m_channel.get(), worldId);
        QCOMPARE(page->webChannel(), m_channel.get());
        QVERIFY(setsHtml(page, QStringLiteral("<title>channel</title>")));
        connectChannel(page, worldId);

        QCOMPARE(evaluate(page, QStringLiteral("bridge.text"), worldId), QVariant(QStringLiteral("initial")));

        evaluate(page, QStringLiteral("bridge.add(2, 3, sum => document.title = 'sum ' + sum)"), worldId);
        QTRY_COMPARE(page->title(), QStringLiteral("sum 5"));

        evaluate(page, QStringLiteral("bridge.describe(['ж', 2], d => document.title = d.count + ' ' + d.first)"), worldId);
        QTRY_COMPARE(page->title(), QStringLiteral("2 ж"));

        evaluate(page, QStringLiteral("bridge.text = 'from page'"), worldId);
        QTRY_COMPARE(m_bridge->text(), QStringLiteral("from page"));

        evaluate(page, QStringLiteral("bridge.textChanged.connect(() => document.title = 'text ' + bridge.text)"), worldId);
        m_bridge->setText(QStringLiteral("from C++"));
        QTRY_COMPARE(page->title(), QStringLiteral("text from C++"));

        evaluate(page, QStringLiteral("bridge.pinged.connect(message => document.title = 'pinged ' + message)"), worldId);
        Q_EMIT m_bridge->pinged(QStringLiteral("héllo"));
        QTRY_COMPARE(page->title(), QStringLiteral("pinged héllo"));
    }

    void otherWorldHasNoTransport()
    {
        ShownView shown;
        shown.page()->setWebChannel(m_channel.get(), QWebEngineScript::ApplicationWorld);
        QVERIFY(setsHtml(shown.page(), QStringLiteral("<title>channel</title>")));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("typeof qt"), QWebEngineScript::ApplicationWorld), QVariant(QStringLiteral("object")));
        QCOMPARE(evaluate(shown.page(), QStringLiteral("typeof qt")), QVariant(QStringLiteral("undefined")));
    }

    void survivesNavigation()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        page->setWebChannel(m_channel.get());
        QVERIFY(setsHtml(page, QStringLiteral("<title>first</title>")));
        QVERIFY(setsHtml(page, QStringLiteral("<title>second</title>")));
        connectChannel(page, QWebEngineScript::MainWorld);
        evaluate(page, QStringLiteral("bridge.add(1, 1, sum => document.title = 'sum ' + sum)"));
        QTRY_COMPARE(page->title(), QStringLiteral("sum 2"));
    }

    void removed()
    {
        ShownView shown;
        QWebEnginePage* page = shown.page();
        page->setWebChannel(m_channel.get());
        page->setWebChannel(nullptr);
        QCOMPARE(page->webChannel(), nullptr);
        QVERIFY(setsHtml(page, QStringLiteral("<title>none</title>")));
        QCOMPARE(evaluate(page, QStringLiteral("typeof qt")), QVariant(QStringLiteral("undefined")));
    }

private:
    // Runs qwebchannel.js in the world and waits until the bridge object is there
    static void connectChannel(QWebEnginePage* page, quint32 worldId)
    {
        QFile library(QStringLiteral(":/qtwebchannel/qwebchannel.js"));
        QVERIFY(library.open(QIODevice::ReadOnly));
        evaluate(page, QString::fromUtf8(library.readAll()) + QStringLiteral(";1"), worldId);
        QCOMPARE(evaluate(page, QStringLiteral("typeof qt.webChannelTransport"), worldId), QVariant(QStringLiteral("object")));
        evaluate(page, QStringLiteral("new QWebChannel(qt.webChannelTransport, channel => window.bridge = channel.objects.bridge); 1"), worldId);
        QTRY_COMPARE(evaluate(page, QStringLiteral("typeof window.bridge"), worldId), QVariant(QStringLiteral("object")));
    }

    std::unique_ptr<QWebChannel> m_channel;
    std::unique_ptr<Bridge> m_bridge;
};

QTEST_MAIN(tst_WebChannel)
#include "tst_webchannel.moc"
