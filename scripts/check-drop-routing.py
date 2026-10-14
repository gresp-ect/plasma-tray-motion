#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Send Qt native MIME events through the tray view hierarchy offscreen."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
from pathlib import Path
import tempfile
from PySide6.QtCore import QUrl,QPoint,QPointF,Qt,QMimeData,QObject,QMetaObject
from PySide6.QtGui import QGuiApplication,QDragEnterEvent,QDragMoveEvent,QDropEvent,QDragLeaveEvent
from PySide6.QtQuick import QQuickView
app=QGuiApplication([])
with tempfile.TemporaryDirectory() as tmp:
 d=Path(tmp); src=Path(__file__).resolve().parents[1]/'work/source/applets/systemtray/qml'
 c=(src/'PtmController.qml').read_text().replace('import org.kde.plasma.plasmoid\n','').replace('Plasmoid.configuration','testConfig').replace('Plasmoid.ptmCommitOrder(order)','motion.testCommits.push(order)').replace('    id: motion','''    id: motion
    objectName: "motion"
    property QtObject testBridge: QtObject {
        signal ptmNativeDragMoved(string token, point position)
        signal ptmNativeDragLeft(string token)
        signal ptmNativeDragDropped(string token, point position)
        signal nativeStarted()
        function ptmRunNativeDrag(imageResult, token) { nativeStarted(); return Qt.IgnoreAction; }
        function ptmWatchNativeDrop(grid, token) { return true; }
        function ptmUnwatchNativeDrop(token) {}
    }
    property var testCommits: []
    property QtObject testConfig: QtObject {
        property bool ptmEnabled: true
        property int ptmHoldMs: 180
        property int ptmAnimationMs: 0
        property bool reverseIconOrder: false
        property bool scaleIconsToFit: false
        property int iconSpacing: 2
    }''',1)
 c=c.replace('Plasmoid.ptmWatchNativeDrop','motion.testBridge.ptmWatchNativeDrop').replace('Plasmoid.ptmUnwatchNativeDrop','motion.testBridge.ptmUnwatchNativeDrop').replace('Plasmoid.ptmRunNativeDrag','motion.testBridge.ptmRunNativeDrag').replace('target: Plasmoid','target: motion.testBridge')
 (d/'PtmController.qml').write_text(c);(d/'ItemLoader.qml').write_bytes((src/'ItemLoader.qml').read_bytes())
 (d/'main.qml').write_text('''import QtQuick
import QtQuick.Layouts
import org.kde.draganddrop as DnD
Item {
 width: 160; height: 40
 function prepare() {
  motion.nativeRunning = true; motion.dragIndex=0;motion.destination=0;
  motion.slots=[Qt.point(0,0),Qt.point(40,0),Qt.point(80,0)];
  motion.ids=["a","b","c"];motion.token="probe";
 }
 MouseArea {
  anchors.fill: parent
  DnD.DropArea { anchors.fill: parent; preventStealing: true; onDragEnter: event => { event.ignore(); } }
  GridLayout {
   anchors.fill: parent
   GridView {
    id: grid
    Layout.preferredWidth: 120; Layout.preferredHeight: 40
    cellWidth:40; cellHeight:40; model: 3; delegate: Item { width:40;height:40 }
    PtmController { id: motion; parent: grid; grid:grid; model: grid.model; iconSize:24 }
   }
  }
 }
}''')
 view=QQuickView();view.setSource(QUrl.fromLocalFile(str(d/'main.qml')));assert view.status()==QQuickView.Ready,view.errors();view.show();app.processEvents()
 root=view.rootObject(); obj=root.findChild(QObject,'motion');QMetaObject.invokeMethod(root,'prepare')
 print('Drag area geometry',obj.property('width'),obj.property('height'),obj.property('x'),obj.property('y'))
 mime=QMimeData();mime.setData('application/x-plasma-tray-motion',b'probe')
 e=QDragEnterEvent(QPoint(30,20),Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(view,e);assert e.isAccepted(), 'Tray did not accept the native enter event'
 e=QDragMoveEvent(QPoint(110,20),Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(view,e);assert e.isAccepted() and obj.property('destination')==2, 'Native move event did not update the preview'
 e=QDropEvent(QPointF(110,20),Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(view,e);assert e.isAccepted() and obj.property('dropAccepted') and obj.property('pendingDropOrder').toVariant()==['b','c','a'], 'Drop event did not retain the order snapshot'
 print('Passed: native MIME enter/move/drop events reach the tray through the KDE DropArea and grid hierarchy, update the preview, and retain the drop snapshot.')
