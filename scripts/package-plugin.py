#!/usr/bin/env python3
"""Build an allowlisted desktop plugin ZIP and verify bundled references."""
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST='.codex-plugin/plugin.json'
TOP={'README.md','LICENSE.md','AGENTS.md','PLAN.md','CHANGELOG.md','requirements-discord.txt','requirements-mail.txt'}
DIRS={'.agents','.codex-plugin','skills','hub','docs','scripts','examples','tests','site'}

def build():
    manifest=json.loads((ROOT/MANIFEST).read_text())
    assert manifest['requires_local_executor'] is True
    assert manifest['skills']=='./skills/'
    version=manifest['version']; assert re.fullmatch(r'\d+\.\d+\.\d+',version)
    files=[]
    # Tracked files only: personal or temporary untracked artifacts never enter releases.
    for line in subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines():
        p=Path(line)
        if line not in TOP and p.parts[0] not in DIRS:continue
        assert not (ROOT/p).is_symlink(), 'symlink in package: '+line
        assert not any(x in p.parts for x in ('.runtime','__pycache__','node_modules','.openai'))
        assert not p.name.startswith('.env') or p.name == '.env.example'
        assert not any(x in p.name for x in ('.sqlite','.key','.pem','google-token','google-client'))
        files.append(line)
    assert MANIFEST in files
    for file in files:
        if not file.endswith('.md'):continue
        for link in re.findall(r'\]\(([^)]+)\)',(ROOT/file).read_text()):
            if '://' in link or link.startswith('#'):continue
            target=((ROOT/file).parent/link.split('#')[0]).resolve()
            assert target.is_relative_to(ROOT), f'external reference: {file}'
            assert str(target.relative_to(ROOT)) in files, f'unbundled reference: {file}: {link}'
    out=ROOT/'release';out.mkdir(exist_ok=True)
    archive=out/f'chat-schedule-hub-{version}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(files):z.write(ROOT/file,file)
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/(archive.name+'.sha256')).write_text(checksum+'  '+archive.name+'\n')
    print(json.dumps({'archive':str(archive),'files':len(files),'sha256':checksum}))

if __name__=='__main__':build()
