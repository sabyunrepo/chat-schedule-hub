"""JSON stdin commands for a desktop Codex skill; secrets never go in arguments."""
import argparse, json, os, sys
from pathlib import Path
from .core import Store, REGISTRY
from .providers import providers

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['sources','register','begin','ingest','select-ingest','kakao-observe','kakao-reviewed','kakao-scan-start','kakao-scan-step','kakao-scan-status','pending','decide','person','apply','snapshot','sync']); args=parser.parse_args()
    if args.command=='sources': print(json.dumps(list(REGISTRY.adapters.values()),ensure_ascii=False)); return
    path=os.environ.get('HUB_DB',str(Path.home()/'Library/Application Support/ChatScheduleHub/hub.sqlite'))
    store=Store(path); data=json.load(sys.stdin) if args.command not in ['pending','snapshot'] else {}
    if args.command in ('kakao-scan-start','kakao-scan-status'):
        from .sources.kakao_incremental import KakaoScan
        scan=KakaoScan(store)
        result=scan.status(data['target']) if args.command=='kakao-scan-status' else scan.start(**data)
    elif args.command=='kakao-observe':
        from .sources.kakao_ui import parse_window
        from .sources.kakao_collection import collect, eligibility
        if data.get('externalProcessingAllowed') is not True: raise ValueError('External processing must be enabled')
        state=eligibility(data.get('quiet'),data.get('latest'),data['since'])
        if state!='eligible': result={'state':state,'apiCalls':0}
        else:
            windows=[parse_window(x) for x in data['observations']]
            if len(windows)!=2 or any(x['title']!=data['label'] for x in windows): raise ValueError('observed room mismatch')
            result=collect(store,data['target'],data['label'],[x['rows'] for x in windows],data['latest'],data['quiet'],data['since'],data['until'],providers.create(data.get('provider','openai-decisions')))
    elif args.command in ('kakao-reviewed','kakao-scan-step'):
        # The host supplies only locally reviewed, permitted rows and None gaps.
        # Raw AX observations never enter the CLI, database, or logs.
        from .sources.kakao_collection import collect
        if data.get('externalProcessingAllowed') is not True: raise ValueError('External processing must be enabled')
        views=data.get('observations')
        if not isinstance(views,list) or len(views)!=2: raise ValueError('two independent observations required')
        for view in views:
            if not isinstance(view,list) or not 3<=len(view)<=500: raise ValueError('invalid observation')
            for row in view:
                if row is not None and (not isinstance(row,dict) or set(row)-{'text','sentAt','authorRef','authorDisplayName','reviewedSchedule'}):
                    raise ValueError('invalid reviewed row')
        if args.command=='kakao-scan-step':
            from .sources.kakao_incremental import KakaoScan
            result=KakaoScan(store).step(data['target'],data['label'],views,providers.create(data.get('provider','openai-decisions')),
                quiet=data['quiet'],latest=data['latest'],at_latest=data.get('atLatest') is True,
                source_end=data.get('sourceEnd') is True,range_end=data.get('rangeEnd') is True,cancelled=data.get('cancelled') is True)
        else:
            result=collect(store,data['target'],data['label'],views,data['latest'],data['quiet'],data['since'],data['until'],providers.create(data.get('provider','openai-decisions')))
    elif args.command=='register': store.register_target(**data); result={'registered':data['target']}
    elif args.command=='begin': result=store.begin(data['target'],restart=data.get('restart') is True)
    elif args.command=='ingest': result=store.ingest(data)
    elif args.command=='select-ingest':
        from .selection import select_ingest
        result=select_ingest(store,data,providers.create(data.get('provider','openai-decisions')),data.get('context',''))
    elif args.command=='pending': result=store.pending()
    elif args.command=='snapshot': result=store.snapshot()
    elif args.command=='person':
        with store.db: store.db.execute('INSERT INTO people VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(data['id'],json.dumps(data,ensure_ascii=False)))
        result={'saved':data['id']}
    elif args.command=='apply': result=store.apply_event(data)
    elif args.command=='decide':
        # Caller selects context and confirms external processing in the collection setup.
        if data.get('externalProcessingAllowed') is not True: raise ValueError('External processing must be enabled for this scope')
        ids=set(data['jobIds']); jobs=[j for j in store.pending(100) if j['id'] in ids]
        if len(jobs)!=len(ids): raise ValueError('Unknown or already completed job')
        provider=providers.create(data.get('provider','openai-decisions'))
        result=provider.decide([j['message'] for j in jobs],data.get('context',''))
        with store.db:
            for job in jobs: store.db.execute("UPDATE jobs SET state='classified',result=?,error=NULL WHERE id=?",(json.dumps(result),job['id']))
    elif args.command=='sync':
        from .sync import sync
        result=sync(store,data)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr); sys.exit(1)
