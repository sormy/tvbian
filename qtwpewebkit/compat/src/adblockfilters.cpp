#include "adblockfilters.h"

#include <QHash>
#include <QRegularExpression>
#include <QSet>
#include <optional>

namespace QtWpeWebKit {

namespace {

// Adblock Plus types WebKit tells apart; "document" and "popup" only when a filter names them
const QHash<QString, QString> webKitTypes {
    { QStringLiteral("script"), QStringLiteral("script") },
    { QStringLiteral("image"), QStringLiteral("image") },
    { QStringLiteral("stylesheet"), QStringLiteral("style-sheet") },
    { QStringLiteral("css"), QStringLiteral("style-sheet") },
    { QStringLiteral("font"), QStringLiteral("font") },
    { QStringLiteral("media"), QStringLiteral("media") },
    { QStringLiteral("object"), QStringLiteral("other") },
    { QStringLiteral("other"), QStringLiteral("other") },
    { QStringLiteral("subdocument"), QStringLiteral("child-document") },
    { QStringLiteral("frame"), QStringLiteral("child-document") },
    { QStringLiteral("xmlhttprequest"), QStringLiteral("fetch") },
    { QStringLiteral("xhr"), QStringLiteral("fetch") },
    { QStringLiteral("websocket"), QStringLiteral("websocket") },
    { QStringLiteral("ping"), QStringLiteral("ping") },
    { QStringLiteral("popup"), QStringLiteral("popup") },
};
const QStringList defaultTypes { QStringLiteral("script"), QStringLiteral("image"), QStringLiteral("style-sheet"),
    QStringLiteral("font"), QStringLiteral("media"), QStringLiteral("other"), QStringLiteral("child-document"),
    QStringLiteral("fetch"), QStringLiteral("websocket"), QStringLiteral("ping"), QStringLiteral("svg-document") };
const QString anyUrl = QStringLiteral(".*");
// Adblock Plus's separator: anything but a letter, digit, or one of _-.%
const QString separator = QStringLiteral("[^a-zA-Z0-9_.%-]");
const QString anySchemeAndSubdomain = QStringLiteral("^[a-z][a-z0-9+.-]*://([^/]*\\.)?");
const QString regexSpecials = QStringLiteral("\\.+?()[]{}$|");

// What an exception lifts
enum class Scope { Requests, Page, ElementHiding, GenericElementHiding };

struct Domains {
    QStringList included;
    QStringList excluded;
    // Some named domain WebKit cannot match, such as an entity like "example.*"
    bool incomplete = false;
};

Domains domainsOf(const QString& list, QChar delimiter)
{
    Domains domains;
    for (QString domain : list.split(delimiter, Qt::SkipEmptyParts)) {
        const bool excluded = domain.startsWith(QLatin1Char('~'));
        domain = domain.mid(excluded ? 1 : 0).toLower();
        const bool expressible = !domain.contains(QLatin1Char('*'))
            && std::all_of(domain.cbegin(), domain.cend(), [](QChar c) { return c.unicode() < 128; });
        if (!expressible)
            domains.incomplete |= !excluded;
        else
            (excluded ? domains.excluded : domains.included).append(QLatin1Char('*') + domain);
    }
    return domains;
}

// Adblock Plus patterns as the regular expressions WebKit accepts: no disjunction, no counted repetition
std::optional<QString> urlFilterOf(QString pattern)
{
    const bool isRegularExpression = pattern.size() > 1 && pattern.startsWith(QLatin1Char('/')) && pattern.endsWith(QLatin1Char('/'));
    if (isRegularExpression)
        return std::nullopt;
    QString filter;
    if (pattern.startsWith(QLatin1String("||"))) {
        filter = anySchemeAndSubdomain;
        pattern.remove(0, 2);
    } else if (pattern.startsWith(QLatin1Char('|'))) {
        filter = QStringLiteral("^");
        pattern.remove(0, 1);
    }
    const bool anchoredAtEnd = pattern.endsWith(QLatin1Char('|'));
    if (anchoredAtEnd)
        pattern.chop(1);
    for (QChar c : std::as_const(pattern)) {
        if (c.unicode() >= 128)
            return std::nullopt;
        if (c == QLatin1Char('*'))
            filter += anyUrl;
        else if (c == QLatin1Char('^'))
            filter += separator;
        else
            filter += regexSpecials.contains(c) ? QString(QLatin1Char('\\')) + c : QString(c);
    }
    if (anchoredAtEnd)
        filter += QLatin1Char('$');
    return filter.isEmpty() ? anyUrl : filter;
}

struct Trigger {
    QString urlFilter = anyUrl;
    QStringList resourceTypes;
    QString loadType;
    bool caseSensitive = false;
    QStringList ifDomain;
    QStringList unlessDomain;
};

struct Rule {
    Trigger trigger;
    QString action;
    QString selector;
};

void restrictTo(Trigger& trigger, const Domains& domains)
{
    if (!domains.included.isEmpty())
        trigger.ifDomain = domains.included;
    else if (!domains.excluded.isEmpty())
        trigger.unlessDomain = domains.excluded;
}

// Written straight into one string: Qt's JSON objects cost an allocation per value, megabytes over EasyList
void appendString(QString& json, QStringView text)
{
    json += QLatin1Char('"');
    for (const QChar c : text) {
        if (c == QLatin1Char('"') || c == QLatin1Char('\\'))
            json += QLatin1Char('\\');
        if (c.unicode() < 0x20)
            json += QStringLiteral("\\u%1").arg(c.unicode(), 4, 16, QLatin1Char('0'));
        else
            json += c;
    }
    json += QLatin1Char('"');
}

void appendStrings(QString& json, const QStringList& texts)
{
    json += QLatin1Char('[');
    for (const QString& text : texts) {
        if (json.back() != QLatin1Char('['))
            json += QLatin1Char(',');
        appendString(json, text);
    }
    json += QLatin1Char(']');
}

void appendRule(QString& json, const Rule& rule)
{
    const Trigger& trigger = rule.trigger;
    json += QLatin1String("{\"trigger\":{\"url-filter\":");
    appendString(json, trigger.urlFilter);
    if (!trigger.resourceTypes.isEmpty()) {
        json += QLatin1String(",\"resource-type\":");
        appendStrings(json, trigger.resourceTypes);
    }
    if (!trigger.loadType.isEmpty()) {
        json += QLatin1String(",\"load-type\":");
        appendStrings(json, { trigger.loadType });
    }
    if (trigger.caseSensitive)
        json += QLatin1String(",\"url-filter-is-case-sensitive\":true");
    if (!trigger.ifDomain.isEmpty()) {
        json += QLatin1String(",\"if-domain\":");
        appendStrings(json, trigger.ifDomain);
    }
    if (!trigger.unlessDomain.isEmpty()) {
        json += QLatin1String(",\"unless-domain\":");
        appendStrings(json, trigger.unlessDomain);
    }
    json += QLatin1String("},\"action\":{\"type\":");
    appendString(json, rule.action);
    if (!rule.selector.isEmpty()) {
        json += QLatin1String(",\"selector\":");
        appendString(json, rule.selector);
    }
    json += QLatin1String("}}");
}

// WebKit applies rules in order, an exception ignoring the rules before it that match the same load
class RuleList {
public:
    void addFilter(const QString& filter)
    {
        static const QRegularExpression elementHiding(QStringLiteral(R"(^([^/*|@"!]*?)#(@)?([?$%])?#(.+)$)"));
        if (filter.isEmpty() || filter.startsWith(QLatin1Char('!')) || filter.startsWith(QLatin1Char('[')))
            return;
        const QRegularExpressionMatch match = elementHiding.match(filter);
        if (match.hasMatch())
            addElementHiding(match.captured(1), !match.captured(2).isEmpty(), !match.captured(3).isEmpty(), match.captured(4));
        else
            addRequestFilter(filter);
    }

