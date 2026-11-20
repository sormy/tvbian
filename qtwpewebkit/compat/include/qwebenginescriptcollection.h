// A profile's user scripts, mirrored into each of its pages' WebKitUserContentManagers
#pragma once

#include "qwebenginescript.h"

#include <QList>

class QWebEnginePage;
typedef struct _WebKitUserContentManager WebKitUserContentManager;
typedef struct _WebKitUserScript WebKitUserScript;

class QWebEngineScriptCollection {
public:
    QWebEngineScriptCollection() = default;
    ~QWebEngineScriptCollection();
    QWebEngineScriptCollection(const QWebEngineScriptCollection&) = delete;
    QWebEngineScriptCollection& operator=(const QWebEngineScriptCollection&) = delete;

    bool isEmpty() const { return m_scripts.isEmpty(); }
    int count() const { return m_scripts.count(); }
    bool contains(const QWebEngineScript& script) const { return m_scripts.contains(script); }
    QList<QWebEngineScript> find(const QString& name) const;
    void insert(const QWebEngineScript& script);
    void insert(const QList<QWebEngineScript>& scripts);
    bool remove(const QWebEngineScript& script);
    void clear();
    QList<QWebEngineScript> toList() const { return m_scripts; }

private:
    friend class QWebEnginePage;
    void addManager(WebKitUserContentManager* manager);
    void removeManager(WebKitUserContentManager* manager);
    void sync();
    void removeUserScripts();

    QList<WebKitUserContentManager*> m_managers;
    QList<QWebEngineScript> m_scripts;
    QList<WebKitUserScript*> m_userScripts;
};
