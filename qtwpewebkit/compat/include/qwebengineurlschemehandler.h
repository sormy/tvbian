// Serves a custom scheme's requests, through QWebEngineProfile::installUrlSchemeHandler
#pragma once

#include <QObject>

class QWebEngineUrlRequestJob;

class QWebEngineUrlSchemeHandler : public QObject {
    Q_OBJECT
public:
    explicit QWebEngineUrlSchemeHandler(QObject* parent = nullptr)
        : QObject(parent)
    {
    }
    virtual void requestStarted(QWebEngineUrlRequestJob* job) = 0;
};
