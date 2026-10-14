#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Plasma Tray Motion installer. User configuration is always handled by an unprivileged user process."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

PLUGIN = Path('/usr/lib64/qt6/plugins/plasma/applets/org.kde.plasma.systemtray.so')
DATABASE = Path('/var/lib/plasma-tray-motion')
UNIT = 'plasma-plasmashell.service'
LEGACY = '7a1e6c09514ff568c81fd26c5072dd32ccbc31ad0d2e1385946c64e62524292f'
ROOT = Path(__file__).resolve().parent


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True, **kwargs)


def output(args):
    return run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def package_version(name):
    return output(['/usr/bin/rpm', '-q', '--qf', '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}', name])


def official_digest():
    for line in output(['/usr/bin/rpm', '-q', '--dump', 'plasma-workspace-libs']).splitlines():
        parts = line.split()
        if parts[0] == str(PLUGIN):
            digest = parts[3]
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise RuntimeError('Official plugin digest in the RPM is not SHA-256; stopping.')
            return digest
    raise RuntimeError('Current RPM has no record of the tray plugin file.')


def manifest():
    data = load(ROOT / 'manifest.json')
    for name, digest in data['files'].items():
        path = ROOT / name
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError('Release file is missing or failed verification: ' + name)
    return data


def check_environment(data, session=False):
    release = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            release[key] = value.strip('"')
    if (release.get('ID'), release.get('VERSION_ID'), platform.machine()) != ('fedora', '44', 'x86_64'):
        raise RuntimeError('This release supports Fedora 44 / x86_64 only.')
    if session and os.environ.get('XDG_SESSION_TYPE') != 'wayland':
        raise RuntimeError('Run in a regular user terminal within a Wayland desktop session.')
    for name, required in data['runtime_packages'].items():
        actual = package_version(name)
        if actual != required:
            raise RuntimeError(f'Version mismatch: {actual}; required: {required}. Rebuild the project.')
    if official_digest() != data['official_sha256']:
        raise RuntimeError('Official file digest in the current RPM differs from the release target; rebuild the project.')


