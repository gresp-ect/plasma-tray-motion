#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise bootstrap retries against a local HTTPS server; no desktop operations."""
import hashlib, io, os, pathlib, socket, ssl, subprocess, tarfile, tempfile, threading
root=pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='ptm-tls-test-') as folder:
    temp=pathlib.Path(folder)
    cert=temp/'cert.pem'; key=temp/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    archive=io.BytesIO()
    name='plasma-tray-motion-0.1.9-fedora44-plasma6.7.5-x86_64'
    with tarfile.open(fileobj=archive,mode='w:xz') as tar:
        for file,contents in [('install.sh', '#!/bin/bash\nprintf "%s\\n" "$@" > "$PTM_TEST_MARKER"\n'),('uninstall.sh','#!/bin/bash\n')]:
            data=contents.encode(); info=tarfile.TarInfo(name+'/'+file); info.size=len(data); tar.addfile(info,io.BytesIO(data))
    body=archive.getvalue()
    script=temp/'install.sh'
    script.write_text((root/'install.sh').read_text().replace('5512994f4296318851cc49597931deddf76fe3b448c07025ecdac0b30718c597',hashlib.sha256(body).hexdigest()))
    listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen(); listener.settimeout(.2)
    port=listener.getsockname()[1]
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert,key)
    state={'attempts':0,'failures':2,'corrupt':False,'stop':False}
    def serve():
        while not state['stop']:
            try: conn,_=listener.accept()
            except socket.timeout: continue
            state['attempts']+=1
            if state['attempts']<=state['failures']:
                conn.close(); continue
            try:
                with ctx.wrap_socket(conn,server_side=True) as tls:
                    tls.recv(16384)
                    payload=b'corrupt' if state['corrupt'] else body
                    tls.sendall(b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: '+str(len(payload)).encode()+b'\r\n\r\n'+payload)
            except (OSError,ssl.SSLError): pass
    thread=threading.Thread(target=serve,daemon=True); thread.start()
    bindir=temp/'bin';bindir.mkdir()
    wrapper=bindir/'curl'; wrapper.write_text('''#!/usr/bin/env python3
import os,sys
args=[os.environ['PTM_TEST_URL'] if x.startswith('https://github.com/') else x for x in sys.argv[1:]]
os.execv('/usr/bin/curl',['curl','--cacert',os.environ['PTM_TEST_CERT'],*args])
''');wrapper.chmod(0o755)
    marker=temp/'called'
    env=dict(os.environ,PATH=str(bindir)+':'+os.environ['PATH'],XDG_DATA_HOME=str(temp/'data'),PTM_TEST_URL=f'https://127.0.0.1:{port}/archive',PTM_TEST_CERT=str(cert),PTM_TEST_MARKER=str(marker))
    def run(): return subprocess.run(['bash',str(script),'--check'],env=env,capture_output=True,text=True,timeout=45)
    result=run()
    assert result.returncode==0,(result.stdout,result.stderr)
    assert state['attempts']==3 and marker.read_text()=='--check\n'
    print('PASS: two real TLS EOF failures retried; third attempt verified and forwarded --check.')
    marker.unlink();state.update(attempts=0,failures=100)
    result=run()
    assert result.returncode!=0 and state['attempts']==4 and not marker.exists(),result.stderr
    assert 'installation has not started' in result.stderr
    retained=list((temp/'data/plasma-tray-motion/releases').iterdir())
    assert len(retained)==1
    print('PASS: persistent TLS failure stops after four attempts, cleans download, and never invokes installer.')
    state.update(attempts=0,failures=0,corrupt=True)
    result=run()
    assert result.returncode!=0 and 'SHA-256 verification failed' in result.stderr and not marker.exists()
    assert len(list((temp/'data/plasma-tray-motion/releases').iterdir()))==1
    print('PASS: corrupt response still rejected before installation.')
    state['stop']=True;thread.join(1);listener.close()
