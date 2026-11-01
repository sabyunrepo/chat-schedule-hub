"""JSON stdin commands for a desktop Codex skill; secrets never go in arguments."""
import argparse, json, os, sys
from pathlib import Path
from .core import Store, REGISTRY
from .providers import providers

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['sources','register','begin','ingest','pending','decide','person','apply','snapshot','sync']); args=parser.parse_args()
    if args.command=='sources': print(json.dumps(list(REGISTRY.adapters.values()),ensure_ascii=False)); return
    path=os.environ.get('HUB_DB',str(Path.home()/'Library/Application Support/ChatScheduleHub/hub.sqlite'))
    store=Store(path); data=json.load(sys.stdin) if args.command not in ['pending','snapshot'] else {}
    if args.command=='register': store.register_target(**data); result={'registered':data['target']}
    elif args.command=='begin': result=store.begin(data['target'])
    elif args.command=='ingest': result=store.ingest(data)
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
