# Plasma Tray Motion

Hold-to-drag icon ordering for the KDE Plasma system tray, with live previews and smooth displacement animations.

![Plasma Tray Motion drag-and-drop demo](docs/images/tray-motion-demo.gif)

## Features

- Reorder visible tray icons and retain their order across Plasma restarts.
- Drag outside the panel and return to continue sorting. Releasing outside cancels.
- Preserve normal clicks, context menus, scrolling, and keyboard actions.
- Configure hold duration and animation speed, or restore the default order.

The default hold duration is 180 ms. Settings allow 100–1500 ms in 10 ms steps. Animation defaults to 160 ms and follows KDE's animation speed setting.

Only visible icons can be reordered. Moving icons into or out of the hidden section is not supported. Icons with identical `itemId` values retain their original relative order.

## Compatibility

Version 0.1.9 is a preview for **Fedora 44, Plasma 6.7.5, x86_64, and Wayland**. This project replaces the system tray plugin; it is not a standalone widget or an official KDE extension.

Release packages require the exact runtime RPM versions listed in `manifest.json`. The drag image adapter uses Qt 6.11 private interfaces, so Qt or Plasma updates require review and rebuilding. Do not reuse a binary built for another runtime version.

Targeted offscreen checks cover ordering, drag routing, image handling, and installation recovery. They do not cover every compositor, panel layout, or scaling configuration.

## Build

Install matching KDE/Qt development packages and run:

```bash
./scripts/build.sh
```

Required tools: Python 3.12+, Git, CMake, Ninja, a C++23 compiler, binutils, and ECM. Development dependencies include Qt6 Core, DBus, Gui, Quick, Widgets, and GuiPrivate; KF6 Config, CoreAddons, I18n, IconThemes, KIO, JobWidgets, Service, ItemModels, WindowSystem, XmlGui, and StatusNotifierItem; Plasma and PlasmaQuick.

The build verifies the pinned upstream archive and applies `patches/plasma-6.7.5-ptm.patch`. Generated sources and build outputs go to `work/`; release directories and archives go to `dist/`. Set `PTM_JOBS` to adjust build parallelism (default: 4).

When editing `work/source`, update the canonical patch before rebuilding. The build refuses to overwrite source changes that differ from the patch.

## Install

Run this in your regular Wayland desktop terminal (without `sudo`):

```bash
curl -fsSL https://raw.githubusercontent.com/gresp-ect/plasma-tray-motion/main/install.sh | bash
```

To check compatibility before installing:

```bash
curl -fsSL https://raw.githubusercontent.com/gresp-ect/plasma-tray-motion/main/install.sh | bash -s -- --check
```

The release download retries connection failures, including interrupted TLS handshakes. If downloading still fails, installation does not start; check your connection to GitHub and rerun the command.

The download script pins version 0.1.9 and verifies the release archive's SHA-256 before running the existing installer. It retains the verified package under `${XDG_DATA_HOME:-$HOME/.local/share}/plasma-tray-motion/releases/` and prints the path to `uninstall.sh` for removal or recovery. This does not expand the supported runtime versions listed above. Forward `--official-plugin /path/to/systemtray.so.stock` when a matching official backup is required.

Alternatively, download and inspect the script before running it:

```bash
curl -fsSL --retry 3 --retry-all-errors --connect-timeout 15 --max-time 60 https://raw.githubusercontent.com/gresp-ect/plasma-tray-motion/main/install.sh -o ptm-install.sh
less ptm-install.sh
bash ptm-install.sh
```

Extract a release archive and run from its directory as your regular desktop user:

```bash
./install.sh --check
./install.sh
```

Installation verifies package versions and file digests, backs up the current plugin, and requests sudo only for system plugin writes. It then restarts Plasma and checks startup. Unknown tray customizations are rejected.

If an existing customization requires an official plugin backup, supply a file matching the current RPM:

```bash
./install.sh --official-plugin /path/to/systemtray.so.stock
```

## Uninstall and recovery

```bash
./uninstall.sh --check
./uninstall.sh
```

Uninstall restores the official plugin verified against the current RPM. Other desktop settings are left intact. Plugin recovery files are stored in `/var/lib/plasma-tray-motion/`; tray configuration backups are in `~/.local/state/plasma-tray-motion/`.

Recover an interrupted installation or uninstall with:

```bash
./uninstall.sh --rollback-pending
```

After a Plasma update, never restore an old plugin backup. If necessary, restore the current official plugin through the package manager:

```bash
sudo dnf reinstall plasma-workspace-libs
systemctl --user restart plasma-plasmashell.service
```

Run `./diagnose.sh` to collect local diagnostic files. Review their contents before sharing.

## Development checks

Run the checks from the repository root:

```bash
python3 scripts/prepare.py
python3 scripts/check-native-drag.py
python3 scripts/check-drop-router.py
python3 scripts/check-drop-routing.py
python3 scripts/check-installer.py
python3 scripts/check-bootstrap.py
```

The checks require Qt6 Quick/Test development packages, `qmltestrunner`, and PySide6. The bootstrap check also uses curl and the OpenSSL CLI to test TLS retries against a temporary local HTTPS server. They run offscreen or in temporary directories without modifying the desktop.

## License

Based on KDE Plasma Workspace v6.7.5. See [NOTICE.md](NOTICE.md) for source and licensing details, [LICENSE](LICENSE) for the project license, and `LICENSES/` for upstream license texts.
