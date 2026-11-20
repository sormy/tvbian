// A custom URL scheme's security flags, given to WebKit's security manager on registration
#pragma once

#include <QByteArray>
#include <QFlags>

class QWebEngineUrlScheme {
public:
    enum class Syntax { HostPortAndUserInformation, HostAndPort, Host, Path };
    enum SpecialPort { PortUnspecified = -1 };
    enum Flag {
        SecureScheme = 0x1,
        LocalScheme = 0x2,
        LocalAccessAllowed = 0x4,
        NoAccessAllowed = 0x8,
        ServiceWorkersAllowed = 0x10,
        ViewSourceAllowed = 0x20,
        ContentSecurityPolicyIgnored = 0x40,
        CorsEnabled = 0x80,
        FetchApiAllowed = 0x100,
    };
    Q_DECLARE_FLAGS(Flags, Flag)

    QWebEngineUrlScheme() = default;
    explicit QWebEngineUrlScheme(const QByteArray& name)
        : m_name(name)
    {
    }
    QByteArray name() const { return m_name; }
    void setName(const QByteArray& name) { m_name = name; }
    Syntax syntax() const { return m_syntax; }
    void setSyntax(Syntax syntax) { m_syntax = syntax; }
    int defaultPort() const { return m_defaultPort; }
    void setDefaultPort(int port) { m_defaultPort = port; }
    Flags flags() const { return m_flags; }
    void setFlags(Flags flags) { m_flags = flags; }

    static void registerScheme(const QWebEngineUrlScheme& scheme);
    static QWebEngineUrlScheme schemeByName(const QByteArray& name);

private:
    QByteArray m_name;
    Syntax m_syntax = Syntax::Path;
    int m_defaultPort = PortUnspecified;
    Flags m_flags;
};

Q_DECLARE_OPERATORS_FOR_FLAGS(QWebEngineUrlScheme::Flags)
