"""Single bounded collection/materialization cycle, suitable for local scheduling."""
import argparse
import json
import os
from .core import Store
from .update import ROOT, DATABASES, update_lock
from .extraction import extractors, process
from .mail_evidence import link_reminders
from .card_events import materialize
from .delta_sync import deliver, prepare
from .sources.mail_calendar import GoogleReadOnly, NaverReadOnly, secret, private_write
from .sources.calendar_pilot import collect
from .sources.mail_incremental import gmail_collect, naver_collect
from .providers import providers


def extraction_budgets(config):
    """Validate all budgets before any collection or database mutation."""
    fallback=config.get('jobsPerSource',5)
    overrides=config.get('jobsPerSourceByName',{})
    if not isinstance(overrides,dict) or any(name not in DATABASES for name in overrides):
        raise ValueError('invalid per-source extraction budgets')
    for value in [fallback,*overrides.values()]:
        if type(value) is not int or not 1<=value<=50:
            raise ValueError('extraction budget must be an integer in 1..50')
    return {name:overrides.get(name,fallback) for name in DATABASES}


def extract_bounded(store, provider, limit):
    # process has a smaller per-call budget. Never retry failed jobs repeatedly
    # inside a cycle merely to consume the remaining source budget.
    result={'processed':0,'applied':0,'failed':0,'modelCalls':0}
    remaining=limit
    while remaining:
        batch=min(remaining,20)
        current=process(store,provider,batch)
        for key in result: result[key]+=current[key]
        remaining-=batch
        if current['failed'] or current['processed']<batch: break
    return result


def cycle(root=ROOT, site_token=None):
    config=json.loads((root/'pipeline.json').read_text())
    if config.get('externalProcessingAllowed') is not True:raise ValueError('external processing not configured')
    budgets=extraction_budgets(config)
    report={}
    destination=None
    access_attempted=False
    def site_destination():
        nonlocal destination
        if destination is None:
            destination=json.loads((root/'update.json').read_text())['siteOrigin'].rstrip('/')
        return destination
    def access_token():
        nonlocal site_token,access_attempted
        if not site_token and not access_attempted and config.get('siteAccess')=='macos-keychain':
            access_attempted=True
            from .site_access import service_token
            try:site_token=service_token(site_destination())
            except Exception as exc:
                report['siteAccess']={'state':'unavailable','errorType':type(exc).__name__}
        return site_token
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
                item['extraction']=extract_bounded(store,provider,budgets[name]) if config.get('extractionEnabled',True) else {'state':'disabled-awaiting-provider-access','modelCalls':0}
                if name=='kakao':item['cards']=materialize(store)
                if prepare(store,site_destination()) is None:
                    item['sync']={'ok':True,'batches':0,'records':0,'state':'unchanged'}
                elif access_token():
                    item['sync']=deliver(store,site_destination(),secret(root/'site-sync.key'),site_token)
                else:item['sync']={'state':'awaiting_site_access','pendingRetained':True}
            except Exception as exc:report[name]={'errorType':type(exc).__name__}
            finally:store.db.close()
        if config.get('pushEnabled'):
            from .push import cycle as push_cycle
            try:
                if access_token():report['push']=push_cycle(root,site_destination(),site_token)
                else:report['push']={'state':'awaiting_site_access'}
            except Exception as exc:report['push']={'errorType':type(exc).__name__}
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
