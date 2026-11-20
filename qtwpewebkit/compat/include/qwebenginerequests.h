// QtWebEngine's small request and result types; protocol handlers, client certificates and notifications are not wired
#pragma once

#include <QByteArray>
#include <QIcon>
#include <QImage>
#include <QMap>
#include <QObject>
#include <QRect>
#include <QSslCertificate>
#include <QUrl>
#include <functional>
#include <memory>
#include <utility>

class QWebEnginePage;
typedef struct _WebKitWebView WebKitWebView;

class QWebEngineFindTextResult {
public:
    QWebEngineFindTextResult() = default;
    QWebEngineFindTextResult(int numberOfMatches, int activeMatch)
        : m_numberOfMatches(numberOfMatches)
        , m_activeMatch(activeMatch)
    {
    }
    int numberOfMatches() const { return m_numberOfMatches; }
    int activeMatch() const { return m_activeMatch; }

private:
    int m_numberOfMatches = 0;
    int m_activeMatch = 0;
};

class QWebEngineNewWindowRequest : public QObject {
    Q_OBJECT
public:
    enum DestinationType { InNewWindow, InNewTab, InNewDialog, InNewBackgroundTab };
    Q_ENUM(DestinationType)

    QWebEngineNewWindowRequest(DestinationType destination, const QUrl& requestedUrl, bool userInitiated,
        WebKitWebView* opener = nullptr)
        : m_destination(destination)
        , m_requestedUrl(requestedUrl)
        , m_userInitiated(userInitiated)
        , m_opener(opener)
    {
    }
    // The page made for this request, which WebKit loads with window.opener kept
    QWebEnginePage* openedPage() const { return m_openedPage; }
    DestinationType destination() const { return m_destination; }
    QUrl requestedUrl() const { return m_requestedUrl; }
    QRect requestedGeometry() const { return {}; }
    bool isUserInitiated() const { return m_userInitiated; }
    // A page made while the request is handled opens in place, window.opener kept; any other loads the URL
    // afresh, the opener relation lost
    void openIn(QWebEnginePage* page);

private:
    DestinationType m_destination;
    QUrl m_requestedUrl;
    bool m_userInitiated;
    WebKitWebView* m_opener;
    QWebEnginePage* m_openedPage = nullptr;
};

class QWebEngineHttpRequest {
public:
    enum Method { Get, Post };

    explicit QWebEngineHttpRequest(const QUrl& url = {}, Method method = Get)
        : m_url(url)
        , m_method(method)
    {
    }
    static QWebEngineHttpRequest postRequest(const QUrl& url, const QMap<QString, QString>&) { return QWebEngineHttpRequest(url, Post); }
    Method method() const { return m_method; }
    void setMethod(Method method) { m_method = method; }
    QUrl url() const { return m_url; }
    void setUrl(const QUrl& url) { m_url = url; }
    QByteArray postData() const { return m_postData; }
    void setPostData(const QByteArray& postData) { m_postData = postData; }
    bool hasHeader(const QByteArray& name) const { return m_headers.contains(name); }
    QList<QByteArray> headers() const { return m_headers.keys(); }
    QByteArray header(const QByteArray& name) const { return m_headers.value(name); }
    void setHeader(const QByteArray& name, const QByteArray& value) { m_headers.insert(name, value); }
    void unsetHeader(const QByteArray& name) { m_headers.remove(name); }

private:
    QUrl m_url;
    Method m_method;
    QByteArray m_postData;
    QMap<QByteArray, QByteArray> m_headers;
};

class QWebEngineFullScreenRequest {
public:
    QWebEngineFullScreenRequest(const QUrl& origin, bool toggleOn, const std::function<void(bool)>& setFullScreen)
        : m_origin(origin)
        , m_toggleOn(toggleOn)
        , m_answer(std::make_shared<Answer>(setFullScreen, !toggleOn))
    {
    }
    void accept() { m_answer->give(m_toggleOn); }
    void reject() { m_answer->give(!m_toggleOn); }
    bool toggleOn() const { return m_toggleOn; }
    QUrl origin() const { return m_origin; }

private:
    // WebKit waits for an answer: a request no copy of which was answered is refused
    struct Answer {
        Answer(const std::function<void(bool)>& setFullScreen, bool refusal)
            : setFullScreen(setFullScreen)
            , refusal(refusal)
        {
        }
        ~Answer() { give(refusal); }
        void give(bool on)
        {
            if (!std::exchange(given, true))
                setFullScreen(on);
        }
        std::function<void(bool)> setFullScreen;
        bool refusal;
        bool given = false;
    };

    QUrl m_origin;
    bool m_toggleOn;
    std::shared_ptr<Answer> m_answer;
};

class QWebEngineRegisterProtocolHandlerRequest {
public:
    QWebEngineRegisterProtocolHandlerRequest() = default;
    void accept() { }
    void reject() { }
    QUrl origin() const { return {}; }
    QString scheme() const { return {}; }
};

class QWebEngineCertificateError {
public:
    enum Type {
        SslPinnedKeyNotInCertificateChain = -150,
        CertificateCommonNameInvalid = -200,
        CertificateDateInvalid = -201,
        CertificateAuthorityInvalid = -202,
        CertificateContainsErrors = -203,
        CertificateNoRevocationMechanism = -204,
        CertificateUnableToCheckRevocation = -205,
        CertificateRevoked = -206,
        CertificateInvalid = -207,
        CertificateWeakSignatureAlgorithm = -208,
        CertificateNonUniqueName = -210,
        CertificateWeakKey = -211,
        CertificateNameConstraintViolation = -212,
        CertificateValidityTooLong = -213,
        CertificateTransparencyRequired = -214,
        CertificateSymantecLegacy = -215,
        CertificateKnownInterceptionBlocked = -217,
        SslObsoleteVersion = -218,
    };

    QWebEngineCertificateError(const QUrl& url, Type type, const QString& description,
        const QList<QSslCertificate>& certificateChain, const std::function<void(bool)>& answer)
        : m_url(url)
        , m_type(type)
        , m_description(description)
        , m_certificateChain(certificateChain)
        , m_answer(answer)
    {
    }
    Type type() const { return m_type; }
    QUrl url() const { return m_url; }
    bool isOverridable() const { return true; }
    QString description() const { return m_description; }
    bool isMainFrame() const { return true; }
    QList<QSslCertificate> certificateChain() const { return m_certificateChain; }
    // Every answer may come later
    void defer() { }
    void rejectCertificate() { m_answer(false); }
    void acceptCertificate() { m_answer(true); }

private:
    QUrl m_url;
    Type m_type;
    QString m_description;
    QList<QSslCertificate> m_certificateChain;
    std::function<void(bool)> m_answer;
};

class QWebEngineClientCertificateSelection {
public:
    QUrl host() const { return {}; }
    void select(const QSslCertificate&) { }
    void selectNone() { }
    QList<QSslCertificate> certificates() const { return {}; }
};

class QWebEngineNotification : public QObject {
    Q_OBJECT
public:
    QUrl origin() const { return {}; }
    QImage icon() const { return {}; }
    QString title() const { return {}; }
    QString message() const { return {}; }
    QString tag() const { return {}; }
    QString language() const { return {}; }
    Qt::LayoutDirection direction() const { return Qt::LeftToRight; }
    void show() const { }
    void click() const { }
    void close() const { }

Q_SIGNALS:
    void closed();
};
