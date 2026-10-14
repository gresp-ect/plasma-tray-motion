#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Targeted QML controller checks with simulated C++ drag and image interfaces."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'work/source/applets/systemtray/qml'
controller = (source / 'PtmController.qml').read_text()
# Replace only component configuration and commit interfaces; retain the actual drag logic.
controller = controller.replace('import org.kde.plasma.plasmoid\n', '')
controller = controller.replace('Plasmoid.configuration', 'testConfig')
controller = controller.replace('Plasmoid.ptmCommitOrder(order)', 'motion.testCommits.push(order)')
controller = controller.replace('Plasmoid.ptmWatchNativeDrop', 'motion.testBridge.ptmWatchNativeDrop').replace('Plasmoid.ptmUnwatchNativeDrop', 'motion.testBridge.ptmUnwatchNativeDrop').replace('Plasmoid.ptmRunNativeDrag', 'motion.testBridge.ptmRunNativeDrag').replace('target: Plasmoid', 'target: motion.testBridge')
controller = controller.replace('    id: motion', '''    id: motion
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
    }''', 1)
with tempfile.TemporaryDirectory(prefix='ptm-native-check-') as temporary:
    directory = Path(temporary)
    (directory / 'PtmController.qml').write_text(controller)
    (directory / 'ItemLoader.qml').write_bytes((source / 'ItemLoader.qml').read_bytes())
    (directory / 'StatusNotifierItem.qml').write_text('import QtQuick\nItem { required property int index; required property int status; required property int effectiveStatus; required property var model }\n')
    (directory / 'tst_native.qml').write_text('''import QtQuick
import QtTest
Item {
    width: 160; height: 40
    GridView {
        id: grid; width: 160; height: 40; cellWidth: 40; cellHeight: 40
        model: dataModel; delegate: ItemLoader { width: 40; height: 40 }
    }
    ListModel {
        id: dataModel
        ListElement { itemId: "a"; itemType: "StatusNotifier"; status: 2; effectiveStatus: 2 }
        ListElement { itemId: "b"; itemType: "StatusNotifier"; status: 2; effectiveStatus: 2 }
        ListElement { itemId: "c"; itemType: "StatusNotifier"; status: 2; effectiveStatus: 2 }
    }
    PtmController { id: subject; grid: grid; model: dataModel; iconSize: 24 }
    SignalSpy { id: started; target: subject.testBridge; signalName: "nativeStarted" }
    TestCase {
        name: "NativeDragRegression"
        when: windowShown
        function init() {
            subject.reset(); subject.testCommits = []; started.clear();
            failOnWarning(/.*drag must be active.*/);
        }
        function test_hold180NotClampedTo200() {
            const timer = findChild(subject, "ptmHoldTimer");
            verify(timer !== null, "Hold timer was not found");
            compare(timer.interval, 180);
        }
        function test_manualNativeStartAndRetry() {
            for (let i = 0; i < 2; ++i) {
                subject.dragIndex = 0;
                subject.capture = ({url: ""});
                subject.startNative();
                compare(started.count, i + 1);
                compare(subject.nativeRunning, false);
            }
        }
        function seedLocal() {
            subject.dragIndex = 0; subject.destination = 0;
            subject.ids = ["a", "b", "c"];
            subject.slots = [Qt.point(0,0), Qt.point(40,0), Qt.point(80,0)];
        }
        function test_localReorderWithoutNative() {
            seedLocal();
            subject.move(Qt.point(100,20));
            compare(subject.destination, 2);
            compare(subject.offsetFor(1).x, -40);
            compare(subject.nativeRunning, false);
            subject.finish(Qt.point(100,20));
            compare(subject.testCommits.length, 1);
            compare(subject.testCommits[0].join(","), "b,c,a");
            compare(started.count, 0);
        }
        function test_dataRefreshDoesNotCancelButIdentityChangeDoes() {
            seedLocal();
            dataModel.setProperty(0, "status", 3);
            wait(1);
            compare(subject.dragIndex, 0);
            verify(subject.snapshotMatches());
            dataModel.setProperty(0, "itemId", "changed");
            wait(1);
            compare(subject.dragIndex, -1);
            dataModel.setProperty(0, "itemId", "a");
        }
        function prepare() {
            subject.nativeRunning = true;
            subject.dragIndex = 0;
            subject.destination = 0;
            subject.ids = ["a", "b", "c"];
            subject.slots = [Qt.point(0,0), Qt.point(40,0), Qt.point(80,0)];
            verify(subject.prepareDrop(Qt.point(100,20)));
        }
        function test_panelWindowSignalsRestorePreviewAndSubmit() {
            prepare();
            subject.dropAccepted = false;
            subject.pendingDropOrder = [];
            subject.token = "window-route";
            subject.testBridge.ptmNativeDragLeft("window-route");
            compare(subject.inside, false);
            subject.testBridge.ptmNativeDragMoved("foreign-route", Qt.point(100,20));
            compare(subject.inside, false);
            subject.testBridge.ptmNativeDragMoved("window-route", Qt.point(100,20));
            compare(subject.destination, 2);
            compare(subject.inside, true);
            compare(subject.offsetFor(1).x, -40);
            subject.testBridge.ptmNativeDragDropped("window-route", Qt.point(100,20));
            subject.completeNative(Qt.MoveAction);
            compare(subject.testCommits.length, 1);
            compare(subject.testCommits[0].join(","), "b,c,a");
        }
        function test_repeatedInsideOutsideKeepsLocalAppearance() {
            prepare();
            subject.pressPosition = Qt.point(20,20);
            subject.token = "repeated-route";
            subject.dropAccepted = false; subject.pendingDropOrder = [];
            for (let i = 0; i < 4; ++i) {
                subject.testBridge.ptmNativeDragLeft("repeated-route");
                compare(subject.inside, false);
                compare(subject.destination, 0);
                compare(subject.offsetFor(0).x, 0);
                subject.testBridge.ptmNativeDragMoved("repeated-route", Qt.point(100,20));
                compare(subject.inside, true);
                compare(subject.destination, 2);
                compare(subject.offsetFor(0).x, 80);
                compare(subject.offsetFor(1).x, -40);
                compare(subject.testCommits.length, 0);
            }
            subject.testBridge.ptmNativeDragDropped("repeated-route", Qt.point(100,20));
            subject.completeNative(Qt.MoveAction);
            compare(subject.testCommits.length, 1);
        }
        function test_dropSurvivesPlatformLeave() {
            prepare();
            subject.move(Qt.point(-1,-1));
            subject.completeNative(Qt.MoveAction);
            compare(subject.testCommits.length, 1);
            compare(subject.testCommits[0].join(","), "b,c,a");
            compare(subject.nativeRunning, false);
        }
        function test_invalidatedDropDoesNotSave() {
            prepare(); subject.cancel();
            subject.completeNative(Qt.MoveAction);
            compare(subject.testCommits.length, 0);
            compare(subject.nativeRunning, false);
        }
        function test_nativeCancelClearsCaptureAndRejectsNewGesture() {
            prepare();
            subject.token = "original-gesture";
            subject.capture = ({url: "old-image"});
            const serial = subject.captureSerial;
            subject.cancel();
            compare(subject.nativeRunning, true);
            compare(subject.nativeInvalidated, true);
            compare(subject.capture, null);
            verify(subject.captureSerial > serial);
            compare(subject.dragIndex, -1);
            compare(subject.ids.length, 0);
            compare(subject.delta, Qt.point(0,0));
            subject.arm(fakeItem(), 20, 20);
            compare(subject.token, "original-gesture");
            compare(subject.sourceItem, null);
            subject.completeNative(Qt.MoveAction);
            compare(subject.testCommits.length, 0);
        }
        function fakeItem() {
            return {mapToItem: () => Qt.point(20,20),
                iconContainer: {grabToImage: callback => {}}};
        }
        function test_nativeGestureCannotBeRearmed() {
            prepare();
            subject.token = "original-gesture";
            subject.arm(fakeItem(), 20, 20);
            compare(subject.token, "original-gesture");
            compare(subject.nativeInvalidated, false);
            compare(subject.dragIndex, 0);
            subject.completeNative(Qt.MoveAction);
            compare(subject.testCommits.length, 1);
        }
        function test_lateCaptureAfterNativeCancelIsIgnored() {
            let deliverCapture;
            const item = fakeItem();
            item.iconContainer.grabToImage = callback => { deliverCapture = callback; };
            subject.arm(item, 20, 20);
            subject.disarm();
            subject.nativeRunning = true;
            subject.cancel();
            deliverCapture({url: "late-image"});
            compare(subject.capture, null);
            subject.completeNative(Qt.IgnoreAction);
            compare(subject.testCommits.length, 0);
        }
    }
}
''')
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
    command = ['/usr/lib64/qt6/bin/qmltestrunner', '-input', str(directory)]
    subprocess.run(command, env=environment, check=True)
