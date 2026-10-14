# Sources and licenses

Plasma Tray Motion is based on KDE Plasma Workspace v6.7.5, commit
`cc1ab7963f94a9b76836412855caed6b94066188`.

Upstream: https://invent.kde.org/plasma/plasma-workspace

`vendor/plasma-workspace-6.7.5-subset.tar.xz` contains the build-required source subset exported from that commit. Its digest and selected directories are recorded in `upstream.lock.json`. Original copyright notices, license texts, and locale metadata are preserved.

The patch adds gesture handling, ordering previews, animations, configuration, and native drag routing. New QML files use LGPL-2.0-or-later. New C++ files, scripts, build files, and project documentation use GPL-2.0-or-later. Modifications to upstream files follow their existing licenses and retain original author attributions.

Full license texts are included in `LICENSES/`; the project license is in `LICENSE`. Release archives do not include Fedora's official plugin binary. Installation creates a recovery copy from the local official file or a backup verified against the current RPM.

This project is not affiliated with KDE.
