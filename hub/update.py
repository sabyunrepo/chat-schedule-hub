"""Bounded local entry point for Dot/desktop skills. No credentials in argv."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys

from .core import Store
from .delta_sync import deliver
from .card_events import materialize
from .mail_evidence import link_reminders

ROOT = Path.home() / 'Library/Application Support/ChatScheduleHub'
DATABASES = {'discord': 'discord-live.sqlite', 'kakao': 'kakao-live.sqlite',
             'mail-calendar': 'mail-calendar.sqlite'}


@contextmanager
def update_lock(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(root / 'update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('update_already_running') from None
        yield
    finally:
        os.close(fd)


def status(root=ROOT):
    result = {}
    for name, filename in DATABASES.items():
        path = root / filename
        if not path.is_file():
            result[name] = {'available': False}
            continue
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            result[name] = dict(available=True,
                events=db.execute('SELECT count(*) FROM events').fetchone()[0],
                pendingJobs=db.execute("SELECT count(*) FROM jobs WHERE state IN ('pending','failed')").fetchone()[0],
                unsentVersions=db.execute('SELECT count(*) FROM outbox WHERE sent=0').fetchone()[0])
        finally:
            db.close()
    return {'sources': result, 'collectionPerformed': False}


def run(action, sources, root=ROOT, site_token=None):
    if action not in ('materialize', 'sync'):
        raise ValueError('unsupported_action')
    if not sources or any(s not in DATABASES for s in sources):
        raise ValueError('unsupported_source')
    paths = [(s, root / DATABASES[s]) for s in dict.fromkeys(sources)]
    if any(not p.is_file() or p.is_symlink() for _, p in paths):
        raise ValueError('source_database_missing_or_symlink')
    origin = token = None
    if action == 'sync':
        # Destination is owner-configured, never taken from collected content.
        config = json.loads((root / 'update.json').read_text())
        origin = config['siteOrigin']
        key = root / 'site-sync.key'
        if key.is_symlink() or key.stat().st_mode & 0o077:
            raise ValueError('pairing_key_permissions')
        token = key.read_text().strip()
        if not site_token:
            raise ValueError('site_access_token_required')
    result = {}
    with update_lock(root):
        for name, path in paths:
            store = Store(path)
            try:
                if action == 'sync':
                    result[name] = deliver(store, origin, token, site_token)
                elif name == 'kakao':
                    result[name] = materialize(store)
                elif name == 'mail-calendar':
                    result[name] = link_reminders(store)
                else:
                    result[name] = {'applied': 0, 'freeTextExtractionComplete': False}
            finally:
                store.db.close()
    return {'action': action, 'sources': result, 'collectionPerformed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'materialize', 'sync'])
    parser.add_argument('--source', action='append', choices=list(DATABASES))
    args = parser.parse_args()
    if args.action == 'status':
        result = status()
    else:
        # stdin is transient; never persist the Sites access token.
        token = json.load(sys.stdin).get('siteAccessToken') if args.action == 'sync' else None
        result = run(args.action, args.source or list(DATABASES), site_token=token)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Third-party exceptions may contain request headers or personal content.
        print(json.dumps({'ok': False, 'errorType': type(error).__name__,
                          'message': '업데이트 실패. 저장된 미전송 변경분은 유지됩니다.'}), file=sys.stderr)
        sys.exit(1)
