#include "qwebenginescript.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>

static QString fromGlob(const QString& glob)
{
    return QLatin1Char('^')
        + QRegularExpression::escape(glob).replace(QLatin1String("\\*"), QLatin1String(".*"))
        + QLatin1Char('$');
}

// A match pattern, scheme://host/path; a malformed one matches nothing
static QString fromMatchPattern(const QString& pattern)
{
    if (pattern == QLatin1String("<all_urls>"))
        return QStringLiteral("^(https?|file|ftp)://");
    static const QRegularExpression parts(QStringLiteral("^(\\*|[a-z][a-z0-9+.-]*)://(\\*|\\*\\.[^/*]+|[^/*]*)(/.*)$"));
    const QRegularExpressionMatch match = parts.match(pattern);
    if (!match.hasMatch())
        return QStringLiteral("(?!)");
    const QString scheme = match.captured(1) == QLatin1String("*") ? QStringLiteral("https?")
                                                                   : QRegularExpression::escape(match.captured(1));
    QString host = match.captured(2);
    if (host == QLatin1String("*"))
        host = QStringLiteral("[^/]*");
    else if (host.startsWith(QLatin1String("*.")))
        host = QStringLiteral("([^/]*\\.)?") + QRegularExpression::escape(host.mid(2));
    else
        host = QRegularExpression::escape(host);
    return QLatin1Char('^') + scheme + QLatin1String("://") + host + fromGlob(match.captured(3)).mid(1);
}

using HeaderEntries = QList<std::pair<QString, QString>>;

// The keys and values of a Greasemonkey header, // @key value
static HeaderEntries headerEntries(const QString& code)
{
    const qsizetype start = code.indexOf(QLatin1String("// ==UserScript=="));
    const qsizetype end = code.indexOf(QLatin1String("// ==/UserScript=="), start);
    if (start < 0 || end < 0)
        return {};
    static const QRegularExpression line(QStringLiteral("^//\\s*@(\\S+)(?:\\s+(.*\\S))?\\s*$"), QRegularExpression::MultilineOption);
    HeaderEntries entries;
    for (const QRegularExpressionMatch& entry : line.globalMatch(code.mid(start, end - start)))
        entries.append({ entry.captured(1), entry.captured(2) });
    return entries;
}

void QWebEngineScript::setSourceCode(const QString& code)
{
    m_sourceCode = code;
    for (const auto& [key, value] : headerEntries(code)) {
        if (key == QLatin1String("name"))
            m_name = value;
        else if (key == QLatin1String("run-at"))
            m_injectionPoint = value == QLatin1String("document-start") ? DocumentCreation
                : value == QLatin1String("document-idle")               ? Deferred
                                                                        : DocumentReady;
    }
}

static QByteArray patternsLiteral(const QStringList& patterns)
{
    return QJsonDocument(QJsonArray::fromStringList(patterns)).toJson(QJsonDocument::Compact);
}

// Read here, not kept in the script: an application built against the script's size must still fit it.
// WebKit's own URL lists need scheme://host, which an application's scheme like falkon:speeddial lacks.
QString QWebEngineScript::injectedSourceCode() const
{
    QStringList included;
    QStringList excluded;
    for (const auto& [key, value] : headerEntries(m_sourceCode)) {
        if (key == QLatin1String("include"))
            included.append(fromGlob(value));
        else if (key == QLatin1String("match"))
            included.append(fromMatchPattern(value));
        else if (key == QLatin1String("exclude"))
            excluded.append(fromGlob(value));
    }
    if (included.isEmpty() && excluded.isEmpty())
        return m_sourceCode;
    const QString includes = included.isEmpty()
        ? QStringLiteral("true")
        : QString::fromUtf8(patternsLiteral(included)) + QStringLiteral(".some(matches)");
    return QStringLiteral("(function () {\n"
                          "const matches = (pattern) => new RegExp(pattern).test(location.href);\n"
                          "if (!%1 || %2.some(matches))\n"
                          "    return;\n"
                          "%3\n"
                          "})();\n")
        .arg(includes, QString::fromUtf8(patternsLiteral(excluded)), m_sourceCode);
}
