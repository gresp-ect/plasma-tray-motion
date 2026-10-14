#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
ptm_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ptm_root"
python3 scripts/prepare.py
export SOURCE_DATE_EPOCH=1788839412
cmake -S . -B work/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  "-DCMAKE_CXX_FLAGS=-ffile-prefix-map=$ptm_root=/usr/src/plasma-tray-motion"
cmake --build work/build --target org.kde.plasma.systemtray --parallel "${PTM_JOBS:-4}"
python3 scripts/make-release.py
