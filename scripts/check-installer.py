#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check recovery transactions in a temporary directory without touching the real desktop."""
import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ptm', root / 'packaging/ptm.py')
ptm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ptm)
with tempfile.TemporaryDirectory(prefix='ptm-installer-check-') as temporary:
    base = Path(temporary)
    plugin = base / 'live.so'
    official = base / 'stock.so'
    payload = base / 'payload/systemtray.so'
    payload.parent.mkdir()
    plugin.write_bytes(b'previous custom plugin')
    official.write_bytes(b'official plugin')
    payload.write_bytes(b'independent PTM plugin')
    previous = ptm.sha(plugin)
    stock = ptm.sha(official)
    new = ptm.sha(payload)
    data = {'version':'0.1.0','official_sha256':stock,'files':{'payload/systemtray.so':new}}
    def simulated_atomic(source, expected):
        contents = Path(source).read_bytes()
        assert ptm.hashlib.sha256(contents).hexdigest() == expected
        plugin.write_bytes(contents)
    with patch.object(ptm, 'PLUGIN', plugin), patch.object(ptm, 'DATABASE', base / 'database'), patch.object(ptm, 'ROOT', base), patch.object(ptm, 'LEGACY', previous), patch.object(ptm.os, 'geteuid', return_value=0), patch.object(ptm, 'manifest', return_value=data), patch.object(ptm, 'check_environment'), patch.object(ptm, 'official_digest', return_value=stock), patch.object(ptm, 'package_version', return_value='plasma-workspace-libs-6.7.5-1.fc44.x86_64'), patch.object(ptm, 'atomic_plugin', side_effect=simulated_atomic):
        result = ptm.root_action('install', official=str(official))
        assert ptm.sha(plugin) == new
        ptm.root_action('rollback', result['transaction'])
        assert ptm.sha(plugin) == previous, 'Failure rollback must restore the pre-install custom plugin'
        result = ptm.root_action('install', official=str(official))
        ptm.root_action('finalize', result['transaction'])
        result = ptm.root_action('uninstall')
        assert ptm.sha(plugin) == stock, 'Uninstall must restore the official plugin'
        ptm.root_action('rollback', result['transaction'])
        assert ptm.sha(plugin) == new
        result = ptm.root_action('uninstall')
        ptm.root_action('finalize', result['transaction'])
        assert ptm.sha(plugin) == stock
        assert ptm.load(base / 'database/state.json')['installed'] is None
        plugin.write_bytes(b'unknown customization')
        try:
            ptm.root_action('install', official=str(official))
        except RuntimeError as error:
            assert 'Unknown' in str(error)
        else:
            raise AssertionError('Unknown plugins must not be overwritten')
print('Temporary directory checks passed: installation failure restores the previous customization, uninstall restores the official plugin, uninstall failure restores PTM, and unknown customizations are rejected.')

# Check startup marker matching without restarting a service or reading real logs.
def simulated_output(args):
    if args[0] == '/usr/bin/systemctl':
        return 'ActiveState=active\nMainPID=123\nNRestarts=0'
    assert args[0] == '/usr/bin/journalctl'
    return 'Plasma Tray Motion 0.1.9 loaded'

with patch.object(ptm, 'run'), patch.object(ptm, 'output', side_effect=simulated_output), patch.object(ptm.time, 'sleep'):
    ptm.restart_and_observe('0.1.9')
    try:
        ptm.restart_and_observe('0.1.8')
    except RuntimeError as error:
        assert 'Could not confirm' in str(error)
    else:
        raise AssertionError('A marker for another version must not pass startup verification')
print('Startup marker checks passed: English marker accepted, mismatched version rejected; no service restarted.')
