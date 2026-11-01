"""Origin-bound macOS Keychain service access; no source/Git credentials."""
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

HELPER = Path(__file__).resolve().parents[1] / '.runtime/site-keychain'

def service_token(origin, helper=HELPER):
    url = urlsplit(origin)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError('invalid_site_origin')
    result = subprocess.run([str(helper), 'get', origin], capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError('site_keychain_unavailable')
    value = result.stdout.decode().strip()
    if not value or len(value) > 16384:
        raise ValueError('invalid_site_credential')
    return value
