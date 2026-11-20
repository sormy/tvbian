// What a page asks the user: permissions, trust in a certificate, credentials
#include "qwebenginepage.h"

#include <QAuthenticator>
#include <QPointer>
#include <optional>
#include <wpe/webkit.h>

static std::optional<QWebEnginePage::Feature> featureOf(WebKitPermissionRequest* request)
{
    if (WEBKIT_IS_GEOLOCATION_PERMISSION_REQUEST(request))
        return QWebEnginePage::Geolocation;
    if (WEBKIT_IS_NOTIFICATION_PERMISSION_REQUEST(request))
        return QWebEnginePage::Notifications;
    if (WEBKIT_IS_POINTER_LOCK_PERMISSION_REQUEST(request))
        return QWebEnginePage::MouseLock;
    if (!WEBKIT_IS_USER_MEDIA_PERMISSION_REQUEST(request))
        return std::nullopt;
    auto* media = WEBKIT_USER_MEDIA_PERMISSION_REQUEST(request);
    const bool audio = webkit_user_media_permission_is_for_audio_device(media);
    if (webkit_user_media_permission_is_for_display_device(media))
        return audio ? QWebEnginePage::DesktopAudioVideoCapture : QWebEnginePage::DesktopVideoCapture;
    if (!webkit_user_media_permission_is_for_video_device(media))
        return QWebEnginePage::MediaAudioCapture;
    return audio ? QWebEnginePage::MediaAudioVideoCapture : QWebEnginePage::MediaVideoCapture;
}

static QUrl originOf(const QUrl& url)
{
    return url.adjusted(QUrl::RemovePath | QUrl::RemoveQuery | QUrl::RemoveFragment | QUrl::RemoveUserInfo);
}

struct TlsError {
    GTlsCertificateFlags flag;
    QWebEngineCertificateError::Type type;
    const char* description;
};

// The first matching flag names the error
static const TlsError tlsErrors[] = {
    { G_TLS_CERTIFICATE_UNKNOWN_CA, QWebEngineCertificateError::CertificateAuthorityInvalid,
        "The certificate is not signed by a trusted authority." },
    { G_TLS_CERTIFICATE_BAD_IDENTITY, QWebEngineCertificateError::CertificateCommonNameInvalid,
        "The certificate is for another site." },
    { G_TLS_CERTIFICATE_EXPIRED, QWebEngineCertificateError::CertificateDateInvalid, "The certificate has expired." },
    { G_TLS_CERTIFICATE_NOT_ACTIVATED, QWebEngineCertificateError::CertificateDateInvalid,
        "The certificate is not valid yet." },
    { G_TLS_CERTIFICATE_REVOKED, QWebEngineCertificateError::CertificateRevoked, "The certificate has been revoked." },
    { G_TLS_CERTIFICATE_INSECURE, QWebEngineCertificateError::CertificateWeakSignatureAlgorithm,
        "The certificate uses an insecure algorithm." },
};

static TlsError tlsErrorOf(GTlsCertificateFlags flags)
{
    for (const TlsError& error : tlsErrors) {
        if (flags & error.flag)
            return error;
    }
    return { flags, QWebEngineCertificateError::CertificateInvalid, "The certificate is not valid." };
}

static QList<QSslCertificate> chainOf(GTlsCertificate* certificate)
{
    QList<QSslCertificate> chain;
    for (; certificate; certificate = g_tls_certificate_get_issuer(certificate)) {
        g_autofree char* pem = nullptr;
        g_object_get(certificate, "certificate-pem", &pem, nullptr);
        chain.append(QSslCertificate(QByteArray(pem)));
    }
    return chain;
}

struct QWebEnginePage::RequestSignals {
    static gboolean permissionRequest(WebKitWebView*, WebKitPermissionRequest* request, QWebEnginePage* page)
    {
        const auto feature = featureOf(request);
        if (!feature)
            return FALSE;
        // Qt may answer right away, from the signal
        page->m_permissionRequests.insert(*feature, WEBKIT_PERMISSION_REQUEST(g_object_ref(request)));
        Q_EMIT page->featurePermissionRequested(originOf(page->url()), *feature);
        return TRUE;
    }

    static gboolean loadFailedWithTlsErrors(WebKitWebView* webView, char* uri, GTlsCertificate* certificate,
        GTlsCertificateFlags flags, QWebEnginePage* page)
    {
        page->m_loadFailed = true;
        const QUrl url = QUrl::fromEncoded(uri);
        const TlsError error = tlsErrorOf(flags);
        std::shared_ptr<GTlsCertificate> trusted(G_TLS_CERTIFICATE(g_object_ref(certificate)), g_object_unref);
        Q_EMIT page->certificateError(QWebEngineCertificateError(url, error.type, QString::fromUtf8(error.description),
            chainOf(certificate), [page = QPointer(page), webView, url, trusted](bool accepted) {
                if (!page || !accepted)
                    return;
                webkit_network_session_allow_tls_certificate_for_host(webkit_web_view_get_network_session(webView),
                    trusted.get(), url.host().toUtf8().constData());
                page->load(url);
            }));
        return TRUE;
    }

    // QAuthenticator's realm is set by Qt's own network code only, so Qt is not told the realm
    static gboolean authenticate(WebKitWebView*, WebKitAuthenticationRequest* request, QWebEnginePage* page)
    {
        auto* origin = webkit_authentication_request_get_security_origin(request);
        QUrl url;
        url.setScheme(QString::fromUtf8(webkit_security_origin_get_protocol(origin)));
        url.setHost(QString::fromUtf8(webkit_security_origin_get_host(origin)));
        if (const guint16 port = webkit_security_origin_get_port(origin))
            url.setPort(port);
        webkit_security_origin_unref(origin);

        QAuthenticator authenticator;
        if (webkit_authentication_request_is_for_proxy(request))
            Q_EMIT page->proxyAuthenticationRequired(url, &authenticator, url.host());
        else
            Q_EMIT page->authenticationRequired(url, &authenticator);
        if (authenticator.isNull()) {
            webkit_authentication_request_authenticate(request, nullptr);
            return TRUE;
        }
        auto* credential = webkit_credential_new(authenticator.user().toUtf8().constData(),
            authenticator.password().toUtf8().constData(), WEBKIT_CREDENTIAL_PERSISTENCE_FOR_SESSION);
        webkit_authentication_request_authenticate(request, credential);
        webkit_credential_free(credential);
        return TRUE;
    }

    static void connect(QWebEnginePage* page)
    {
        WebKitWebView* view = page->m_webView;
        g_signal_connect(view, "permission-request", G_CALLBACK(permissionRequest), page);
        g_signal_connect(view, "load-failed-with-tls-errors", G_CALLBACK(loadFailedWithTlsErrors), page);
        g_signal_connect(view, "authenticate", G_CALLBACK(authenticate), page);
    }
};

void QWebEnginePage::setFeaturePermission(const QUrl&, Feature feature, PermissionPolicy policy)
{
    if (policy == PermissionUnknown)
        return;
    for (WebKitPermissionRequest* request : m_permissionRequests.values(feature)) {
        policy == PermissionGrantedByUser ? webkit_permission_request_allow(request) : webkit_permission_request_deny(request);
        g_object_unref(request);
    }
    m_permissionRequests.remove(feature);
}

void QWebEnginePage::connectRequestSignals()
{
    RequestSignals::connect(this);
}

void QWebEnginePage::denyPermissionRequests()
{
    for (WebKitPermissionRequest* request : std::as_const(m_permissionRequests)) {
        webkit_permission_request_deny(request);
        g_object_unref(request);
    }
    m_permissionRequests.clear();
}
