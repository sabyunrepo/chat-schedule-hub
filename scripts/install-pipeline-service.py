"""Install a bounded 15-minute local pipeline, retaining pending site delivery."""
import os
from pathlib import Path
import plistlib
import subprocess

repo=Path(__file__).resolve().parents[1]
root=Path.home()/'Library/Application Support/ChatScheduleHub'
python=repo/'.runtime/pipeline-venv/bin/python'
if not python.is_file() or not (root/'pipeline.json').is_file():raise SystemExit('Configure pipeline.json and install requirements-mail.txt in .runtime/pipeline-venv first')
label='com.chatschedulehub.pipeline'
path=Path.home()/'Library/LaunchAgents'/f'{label}.plist'
if path.exists():
 previous=plistlib.loads(path.read_bytes())
 if previous.get('WorkingDirectory')!=str(repo):raise SystemExit('Service belongs to another installation')
 subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],capture_output=True)
path.parent.mkdir(parents=True,exist_ok=True)
path.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':[str(python),'-m','hub.pipeline'],'WorkingDirectory':str(repo),'RunAtLoad':False,'StartInterval':900,'ProcessType':'Background','StandardOutPath':str(root/'pipeline-worker.log'),'StandardErrorPath':str(root/'pipeline-worker-error.log')}));path.chmod(0o600)
subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(path)],check=True)
print('Pipeline scheduled every 15 minutes; site delivery requires a live Sites access token.')
