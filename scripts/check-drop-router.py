#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile the actual C++ router and check native window events offscreen."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'work/source/applets/systemtray'
with tempfile.TemporaryDirectory(prefix='ptm-router-check-') as temporary:
    directory = Path(temporary)
    (directory / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.25)
project(PtmRouterCheck LANGUAGES CXX)
set(CMAKE_AUTOMOC ON)
set(CMAKE_CXX_STANDARD 23)
find_package(Qt6 REQUIRED COMPONENTS Quick Test)
find_package(Qt6GuiPrivate CONFIG REQUIRED)
add_executable(check "{root / 'scripts/drop-router-check.cpp'}" "{source / 'ptmdroprouter.cpp'}" "{source / 'ptmdroprouter.h'}")
target_include_directories(check PRIVATE "{source}")
target_link_libraries(check PRIVATE Qt6::Quick Qt6::Test Qt6::GuiPrivate)
''')
    (directory / 'main.qml').write_text('''import QtQuick
Item {
    id: root; width: 200; height: 60
    property int stolenDrops: 0
    property bool captureFinished: false
    function captureFromQml() {
        imageGrid.grabToImage(result => {
            pixelBridge.runNativeDrag(result, "own-gesture");
            captureFinished = true;
        });
    }
    Item { id: imageGrid; objectName: "grid"; x: 40; y: 10; width: 120; height: 40; Rectangle { anchors.fill: parent; color: "red" } }
    DropArea {
        anchors.fill: parent; z: 50000
        onEntered: event => { event.accepted = true; }
        onDropped: event => { ++root.stolenDrops; event.accept(Qt.MoveAction); }
    }
}
''')
    for command in [['cmake','-S',str(directory),'-B',str(directory/'build'),'-G','Ninja'], ['cmake','--build',str(directory/'build'),'--parallel','2']]:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
    subprocess.run([str(directory/'build/check'),str(directory/'main.qml')], check=True,
                   env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software'))

print('Passed: blocking receiver negative control, leave/reenter window drop routing, coordinate mapping, external/unrelated drags, filter cleanup, screenshot pixels and native image offset, four inside/outside cycles, deferred painting, reentry rejection, and repaint after cancellation.')
