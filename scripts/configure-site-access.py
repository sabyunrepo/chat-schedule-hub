"""Store a Sites service credential in macOS Keychain without argv/files."""
import getpass
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hub.update import ROOT
from hub.site_access import HELPER,service_token

origin=json.loads((ROOT/'update.json').read_text())['siteOrigin']
if not HELPER.is_file():raise SystemExit('Build scripts/site-keychain.swift into .runtime/site-keychain first')
value=getpass.getpass('Site service credential (hidden): ')
result=subprocess.run([str(HELPER),'set',origin],input=value+'\n',text=True,capture_output=True,timeout=30)
if result.returncode or service_token(origin)!=value:raise SystemExit('Keychain setup failed; secret output suppressed')
print('Site service credential saved and verified in Keychain.')
