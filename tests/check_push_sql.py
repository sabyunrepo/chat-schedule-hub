import sqlite3,pathlib,re
root=pathlib.Path(__file__).resolve().parents[1]/'site'
db=sqlite3.connect(':memory:')
for p in sorted((root/'drizzle').glob('*.sql')):db.executescript(p.read_text())
s=(root/'app/api/push/dispatch/route.ts').read_text();sql=re.search(r'prepare\(`(INSERT INTO push_deliveries.*?)`\)',s,re.S)[1]
def claim(owner,lease,now):
 db.execute(sql,(owner,'sub','item',lease,now+300000,now));return db.execute('SELECT changes()').fetchone()[0]
assert claim('u','a',0)==1
assert claim('u','b',1)==0
assert claim('v','c',1)==1
assert claim('u','d',300001)==1
# Stale acknowledgments cannot mark a newer lease as sent.
assert db.execute("UPDATE push_deliveries SET state='sent' WHERE owner='u' AND lease='a'").rowcount==0
assert claim('u','e',600002)==1
assert claim('u','f',900003)==0
print('push lease: concurrent claim, owner isolation, stale ack, retry cap passed')
