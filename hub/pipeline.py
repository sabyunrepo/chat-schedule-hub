"""Single bounded collection/materialization cycle, suitable for local scheduling."""
import argparse
import json
import os
from .core import Store
from .update import ROOT, DATABASES, update_lock
from .extraction import extractors, process
from .mail_evidence import link_reminders
from .card_events import materialize
from .delta_sync import deliver
from .sources.mail_calendar import GoogleReadOnly, NaverReadOnly, secret, private_write
from .sources.calendar_pilot import collect
from .sources.mail_incremental import gmail_collect, naver_collect
from .providers import providers


def cycle(root=ROOT, site_token=None):
    config=json.loads((root/'pipeline.json').read_text())
    if config.get('externalProcessingAllowed') is not True:raise ValueError('external processing not configured')
    report={}
    with update_lock(root):
        provider=extractors.create(config.get('extractionProvider','openai-responses'),model=config.get('extractionModel'))
        api=None
        for name in config['sources']:
            if name not in DATABASES:raise ValueError('source not allowed')
            path=root/DATABASES[name]
            if not path.is_file() or path.is_symlink():raise ValueError('missing database')
            store=Store(path)
            try:
                item={};report[name]=item
                if name=='mail-calendar' and config.get('calendars'):
                    api=GoogleReadOnly(root/'google-token.json');item['calendars']=[]
                    for calendar in config['calendars']:
                        try:item['calendars'].append(collect(store,api,calendar['id'],calendar.get('kind','personal'),250,20,calendar.get('associateMe',False)))
                        except Exception as exc:item['calendars'].append({'errorType':type(exc).__name__})
                if name=='mail-calendar' and config.get('gmail'):
                    try:
                        api=api or GoogleReadOnly(root/'google-token.json')
                        item['gmail']=gmail_collect(store,api,providers.create('openai-decisions'),config.get('mailPageSize',5))
                    except Exception as exc:item['gmail']={'errorType':type(exc).__name__}
                if name=='mail-calendar' and config.get('naverAccount'):
                    naver=None
                    try:
                        naver=NaverReadOnly(config['naverAccount'],root/'naver-app.key')
                        item['naver']=naver_collect(store,naver,providers.create('openai-decisions'),config.get('mailPageSize',5))
                    except Exception as exc:item['naver']={'errorType':type(exc).__name__}
                    finally:
                        if naver:naver.close()
                if name=='mail-calendar':item['mailLinks']=link_reminders(store)
                item['extraction']=process(store,provider,config.get('jobsPerSource',5)) if config.get('extractionEnabled',True) else {'state':'disabled-awaiting-provider-access','modelCalls':0}
                if name=='kakao':item['cards']=materialize(store)
                if site_token:
                    destination=json.loads((root/'update.json').read_text())['siteOrigin']
                    item['sync']=deliver(store,destination,secret(root/'site-sync.key'),site_token)
                else:item['sync']={'state':'awaiting_site_access','pendingRetained':True}
            except Exception as exc:report[name]={'errorType':type(exc).__name__}
            finally:store.db.close()
    private_write(root/'pipeline-report.json',json.dumps(report,ensure_ascii=False))
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--site-token-stdin',action='store_true');args=p.parse_args()
    token=None
    if args.site_token_stdin:
        import sys
        token=json.load(sys.stdin).get('siteAccessToken')
    print(json.dumps(cycle(site_token=token),ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'errorType':type(exc).__name__,'ok':False}));raise SystemExit(1)
