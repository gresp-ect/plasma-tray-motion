// SPDX-License-Identifier: GPL-2.0-or-later
#include "ptmdroprouter.h"
#include <QGuiApplication>
#include <QDrag>
#include <QQuickItemGrabResult>
#include <QQmlEngine>
#include <QQmlContext>
#include <QQuickView>
#include <QQuickItem>
#include <QMimeData>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QSignalSpy>
#include <QDebug>
#include <cstdio>
#include <QRasterWindow>
#include <QPainter>
#include <QTest>

class ProbeImageWindow : public QRasterWindow
{
public:
    ProbeImageWindow() {
        QSurfaceFormat format; format.setAlphaBufferSize(8); setFormat(format);
        resize(32,32);
    }
    QImage pixels() const { return static_cast<QImage *>(redirected(nullptr))->copy(); }
protected:
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this);
        painter.setCompositionMode(QPainter::CompositionMode_Source);
        painter.fillRect(QRect(QPoint(), size()), Qt::red);
    }
};

struct PtmDropRouterImageCheck
{
    static void run(PtmDropRouter &router) {
        ProbeImageWindow image;
        image.show();
        QTest::qWait(30);
        router.m_nativeExecuting = true;
        router.m_imageWindow = &image;
        image.installEventFilter(&router);
        for (int i = 0; i < 4; ++i) {
            router.updateNativeImage(true);
            if (image.pixels().pixelColor(5,5).alpha() != 0) qFatal("Native drag image did not become transparent inside the tray");
            image.update(); QTest::qWait(30);
            if (image.pixels().pixelColor(5,5).alpha() != 0) qFatal("Deferred painting incorrectly restored the native image inside the tray");
            router.updateNativeImage(false);
            QTest::qWait(30);
            if (image.pixels().pixelColor(5,5) != QColor(Qt::red)) qFatal("Native drag image pixels were not restored outside the tray");
            if (!image.isVisible() || !image.handle()) qFatal("Drag surface was hidden or destroyed");
        }
        router.updateNativeImage(true);
        router.end(router.m_token);
        QTest::qWait(30);
        if (image.pixels().pixelColor(5,5) != QColor(Qt::red)) qFatal("Transparent drag image buffer was not returned to Qt for repaint after cancellation");
        if (!image.isVisible() || !image.handle()) qFatal("Drag surface was hidden or destroyed during cancellation");
        router.m_nativeExecuting = false;
    }
};

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    qInstallMessageHandler([](QtMsgType, const QMessageLogContext &, const QString &message) { std::fprintf(stderr, "%s\n", message.toLocal8Bit().constData()); });
    QQuickView view;
    view.setSource(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    if (view.status() != QQuickView::Ready) return 1;
    view.show();
    app.processEvents();
    auto *root = view.rootObject();
    auto *grid = root->findChild<QQuickItem *>(QStringLiteral("grid"));
    if (!grid) return 2;
    const QString token = QStringLiteral("own-gesture");
    QMimeData mime;
    mime.setData(QStringLiteral("application/x-plasma-tray-motion"), token.toUtf8());
    auto enter = [&](QPoint point, QMimeData *data) {
        QDragEnterEvent event(point, Qt::MoveAction, data, Qt::LeftButton, Qt::NoModifier);
        app.sendEvent(&view, &event);
        return event.isAccepted();
    };
    auto drop = [&](QPointF point, QMimeData *data) {
        QDropEvent event(point, Qt::MoveAction, data, Qt::LeftButton, Qt::NoModifier);
        app.sendEvent(&view, &event);
        return event.isAccepted();
    };
    auto require = [](bool condition, const char *message) {
        if (!condition) qFatal("%s", message);
    };
    // Reproduce the actual failure: another panel component accepts MoveAction,
    // while the tray never receives the drop event.
    require(enter(QPoint(100,20), &mime), "Blocking receiver did not accept the enter event");
    require(drop(QPointF(100,20), &mime), "Blocking receiver did not accept the drop event");
    require(root->property("stolenDrops").toInt() == 1, "Negative control did not intercept the drop event");
    root->setProperty("stolenDrops", 0);
    PtmDropRouter router;
    QSignalSpy moved(&router, &PtmDropRouter::moved);
    QSignalSpy left(&router, &PtmDropRouter::left);
    QSignalSpy dropped(&router, &PtmDropRouter::dropped);
    require(router.begin(grid, token), "Router failed to start");
    require(enter(QPoint(5,5), &mime), "Panel enter event outside the tray was not accepted");
    require(left.size() == 1, "Entering an external region must clear the preview");
    QDragLeaveEvent leaveEvent;
    app.sendEvent(&view, &leaveEvent);
    require(enter(QPoint(50,20), &mime), "Failed to reenter the source panel");
    QDragMoveEvent moveEvent(QPoint(140,20), Qt::MoveAction, &mime, Qt::LeftButton, Qt::NoModifier);
    app.sendEvent(&view, &moveEvent);
    require(moveEvent.isAccepted(), "Move after reentry was rejected");
    require(moved.last().at(1).toPointF() == QPointF(100,10), "Incorrect scene-to-tray coordinate mapping");
    require(drop(QPointF(140,20), &mime), "Drop after reentry was rejected");
    require(dropped.size() == 1, "Tray did not receive the drop after reentry");
    require(root->property("stolenDrops").toInt() == 0, "Blocking receiver intercepted the tray drop");
    router.end(QStringLiteral("another-token"));
    require(enter(QPoint(5,5), &mime), "Unrelated token stopped the current router");
    require(!drop(QPointF(5,5), &mime), "External drop was incorrectly accepted");
    require(dropped.size() == 1, "External drop was incorrectly committed");
    QMimeData foreign;
    foreign.setData(QStringLiteral("application/x-plasma-tray-motion"), QByteArrayLiteral("foreign-gesture"));
    require(enter(QPoint(100,20), &foreign), "Unrelated enter event must reach the normal scene receiver");
    require(drop(QPointF(100,20), &foreign), "Unrelated drop event must reach the normal scene receiver");
    require(dropped.size() == 1, "Unrelated gesture was incorrectly routed to the tray");
    require(root->property("stolenDrops").toInt() == 1, "Unrelated gesture was incorrectly intercepted");
    router.end(token);
    enter(QPoint(100,20), &mime);
    drop(QPointF(100,20), &mime);
    require(root->property("stolenDrops").toInt() == 2, "Router remained active after ending");
    // Check that completed scene pixels actually become the QDrag image,
    // and retain the specified offset, beyond checking the screenshot URL.
    router.begin(grid, token);
    QObject notAnImage;
    require(router.runNativeDrag(&notAnImage, token) == int(Qt::IgnoreAction), "Invalid images must be rejected");
    const auto grab = grid->grabToImage();
    require(bool(grab), "Cannot request screenshot");
    QSignalSpy ready(grab.data(), &QQuickItemGrabResult::ready);
    if (grab->image().isNull()) require(ready.wait(2000), "Screenshot did not complete");
    require(!grab->image().isNull(), "Screenshot is empty");
    require(grab->image().pixelColor(5,5).red() > 200 && grab->image().pixelColor(5,5).alpha() > 200, "Source screenshot lacks visible red pixels");
    QList<QImage> nativeImages;
    QList<QPoint> nativeHotspots;
    QObject::connect(&router, &PtmDropRouter::nativeDragPrepared, &view, [&](QObject *object) {
        const auto *drag = qobject_cast<QDrag *>(object);
        require(drag && !drag->pixmap().isNull(), "Native drag image is missing");
        nativeImages.append(drag->pixmap().toImage());
        nativeHotspots.append(drag->hotSpot());
        require(!router.begin(grid, QStringLiteral("nested-gesture")), "Gesture watcher was incorrectly replaced during native drag");
        require(router.runNativeDrag(grab.data(), token) == int(Qt::IgnoreAction), "Nested start was allowed during native drag");
    });
    router.runNativeDrag(grab.data(), token);
    require(nativeImages.size() == 1, "Native drag image was not prepared");
    require(nativeImages.last().pixelColor(5,5).red() > 200, "Native drag image lost screenshot pixels");
    require(nativeHotspots.last() == QPoint(-24,-24), "Native drag image offset changed");
    view.engine()->rootContext()->setContextProperty(QStringLiteral("pixelBridge"), &router);
    QSignalSpy qmlFinished(root, SIGNAL(captureFinishedChanged()));
    QMetaObject::invokeMethod(root, "captureFromQml");
    if (!root->property("captureFinished").toBool()) require(qmlFinished.wait(2000), "QML image callback did not complete");
    require(nativeImages.size() == 2, "QML grab result was not converted to a native image object");
    require(nativeImages.last().pixelColor(5,5).red() > 200, "QML callback lost screenshot pixels");
    PtmDropRouterImageCheck::run(router);
    router.end(token);
    qInfo() << "Passed: blocking receiver reproduction, priority leave/reenter routing, external drops, unrelated drags, and cleanup.";
    return 0;
}
