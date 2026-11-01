"""Bounded official REST pilot. Gateway/background collection is not enabled yet."""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta, timezone
from ..core import require, now


class DiscordAPIError(RuntimeError):
    pass


class DiscordBot:
    def __init__(self, config, opener=None):
        self.config = config
        self.guilds = frozenset(str(x) for x in config['guildAllowlist'])
        require(bool(self.guilds) and all(x.isdigit() for x in self.guilds), 'invalid guild allowlist')
        path = Path(config['tokenFile'])
        require(not path.is_symlink() and not path.stat().st_mode & 0o077, 'token must be owner-only')
        self._token = path.read_text().strip()
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def get(self, route):
        require(route.startswith('/') and not any(x in route for x in ['://', '..', '#']), 'invalid API route')
        for attempt in range(3):
            req = urllib.request.Request('https://discord.com/api/v10' + route, headers={
                'Authorization': 'Bot ' + self._token,
                'User-Agent': 'DiscordBot (https://github.com/sabyunrepo/chat-schedule-hub, 0.1)'})
            try:
                with self.opener.open(req, timeout=20) as response: return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code == 429 and attempt < 2:
                    try: delay = float(json.load(error).get('retry_after', 1))
                    except (ValueError, TypeError): delay = 1
                    if not 0 <= delay <= 15: raise DiscordAPIError('Discord rate limit: retry later') from None
                    time.sleep(delay)
                    continue
                raise DiscordAPIError('Discord HTTP ' + str(error.code)) from None
            except urllib.error.URLError:
                raise DiscordAPIError('Discord connection failed') from None
        raise DiscordAPIError('Discord retry budget exhausted')

    def verify(self):
        me = self.get('/users/@me')
        require(me.get('bot') is True and me['id'] == self.config['applicationId'], 'wrong bot identity')
        return me['id']

    def inventory(self):
        self.verify()
        result = []
        for guild in sorted(self.guilds):
            channels = self.get('/guilds/' + guild + '/channels')
            threads = self.get('/guilds/' + guild + '/threads/active')['threads']
            result.append({'guildId': guild, 'channels': channels, 'activeThreads': threads,
                           'archivedThreadsEnumerated': False})
        return result

    def page(self, guild, channel, *, before=None, limit=16):
        require(str(guild) in self.guilds, 'guild outside allowlist')
        require(str(channel).isdigit() and (before is None or str(before).isdigit()), 'invalid cursor')
        require(1 <= limit <= 32, 'pilot page limit is 32')
        meta = self.get('/channels/' + str(channel))
        require(str(meta.get('guild_id')) == str(guild), 'channel outside selected guild')
        suffix = '?limit=' + str(limit) + ('&before=' + str(before) if before else '')
        messages = self.get('/channels/' + str(channel) + '/messages' + suffix)
        require(all(str(m.get('channel_id')) == str(channel) for m in messages), 'wrong message channel')
        return meta, messages


def target_id(connection, guild, channel):
    return 'discord-bot:' + ':'.join(map(str, (connection, guild, channel)))


def normalize(message, connection, guild, channel, *, thread=False):
    require(str(message.get('channel_id')) == str(channel), 'wrong message channel')
    require(message.get('id') and message.get('timestamp') and 'content' in message, 'partial message requires refetch')
    ref = message.get('message_reference') or {}
    require(not ref.get('guild_id') or str(ref['guild_id']) == str(guild), 'cross-guild reference unsupported')
    author = message.get('author') or {}
    attachments = [{'id': a['id'], 'filename': a.get('filename'), 'size': a.get('size'),
                    'contentType': a.get('content_type'), 'status': 'metadata-only'}
                   for a in message.get('attachments', [])]
    return {'originId': str(message['id']), 'identityQuality': 'stable',
            'authorRef': str(author['id']) if author.get('id') else None,
            'authorDisplayName': author.get('global_name') or author.get('username'),
            'text': message['content'], 'sentAt': message['timestamp'], 'observedAt': now(),
            'editedAt': message.get('edited_timestamp'), 'observationKind': 'observed',
            'timestampPrecision': 'exact', 'provenance': 'official-api',
            'attachments': attachments,
            'replyToRef': {'targetId': target_id(connection, guild, ref.get('channel_id', channel)),
                           'identity': str(ref['message_id'])} if ref.get('message_id') else None,
            'threadRef': str(channel) if thread else None,
            'sourceLocator': f'https://discord.com/channels/{guild}/{channel}/{message["id"]}'}


def pilot(store, api, guild, channel, provider, *, limit=16, repeat=False):
    """One bounded page, never claims 30-day coverage. Retains only selected content."""
    import uuid
    from ..selection import select_ingest
    api.verify()
    started = time.perf_counter()
    meta, raw = api.page(guild, channel, limit=limit)
    fetch_ms = round((time.perf_counter() - started) * 1000, 2)
    upper = datetime.now(timezone.utc)
    lower = upper - timedelta(days=30)
    connection = api.config['applicationId']
    target = target_id(connection, guild, channel)
    messages = [normalize(m, connection, guild, channel, thread=meta['type'] in (10,11,12))
                for m in raw if lower <= datetime.fromisoformat(m['timestamp']) <= upper]
    store.register_target(target, 'discord-bot', connection, meta.get('name', 'Discord'),
                          {'since': lower.isoformat(), 'until': upper.isoformat()})
    run = store.begin(target)
    batch = {'schemaVersion': 1, 'batchId': str(uuid.uuid4()), 'runId': run['id'],
             'targetId': target, 'verifiedTarget': True, 'externalProcessingAllowed': True,
             'messages': messages, 'stopReason': 'budget-exhausted', 'coverageVerified': False,
             'cursor': {'kind': 'bounded-pilot', 'before': raw[-1]['id'] if raw else None}}
    result = select_ingest(store, batch, provider)
    report = {'fetchMs': fetch_ms, 'fetched': len(raw), 'within30Days': len(messages), 'result': result,
              'uninterpretedAttachmentCount': sum(len(m['attachments']) for m in messages),
              'coverageComplete': False}
    if repeat:
        batch['batchId'] = str(uuid.uuid4())
        report['repeat'] = select_ingest(store, batch, provider)
    return report


def main():
    import argparse
    import os
    from ..core import Store
    from ..providers import providers
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['probe', 'pilot'])
    parser.add_argument('--config', type=Path, default=Path.home()/'Library/Application Support/ChatScheduleHub/discord-bot.json')
    parser.add_argument('--guild'); parser.add_argument('--channel')
    parser.add_argument('--limit', type=int, default=16)
    parser.add_argument('--allow-external-processing', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    api = DiscordBot(config)
    if args.command == 'probe':
        result = [{'guildId': g['guildId'], 'channelCount': len(g['channels']),
                   'activeThreadCount': len(g['activeThreads']), 'archivedThreadsEnumerated': False}
                  for g in api.inventory()]
    else:
        require(args.allow_external_processing, 'external processing must be explicitly enabled')
        require(args.guild and args.channel, 'explicit pilot guild and channel required')
        dbpath = Path(os.environ.get('HUB_DB', str(args.config.parent/'discord-bot-pilot.sqlite')))
        store = Store(dbpath); dbpath.chmod(0o600)
        result = pilot(store, api, args.guild, args.channel, providers.create('openai-decisions'), limit=args.limit, repeat=True)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except (DiscordAPIError, ValueError, OSError) as error:
        # No network response body or credential-bearing request is printed.
        import sys
        print(json.dumps({'error': str(error) if isinstance(error, (DiscordAPIError, ValueError)) else 'Local configuration unavailable'}), file=sys.stderr)
        sys.exit(1)
