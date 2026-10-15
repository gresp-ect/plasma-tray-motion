#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

# Keep the archive and digest pinned together when publishing a new release.
ptm_version=0.1.9
ptm_name="plasma-tray-motion-${ptm_version}-fedora44-plasma6.7.5-x86_64"
ptm_sha256=5512994f4296318851cc49597931deddf76fe3b448c07025ecdac0b30718c597
ptm_url="https://github.com/gresp-ect/plasma-tray-motion/releases/download/v${ptm_version}/${ptm_name}.tar.xz"

ptm_args=("$@")
while (( $# )); do
    case "$1" in
        --check) shift ;;
        --official-plugin)
            if (( $# < 2 )); then
                echo 'Error: --official-plugin requires a path.' >&2
                exit 2
            fi
            shift 2 ;;
        -h|--help)
            echo 'Usage: bash install.sh [--check] [--official-plugin PATH]'
            echo 'Download and verify Plasma Tray Motion 0.1.9 for Fedora 44 / Plasma 6.7.5 / x86_64 / Wayland.'
            echo 'Run as your regular desktop user. Only system plugin writes request sudo.'
            exit 0 ;;
        *) echo "Error: unknown option: $1" >&2; exit 2 ;;
    esac
done
if (( EUID == 0 )); then
    echo 'Error: run as your regular desktop user, without sudo.' >&2
    exit 1
fi
for ptm_tool in curl sha256sum tar python3 mktemp; do
    command -v "$ptm_tool" >/dev/null || { echo "Error: required tool not found: $ptm_tool" >&2; exit 1; }
done
ptm_base="${XDG_DATA_HOME:-$HOME/.local/share}/plasma-tray-motion/releases"
mkdir -p -- "$ptm_base"
ptm_dir="$(mktemp -d "$ptm_base/${ptm_version}.XXXXXXXX")"
ptm_ready=false
trap 'if [[ "$ptm_ready" == false ]]; then rm -rf -- "$ptm_dir"; fi' EXIT
printf 'Downloading Plasma Tray Motion %s...\n' "$ptm_version"
# TLS handshake failures are not retried by --retry alone. Output to a file
# lets curl discard partial responses before retrying the complete download.
if ! curl --fail --location --show-error --silent --retry 3 --retry-all-errors \
    --retry-max-time 180 --connect-timeout 15 --max-time 60 \
    --proto '=https' --proto-redir '=https' "$ptm_url" -o "$ptm_dir/package.tar.xz"; then
    echo 'Error: release download failed after retries; installation has not started. Check your connection to GitHub and try again.' >&2
    exit 1
fi
printf '%s  %s\n' "$ptm_sha256" "$ptm_dir/package.tar.xz" | sha256sum --check --status || {
    echo 'Error: release SHA-256 verification failed; refusing to install.' >&2
    exit 1
}
tar -xJf "$ptm_dir/package.tar.xz" -C "$ptm_dir"
rm -- "$ptm_dir/package.tar.xz"
ptm_release="$ptm_dir/$ptm_name"
[[ -f "$ptm_release/install.sh" && -f "$ptm_release/uninstall.sh" ]] || {
    echo 'Error: release package is incomplete.' >&2
    exit 1
}
# Retain recovery scripts even if installation fails or is interrupted.
ptm_ready=true
printf 'Verified release: %s\n' "$ptm_release"
printf 'Uninstall or recovery: %s/uninstall.sh\n' "$ptm_release"
bash "$ptm_release/install.sh" "${ptm_args[@]}"