def atomic_plugin(source, expected):
    # Stage on the target filesystem and verify the copied contents before renaming.
    if PLUGIN.is_symlink() or not PLUGIN.is_file():
        raise RuntimeError('System plugin is not a regular file; stopping.')
    descriptor, name = tempfile.mkstemp(prefix='.ptm-', suffix='.so', dir=PLUGIN.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream, Path(source).open('rb') as incoming:
            shutil.copyfileobj(incoming, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if sha(temporary) != expected:
            raise RuntimeError('Staged plugin verification failed.')
        os.chown(temporary, 0, 0)
        temporary.chmod(0o755)
        # Restore the target file SELinux context before replacement.
        if Path('/usr/sbin/selinuxenabled').exists():
            enabled = subprocess.run(['/usr/sbin/selinuxenabled']).returncode == 0
            if enabled:
                run(['/usr/bin/chcon', '--reference=' + str(PLUGIN), str(temporary)])
        os.replace(temporary, PLUGIN)
        directory = os.open(PLUGIN.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def inspect_install(data, state):
    current = sha(PLUGIN)
    known = {data['official_sha256'], LEGACY}
    if state.get('installed'):
        known.add(state['installed']['sha256'])
    if current not in known:
        raise RuntimeError('Unknown tray customization detected; refusing to overwrite it. Verify it or restore the official plugin first.')
    return current


def root_action(action, token=None, official=None):
    if os.geteuid() != 0:
        raise RuntimeError('Internal installation operations require administrator privileges.')
    DATABASE.mkdir(mode=0o755, parents=True, exist_ok=True)
    with (DATABASE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = DATABASE / 'state.json'
        state = load(state_path) if state_path.exists() else {'installed': None, 'pending': None}
        if action in ('finalize', 'rollback'):
            if not token or state.get('pending') != token:
                raise RuntimeError('Transaction ID does not match the pending transaction.')
            transaction = DATABASE / 'transactions' / token
            record = load(transaction / 'record.json')
            if package_version('plasma-workspace-libs') != record['plasma_rpm']:
                raise RuntimeError('Plasma was updated during the transaction; refusing to restore an old plugin. Restore through the package manager.')
            current = sha(PLUGIN)
            allowed = {record['applied_sha256'], record['previous_sha256']} if action == 'rollback' else {record['applied_sha256']}
            if current not in allowed:
                raise RuntimeError('Plugin changed after the transaction; refusing to overwrite it.')
            if action == 'rollback':
                if current != record['previous_sha256']:
                    atomic_plugin(transaction / 'previous.so', record['previous_sha256'])
                state = record['previous_state']
            else:
                state['installed'] = record['next_installed']
                state['pending'] = None
            save(state_path, state)
            return {'action': action, 'transaction': token}
        if state.get('pending'):
            raise RuntimeError('An unfinished transaction exists: ' + state['pending'] + '; run ./uninstall.sh --rollback-pending before retrying.')
        data = manifest() if action == 'install' else {}
        current = sha(PLUGIN)
        rpm_digest = official_digest()
        if action == 'uninstall' and current == rpm_digest:
            state['installed'] = None
            save(state_path, state)
            return {'already_official': True}
        if action == 'install':
            check_environment(data)
            current = inspect_install(data, state)
            stock = DATABASE / ('official-' + rpm_digest + '.so')
            if not stock.exists() or sha(stock) != rpm_digest:
                candidate = PLUGIN if current == rpm_digest else Path(official) if official else None
                if candidate is None or not candidate.is_file() or sha(candidate) != rpm_digest:
                    raise RuntimeError('An official plugin matching the current RPM is required. Specify a stock backup with --official-plugin PATH.')
                contents = candidate.read_bytes()
                if hashlib.sha256(contents).hexdigest() != rpm_digest:
                    raise RuntimeError('Stock backup verification failed.')
                stock.write_bytes(contents)
                stock.chmod(0o644)
            target = ROOT / 'payload/systemtray.so'
            target_sha = data['files']['payload/systemtray.so']
            next_installed = {'sha256': target_sha, 'version': data['version'],
                              'plasma_rpm': package_version('plasma-workspace-libs'),
                              'official_sha256': rpm_digest}
        elif action == 'uninstall':
            installed = state.get('installed')
            if not installed or current != installed['sha256']:
                raise RuntimeError('Current plugin is not the recorded PTM plugin; refusing to overwrite it.')
            if package_version('plasma-workspace-libs') != installed['plasma_rpm'] or rpm_digest != installed['official_sha256']:
                raise RuntimeError('Plasma was updated; use sudo dnf reinstall plasma-workspace-libs to restore the current official plugin.')
            target_sha = rpm_digest
            target = DATABASE / ('official-' + rpm_digest + '.so')
            if not target.is_file() or sha(target) != rpm_digest:
                raise RuntimeError('Official backup is missing or damaged; restore through the package manager.')
            next_installed = None
        else:
            raise RuntimeError('Unknown internal operation.')
        token = uuid.uuid4().hex
        transaction = DATABASE / 'transactions' / token
        transaction.mkdir(parents=True, mode=0o755)
        shutil.copyfile(PLUGIN, transaction / 'previous.so')
        if sha(transaction / 'previous.so') != current:
            raise RuntimeError('Plugin changed before installation; stopping.')
        record = {'previous_state': state.copy(), 'previous_sha256': current,
                  'applied_sha256': target_sha, 'next_installed': next_installed,
                  'plasma_rpm': package_version('plasma-workspace-libs')}
        save(transaction / 'record.json', record)
        # Write recovery records to disk before modifying a file in use.
        state['pending'] = token
        save(state_path, state)
        try:
            atomic_plugin(target, target_sha)
        except BaseException:
            if sha(PLUGIN) == current:
                save(state_path, record['previous_state'])
            raise
        return {'transaction': token, 'action': action, 'previous_sha256': current, 'installed_sha256': target_sha}


def privileged(action, token=None, official=None):
    args = ['/usr/bin/sudo', '/usr/bin/python3', str(Path(__file__).resolve()), '--root-action', action]
    if token:
        args += ['--transaction', token]
    if official:
        args += ['--official-plugin', str(Path(official).resolve())]
    try:
        return json.loads(output(args))
    except subprocess.CalledProcessError as exc:
        raise RuntimeError((exc.stderr or str(exc)).strip()) from exc


def config_snapshot():
    path = Path.home() / '.config/plasma-org.kde.plasma.desktop-appletsrc'
    if not path.exists():
        return ''
    chunks = re.split(r'(?=^\[)', path.read_text(), flags=re.MULTILINE)
    parents = []
    for chunk in chunks:
        header = chunk.splitlines()[0] if chunk else ''
        if re.fullmatch(r'\[Containments\]\[\d+\]\[Applets\]\[\d+\]', header) and '\nplugin=org.kde.plasma.systemtray\n' in '\n' + chunk:
            parents.append(header)
    return ''.join(chunk for chunk in chunks if any(chunk.startswith(prefix + '\n') or chunk.startswith(prefix + '[General]\n') for prefix in parents))


def restart_and_observe(expect_ptm=None):
    since = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    run(['/usr/bin/systemctl', '--user', 'restart', UNIT], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pid = None
    restarts = None
    for _ in range(8):
        time.sleep(1)
        props = dict(line.split('=', 1) for line in output(['/usr/bin/systemctl', '--user', 'show', UNIT, '-p', 'ActiveState', '-p', 'MainPID', '-p', 'NRestarts']).splitlines())
        if props['ActiveState'] != 'active' or props['MainPID'] == '0':
            raise RuntimeError('Plasma service did not remain running.')
        if pid is not None and (pid != props['MainPID'] or restarts != props['NRestarts']):
            raise RuntimeError('Plasma restarted during the startup check.')
        pid, restarts = props['MainPID'], props['NRestarts']
    logs = output(['/usr/bin/journalctl', '--user', '-u', UNIT, '--since', since, '-o', 'cat', '--no-pager'])
    if expect_ptm and f'Plasma Tray Motion {expect_ptm} loaded' not in logs:
        raise RuntimeError('Could not confirm that the new PTM plugin loaded.')
    for line in logs.splitlines():
        if re.search(r'PtmController|/systemtray/', line) and re.search(r'TypeError|ReferenceError|is not a type|Cannot assign|Invalid property|is not available', line):
            raise RuntimeError('Tray QML loading error: ' + line)


def diagnose(destination):
    destination = Path(destination or ('ptm-diagnose-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    info = {'architecture': platform.machine(), 'session': os.environ.get('XDG_SESSION_TYPE'), 'plugin_sha256': sha(PLUGIN)}
    for name, args in {'os': ['cat', '/etc/os-release'], 'plasma': ['plasmashell', '--version'],
                       'package': ['/usr/bin/rpm', '-q', 'plasma-workspace-libs'],
                       'service': ['/usr/bin/systemctl', '--user', 'show', UNIT, '-p', 'ActiveState', '-p', 'MainPID', '-p', 'NRestarts']}.items():
        try:
            info[name] = output(args)
        except (OSError, subprocess.CalledProcessError) as exc:
            info[name] = str(exc)
    save(destination / 'system.json', info)
    (destination / 'tray-config.txt').write_text(config_snapshot())
    try:
        logs = output(['/usr/bin/journalctl', '--user', '-u', UNIT, '-b', '-n', '1000', '-o', 'cat', '--no-pager'])
        lines = [line.replace(str(Path.home()), '~') for line in logs.splitlines() if re.search(r'ptm|systemtray|PtmController|cannot grab mouse|onPressed', line, re.IGNORECASE)]
        (destination / 'tray-journal.txt').write_text('\n'.join(lines) + '\n')
    except subprocess.CalledProcessError:
        (destination / 'tray-journal.txt').write_text('Journal unavailable.\n')
    print('Diagnostics saved: ' + str(destination) + '\nReview application names and personal information in the configuration and logs before sharing.')


class PtmArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError('Command-line argument error: ' + message)


def main():
    parser = PtmArgumentParser(description=__doc__, add_help=False,
        usage='%(prog)s [install|uninstall|diagnose] [options]')
    parser._positionals.title = 'actions'
    parser._optionals.title = 'options'
    parser.add_argument('-h', '--help', action='help', help='Show help and exit')
    parser.add_argument('action', nargs='?', choices=['install', 'uninstall', 'diagnose'], help='Install, uninstall, or collect diagnostics')
    parser.add_argument('--check', action='store_true', help='Check only; do not install, back up, or restart')
    parser.add_argument('--official-plugin', metavar='OFFICIAL_PLUGIN_PATH', help='Specify an official plugin backup matching the current RPM')
    parser.add_argument('--output', metavar='DIRECTORY', help='Specify the diagnostics output directory')
    parser.add_argument('--rollback-pending', action='store_true', help='Recover an unfinished installation or uninstall transaction')
    parser.add_argument('--root-action', choices=['install', 'uninstall', 'finalize', 'rollback'], help=argparse.SUPPRESS)
    parser.add_argument('--transaction', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.root_action:
        print(json.dumps(root_action(args.root_action, args.transaction, args.official_plugin)))
        return
    if os.geteuid() == 0:
        raise RuntimeError('Run as the regular desktop user; only plugin writes request sudo.')
    if args.action == 'diagnose':
        diagnose(args.output)
        return
    if args.rollback_pending:
        if args.action != 'uninstall':
            parser.error('--rollback-pending is only valid with uninstall')
        state = load(DATABASE / 'state.json')
        token = state.get('pending')
        if not token:
            raise RuntimeError('No pending transaction to recover.')
        if args.check:
            print('Transaction to roll back: ' + token + '; read-only check, recovery was not performed.')
            return
        privileged('rollback', token)
        restart_and_observe()
        print('Unfinished transaction recovered.')
        return
    data = manifest() if args.action == 'install' else {}
    if args.action == 'install':
        check_environment(data, session=True)
        state = load(DATABASE / 'state.json') if (DATABASE / 'state.json').exists() else {}
        inspect_install(data, state)
        if sha(PLUGIN) != data['official_sha256']:
            stock = DATABASE / ('official-' + data['official_sha256'] + '.so')
            candidate = Path(args.official_plugin).resolve() if args.official_plugin else stock
            if not candidate.is_file() or sha(candidate) != data['official_sha256']:
                raise RuntimeError('Current tray is customized; specify a verified matching official backup with --official-plugin PATH.')
    if args.check:
        if args.action == 'uninstall':
            state = load(DATABASE / 'state.json') if (DATABASE / 'state.json').exists() else {}
            if sha(PLUGIN) != official_digest():
                installed = state.get('installed')
                if not installed or sha(PLUGIN) != installed['sha256'] or installed['official_sha256'] != official_digest() or installed['plasma_rpm'] != package_version('plasma-workspace-libs'):
                    raise RuntimeError('Cannot uninstall safely: the current plugin or official version does not match the PTM installation record.')
        print('Read-only check passed; system and configuration were not modified.')
        return
    if args.action not in ('install', 'uninstall'):
        parser.error('Choose install / uninstall / diagnose')
    if os.environ.get('XDG_SESSION_TYPE') != 'wayland':
        raise RuntimeError('Run in a regular user terminal on the Wayland desktop.')
    if output(['/usr/bin/systemctl', '--user', 'is-active', UNIT]) != 'active':
        raise RuntimeError('Plasma service is not running; stopping.')
    backup = Path.home() / '.local/state/plasma-tray-motion' / (datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True, mode=0o700)
    (backup / 'tray-config.txt').write_text(config_snapshot())
    print('Tray configuration backup: ' + str(backup), flush=True)
    result = privileged(args.action, official=args.official_plugin)
    save(backup / 'transaction.json', result)
    if result.get('already_official'):
        print('System already has the official tray from the current RPM; no restoration needed.')
        return
    token = result['transaction']
    try:
        restart_and_observe(expect_ptm=data['version'] if args.action == 'install' else None)
        privileged('finalize', token)
    except BaseException:
        print('Desktop startup check failed; restoring the pre-install plugin...', file=sys.stderr, flush=True)
        privileged('rollback', token)
        restart_and_observe()
        raise RuntimeError('Pre-install plugin restored; run diagnose.sh to inspect the relevant logs.')
    print('Plasma Tray Motion installed; test dragging manually.' if args.action == 'install' else 'Official tray for the current version restored; other customizations are unchanged.')
    print('Configuration backups retained; old panel settings were not applied to the current desktop.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Error: ' + str(error), file=sys.stderr)
        sys.exit(1)
