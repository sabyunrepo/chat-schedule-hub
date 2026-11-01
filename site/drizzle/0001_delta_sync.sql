CREATE TABLE sync_heads(owner TEXT NOT NULL, installation TEXT NOT NULL, sequence INTEGER NOT NULL, digest TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(owner,installation));
--> statement-breakpoint
CREATE TABLE sync_records(owner TEXT NOT NULL, installation TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, sequence INTEGER NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(owner,installation,kind,id));
--> statement-breakpoint
CREATE INDEX sync_records_owner_kind ON sync_records(owner,kind);
--> statement-breakpoint
INSERT INTO sync_records SELECT s.owner,s.installation,'event',json_extract(j.value,'$.id'),j.value,s.sequence,s.updated FROM snapshots s,json_each(s.payload,'$.events') j;
--> statement-breakpoint
INSERT INTO sync_records SELECT s.owner,s.installation,'person',json_extract(j.value,'$.id'),j.value,s.sequence,s.updated FROM snapshots s,json_each(s.payload,'$.people') j;
--> statement-breakpoint
INSERT INTO sync_records SELECT s.owner,s.installation,'source',json_extract(j.value,'$.id'),j.value,s.sequence,s.updated FROM snapshots s,json_each(s.payload,'$.sources') j;
--> statement-breakpoint
INSERT INTO sync_heads SELECT owner,installation,sequence,'legacy',updated FROM snapshots;
