// A user script as QtWebEngine describes it; QWebEngineScriptCollection hands it to WebKit
#pragma once

#include <QString>
#include <QUrl>

class QWebEngineScript {
public:
    enum InjectionPoint { Deferred, DocumentReady, DocumentCreation };
    enum ScriptWorldId { MainWorld = 0, ApplicationWorld, UserWorld };

    bool isNull() const { return m_sourceCode.isEmpty(); }
    QString name() const { return m_name; }
    void setName(const QString& name) { m_name = name; }
    QUrl sourceUrl() const { return m_sourceUrl; }
    void setSourceUrl(const QUrl& url) { m_sourceUrl = url; }
    QString sourceCode() const { return m_sourceCode; }
    void setSourceCode(const QString& code) { m_sourceCode = code; }
    InjectionPoint injectionPoint() const { return m_injectionPoint; }
    void setInjectionPoint(InjectionPoint point) { m_injectionPoint = point; }
    quint32 worldId() const { return m_worldId; }
    void setWorldId(quint32 id) { m_worldId = id; }
    bool runsOnSubFrames() const { return m_runsOnSubFrames; }
    void setRunsOnSubFrames(bool on) { m_runsOnSubFrames = on; }
    bool operator==(const QWebEngineScript& other) const
    {
        return m_name == other.m_name && m_sourceUrl == other.m_sourceUrl && m_sourceCode == other.m_sourceCode
            && m_injectionPoint == other.m_injectionPoint && m_worldId == other.m_worldId
            && m_runsOnSubFrames == other.m_runsOnSubFrames;
    }

private:
    QString m_name;
    QUrl m_sourceUrl;
    QString m_sourceCode;
    InjectionPoint m_injectionPoint = DocumentReady;
    quint32 m_worldId = MainWorld;
    bool m_runsOnSubFrames = false;
};
