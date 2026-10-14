#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify the pinned upstream archive and apply the Plasma Tray Motion patch, preserving local changes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
lock = json.loads((root / 'upstream.lock.json').read_text())
archive = root / lock['archive']
if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']:
    raise SystemExit('Upstream source archive verification failed')
work = root / 'work'
work.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='ptm-prepare-', dir='/tmp') as temporary:
    prepared = Path(temporary)
    with tarfile.open(archive) as stream:
        stream.extractall(prepared, filter='data')
    subprocess.run(['git', 'apply', '--check', str(root / 'patches/plasma-6.7.5-ptm.patch')], cwd=prepared, check=True)
    subprocess.run(['git', 'apply', str(root / 'patches/plasma-6.7.5-ptm.patch')], cwd=prepared, check=True)
    source = work / 'source'
    if source.exists():
        def hashes(base):
            return {str(f.relative_to(base)): hashlib.sha256(f.read_bytes()).hexdigest() for f in base.rglob('*') if f.is_file()}
        if hashes(source) != hashes(prepared):
            raise SystemExit('work/source differs from the release patch. Save your changes and update the patch, or move this directory before retrying.')
    else:
        shutil.copytree(prepared, source)
print('Upstream source verification and patch application without fuzz passed.')