    QByteArray toJson() const
    {
        QString json;
        json += QLatin1Char('[');
        const auto append = [&json](const Rule& rule) {
            if (json.size() > 1)
                json += QLatin1Char(',');
            appendRule(json, rule);
        };
        for (auto selector = m_genericHiding.cbegin(); selector != m_genericHiding.cend(); ++selector) {
            if (m_selectorsShownEverywhere.contains(selector.key()))
                continue;
            Domains domains = selector.value();
            for (const QString& domain : m_selectorExceptions.value(selector.key()))
                domains.excluded.append(domain);
            Trigger trigger;
            restrictTo(trigger, domains);
            append({ trigger, QStringLiteral("css-display-none"), selector.key() });
        }
        for (const QList<Rule>* section : { &m_genericHidingExceptions, &m_domainHiding, &m_hidingExceptions, &m_blocking, &m_exceptions })
            for (const Rule& rule : *section)
                append(rule);
        json += QLatin1Char(']');
        return json.toUtf8();
    }

private:
    void addElementHiding(const QString& domainList, bool exception, bool extended, const QString& selector)
    {
        // Extended selectors and scriptlets are an extension's, not CSS
        if (extended || selector.startsWith(QLatin1Char('+')) || selector.startsWith(QLatin1Char('^')))
            return;
        const Domains domains = domainsOf(domainList, QLatin1Char(','));
        if (domains.incomplete)
            return;
        if (exception) {
            if (domains.included.isEmpty())
                m_selectorsShownEverywhere.insert(selector);
            m_selectorExceptions[selector] += domains.included;
        } else if (domains.included.isEmpty()) {
            m_genericHiding.insert(selector, domains);
        } else {
            Trigger trigger;
            restrictTo(trigger, domains);
            m_domainHiding.append({ trigger, QStringLiteral("css-display-none"), selector });
        }
    }

