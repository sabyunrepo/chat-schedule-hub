"""Install the local read-only collector as a per-user macOS LaunchAgent."""
import os
import plistlib
import subprocess
from pathlib import Path

repo=Path(__file__).resolve().parent.parent
root=Path.home()/'Library/Application Support/ChatScheduleHub'
python=repo/'.runtime/discord-venv/bin/python'
if not python.is_file():raise SystemExit('Create .runtime/discord-venv and install requirements-discord.txt first')
label='com.chatschedulehub.discord'
path=Path.home()/'Library/LaunchAgents'/f'{label}.plist'
path.parent.mkdir(parents=True,exist_ok=True)
content={'Label':label,'ProgramArguments':[str(python),'-m','hub.sources.discord_watch','--config',str(root/'discord-bot.json')],
 'WorkingDirectory':str(repo),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,
 'EnvironmentVariables':{'PYTHONUNBUFFERED':'1'},'StandardOutPath':str(root/'discord-worker.log'),
 'StandardErrorPath':str(root/'discord-worker-error.log')}
if path.exists():
 previous=plistlib.loads(path.read_bytes())
 if previous.get('Label')!=label or previous.get('WorkingDirectory')!=str(repo):
  raise SystemExit('Existing service belongs to another installation; refusing replacement')
 subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],capture_output=True)
path.write_bytes(plistlib.dumps(content));path.chmod(0o600)
subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(path)],check=True)
print('Discord LaunchAgent installed. Stop: launchctl bootout gui/$(id -u)/com.chatschedulehub.discord')
