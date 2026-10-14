#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

root = Path(__file__).resolve().parents[1]
os.chdir(root)
def output(args):
    return subprocess.check_output(args, text=True).strip()
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
if output(['rpm','-q','--qf','%{VERSION}', 'plasma-workspace-libs']) != '6.7.5':
    raise SystemExit('Current Plasma does not match upstream source 6.7.5; refusing to release.')
if output(['uname','-m']) != 'x86_64':
    raise SystemExit('This release supports x86_64 only.')
name = 'plasma-tray-motion-0.1.9-fedora44-plasma6.7.5-x86_64'
destination = root / 'dist' / name
if destination.exists():
    shutil.rmtree(destination)
destination.mkdir(parents=True)
for entry in ['CMakeLists.txt','upstream.lock.json','README.md','NOTICE.md','LICENSE','LICENSES','patches','vendor','scripts','packaging']:
    source = root / entry
    if source.is_dir():
        shutil.copytree(source, destination / entry, ignore=shutil.ignore_patterns('__pycache__'))
    else:
        shutil.copy2(source, destination / entry)
for source in (root / 'packaging').iterdir():
    if source.is_file(): shutil.copy2(source, destination / source.name)
payload = destination / 'payload/systemtray.so'
payload.parent.mkdir()
shutil.copy2(root / 'work/build/bin/plasma/applets/org.kde.plasma.systemtray.so', payload)
subprocess.run(['strip','--strip-debug',str(payload)], check=True)
ldd = output(['ldd', str(payload)])
if 'not found' in ldd:
    raise SystemExit('Plugin dependencies are missing; refusing to package.')
paths = {str(Path(path).resolve()) for path in re.findall(r'=> (/\S+)', ldd)}
packages = {'plasma-workspace-libs','plasma-workspace','libplasma','qt6-qtdeclarative','kf6-kirigami','kf6-kdeclarative','kf6-kcmutils','kf6-kitemmodels','libplasma-components'}
# Some Fedora QML modules share packages; query the actual package owning each file.
packages.discard('libplasma-components')
for path in paths:
    packages.update(output(['rpm','-qf','--qf','%{NAME}\n',path]).splitlines())
versions = {package: output(['rpm','-q','--qf','%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}',package]) for package in sorted(packages)}
stock = None
for line in output(['rpm','-q','--dump','plasma-workspace-libs']).splitlines():
    parts = line.split()
    if parts[0] == '/usr/lib64/qt6/plugins/plasma/applets/org.kde.plasma.systemtray.so': stock = parts[3]
if not stock or not re.fullmatch('[0-9a-f]{64}', stock):
    raise SystemExit('Official plugin SHA-256 is missing or invalid in the current RPM.')
manifest = {'version':'0.1.9','status':'preview','distribution':'fedora','distribution_version':'44','plasma_version':'6.7.5','architecture':'x86_64','upstream':json.loads((root / 'upstream.lock.json').read_text()),'official_sha256':stock,'runtime_packages':versions,'build_tools':{tool:output([tool,'--version']).splitlines()[0] for tool in ['cmake','c++','ninja']},'files':{str(path.relative_to(destination)):digest(path) for path in sorted(destination.rglob('*')) if path.is_file()}}
(destination / 'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
files = sorted(path for path in destination.rglob('*') if path.is_file())
(destination / 'SHA256SUMS').write_text(''.join(digest(path)+'  '+str(path.relative_to(destination))+'\n' for path in files))
archive = Path(str(destination)+'.tar.xz')
with tarfile.open(archive,'w:xz') as stream:
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            info=stream.gettarinfo(str(path),arcname=str(Path(name)/path.relative_to(destination)))
            info.uid=info.gid=0;info.uname=info.gname='';info.mtime=1788839412
            with path.open('rb') as data: stream.addfile(info,data)
print('Release directory: '+str(destination))
print('Release archive: '+str(archive))
print('SHA-256: '+digest(archive))
