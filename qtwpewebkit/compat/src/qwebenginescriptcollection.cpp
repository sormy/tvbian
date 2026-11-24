#include "qwebenginescriptcollection.h"

#include "internal.h"

#include <wpe/webkit.h>

QWebEngineScriptCollection::~QWebEngineScriptCollection()
{
    removeUserScripts();
}

QList<QWebEngineScript> QWebEngineScriptCollection::find(const QString& name) const
{
    QList<QWebEngineScript> found;
    std::copy_if(m_scripts.cbegin(), m_scripts.cend(), std::back_inserter(found),
        [&name](const QWebEngineScript& script) { return script.name() == name; });
    return found;
}

void QWebEngineScriptCollection::insert(const QWebEngineScript& script)
{
    m_scripts.append(script);
    sync();
}

void QWebEngineScriptCollection::insert(const QList<QWebEngineScript>& scripts)
{
    m_scripts.append(scripts);
    sync();
}

bool QWebEngineScriptCollection::remove(const QWebEngineScript& script)
{
    const bool removed = m_scripts.removeOne(script);
    sync();
    return removed;
}

void QWebEngineScriptCollection::clear()
{
    m_scripts.clear();
    sync();
}

WebKitUserScript* QtWpeWebKit::newUserScript(const QByteArray& source, quint32 worldId, bool allFrames, bool atDocumentStart)
{
    const QByteArray world = worldName(worldId);
    const auto frames = allFrames ? WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES : WEBKIT_USER_CONTENT_INJECT_TOP_FRAME;
    const auto time = atDocumentStart ? WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START : WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_END;
    return world.isNull() ? webkit_user_script_new(source.constData(), frames, time, nullptr, nullptr)
                          : webkit_user_script_new_for_world(source.constData(), frames, time, world.constData(), nullptr, nullptr);
}

void QWebEngineScriptCollection::addManager(WebKitUserContentManager* manager)
{
    m_managers.append(manager);
    for (WebKitUserScript* userScript : std::as_const(m_userScripts))
        webkit_user_content_manager_add_script(manager, userScript);
}

void QWebEngineScriptCollection::removeManager(WebKitUserContentManager* manager)
{
    for (WebKitUserScript* userScript : std::as_const(m_userScripts))
        webkit_user_content_manager_remove_script(manager, userScript);
    m_managers.removeOne(manager);
}

// Other scripts in the managers, like a page's web channel, stay
void QWebEngineScriptCollection::removeUserScripts()
{
    for (WebKitUserScript* userScript : std::as_const(m_userScripts)) {
        for (WebKitUserContentManager* manager : std::as_const(m_managers))
            webkit_user_content_manager_remove_script(manager, userScript);
        webkit_user_script_unref(userScript);
    }
    m_userScripts.clear();
}

void QWebEngineScriptCollection::sync()
{
    removeUserScripts();
    // WebKit runs scripts at document start or end only: Deferred runs at the end too
    for (const QWebEngineScript& script : std::as_const(m_scripts))
        m_userScripts.append(QtWpeWebKit::newUserScript(script.injectedSourceCode().toUtf8(), script.worldId(), script.runsOnSubFrames(),
            script.injectionPoint() == QWebEngineScript::DocumentCreation));
    for (WebKitUserContentManager* manager : std::as_const(m_managers)) {
        for (WebKitUserScript* userScript : std::as_const(m_userScripts))
            webkit_user_content_manager_add_script(manager, userScript);
    }
}
