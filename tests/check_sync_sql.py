import sqlite3,re,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'site'
db=sqlite3.connect(':memory:')
db.executescript((root/'drizzle/0000_good_puma.sql').read_text())
db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?)',('old','install',1,json.dumps({'events':[{'id':'keep'}],'people':[],'sources':[]}), '2026-01-01'))
db.executescript((root/'drizzle/0001_delta_sync.sql').read_text())
assert db.execute('SELECT id FROM sync_records').fetchone()[0]=='keep'
sql=re.findall(r'db.prepare\(`([^`]+)`\)',(root/'lib/sync-records.ts').read_text())
def apply(owner,seq,name):
 with db:
  db.execute(sql[0],(owner,'i','event','e',json.dumps({'id':'e','title':name}),seq,'now',owner,'i',seq))
  db.execute(sql[1],(owner,'i',seq,name,'now'))
apply('a',2,'new');apply('a',1,'old');apply('a',2,'replay');apply('b',1,'separate')
assert json.loads(db.execute("SELECT payload FROM sync_records WHERE owner='a'").fetchone()[0])['title']=='new'
assert db.execute("SELECT count(*) FROM sync_records").fetchone()[0]==3
print('Migration preservation, stale/repeated batches, owner isolation: PASS')