    void addRequestFilter(QString filter)
    {
        const bool exception = filter.startsWith(QLatin1String("@@"));
        if (exception)
            filter.remove(0, 2);
        const qsizetype optionsStart = filter.lastIndexOf(QLatin1Char('$'));
        const QStringList options = optionsStart < 0 ? QStringList() : filter.mid(optionsStart + 1).split(QLatin1Char(','));
        const QString pattern = optionsStart < 0 ? filter : filter.left(optionsStart);

        QStringList includedTypes, excludedTypes;
        Trigger trigger;
        Domains domains;
        Scope scope = Scope::Requests;
        for (const QString& option : options) {
            const bool negated = option.startsWith(QLatin1Char('~'));
            const QString name = option.mid(negated ? 1 : 0).section(QLatin1Char('='), 0, 0).toLower();
            if (webKitTypes.contains(name))
                (negated ? excludedTypes : includedTypes).append(webKitTypes.value(name));
            else if (name == QLatin1String("domain"))
                domains = domainsOf(option.section(QLatin1Char('='), 1), QLatin1Char('|'));
            else if (name == QLatin1String("third-party") || name == QLatin1String("3p"))
                trigger.loadType = negated ? QStringLiteral("first-party") : QStringLiteral("third-party");
            else if (name == QLatin1String("first-party") || name == QLatin1String("1p"))
                trigger.loadType = negated ? QStringLiteral("third-party") : QStringLiteral("first-party");
            else if (name == QLatin1String("match-case"))
                trigger.caseSensitive = true;
            else if (name == QLatin1String("document") || name == QLatin1String("doc"))
                exception ? void(scope = Scope::Page) : includedTypes.append(QStringLiteral("top-document"));
            else if (exception && (name == QLatin1String("elemhide") || name == QLatin1String("ehide")))
                scope = Scope::ElementHiding;
            else if (exception && (name == QLatin1String("generichide") || name == QLatin1String("ghide")))
                scope = Scope::GenericElementHiding;
            else if (name != QLatin1String("important"))
                return; // Redirects, rewrites, header and CSP changes are beyond a content blocker
        }
        if (domains.incomplete)
            return;

        if (scope != Scope::Requests) {
            addPageException(pattern, domains, scope);
            return;
        }
        const std::optional<QString> urlFilter = urlFilterOf(pattern);
        // A filter that would block every request of a kind on every site is a mistake, not a policy
        if (!urlFilter || (*urlFilter == anyUrl && domains.included.isEmpty() && !exception))
            return;
        QStringList types = includedTypes;
        if (types.isEmpty())
            for (const QString& type : defaultTypes)
                if (!excludedTypes.contains(type))
                    types.append(type);
        trigger.urlFilter = *urlFilter;
        trigger.resourceTypes = types;
        restrictTo(trigger, domains);
        (exception ? m_exceptions : m_blocking).append({ trigger, exception ? QStringLiteral("ignore-previous-rules") : QStringLiteral("block") });
    }

    // Lifts filters on the pages of some sites, named by domain=, or by a pattern that is only a domain
    void addPageException(const QString& pattern, Domains domains, Scope scope)
    {
        static const QRegularExpression onlyDomain(QStringLiteral(R"(^\|\|([a-z0-9.-]+)\^?$)"));
        if (!pattern.isEmpty()) {
            const QRegularExpressionMatch match = onlyDomain.match(pattern.toLower());
            if (!match.hasMatch())
                return;
            domains.included = { QLatin1Char('*') + match.captured(1) };
        }
        if (domains.included.isEmpty())
            return;
        Trigger trigger;
        trigger.ifDomain = domains.included;
        QList<Rule>& section = scope == Scope::Page ? m_exceptions
            : scope == Scope::ElementHiding        ? m_hidingExceptions
                                                   : m_genericHidingExceptions;
        section.append({ trigger, QStringLiteral("ignore-previous-rules") });
    }

    // By selector, so one rule hides it everywhere hiding is not lifted
    QHash<QString, Domains> m_genericHiding;
    QHash<QString, QStringList> m_selectorExceptions;
    QSet<QString> m_selectorsShownEverywhere;
    QList<Rule> m_genericHidingExceptions;
    QList<Rule> m_domainHiding;
    QList<Rule> m_hidingExceptions;
    QList<Rule> m_blocking;
    QList<Rule> m_exceptions;
};

} // namespace

QByteArray contentBlockerRules(const QString& filterLists)
{
    RuleList rules;
    for (const QStringView line : QStringView(filterLists).split(QLatin1Char('\n')))
        rules.addFilter(line.trimmed().toString());
    return rules.toJson();
}

} // namespace QtWpeWebKit
