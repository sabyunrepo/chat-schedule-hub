"""Match normalized UI rows using unique three-row overlaps; never use AX indices as IDs."""
import json
import uuid
from collections import Counter
from ..core import digest, require, now


class KakaoAnchors:
    def __init__(self, db):
        self.db=db
        db.execute('''CREATE TABLE IF NOT EXISTS kakao_windows(
            target TEXT PRIMARY KEY, window TEXT NOT NULL, updated TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS kakao_anchor_history(
            target TEXT NOT NULL, triple TEXT NOT NULL, keys TEXT NOT NULL,
            PRIMARY KEY(target,triple,keys))''')

    def observe(self, target, rows):
        """Rows must contain actual observed text/date/author only. No raw text persists here.

        First view establishes provisional occurrence IDs. Only unambiguous 3-row overlaps
        on another observation confirm them. New/unmatched rows require another view.
        Changed text cannot identify which old message was edited, so is left unconfirmed.
        """
        require(3<=len(rows)<=500,'need 3..500 observed rows')
        if not any(rows[i] is not None and rows[i+1] is not None and rows[i+2] is not None for i in range(len(rows)-2)):
            return {'messages':[], 'unconfirmed':len(rows), 'matchedRows':0, 'coverageVerified':False, 'editsIdentifiable':False}
        fingerprints=[digest({k:(None if k=='authorDisplayName' else r.get(k)) for k in ('text','sentAt','authorRef','authorDisplayName','contentKind')}) if r is not None else None for r in rows]
        record=self.db.execute('SELECT window FROM kakao_windows WHERE target=?',(target,)).fetchone()
        previous=json.loads(record[0]) if record else []
        old=[r['fingerprint'] for r in previous]
        old_triples=[tuple(old[i:i+3]) for i in range(len(old)-2)]
        new_triples=[tuple(fingerprints[i:i+3]) for i in range(len(fingerprints)-2)]
        old_counts=Counter(old_triples);new_counts=Counter(new_triples)
        positions={triple:i for i,triple in enumerate(old_triples) if old_counts[triple]==1}
        candidates={}
        for j,triple in enumerate(new_triples):
            if None in triple or new_counts[triple]!=1 or triple not in positions:continue
            i=positions[triple]
            for offset in range(3):candidates.setdefault(j+offset,set()).add(i+offset)
        # Both directions must agree; no collapsing repeated identical messages.
        matches={j:next(iter(indices)) for j,indices in candidates.items() if len(indices)==1}
        used=Counter(matches.values())
        matches={j:i for j,i in matches.items() if used[i]==1}
        matched_order=[matches[j] for j in sorted(matches)]
        reordered=matched_order!=sorted(matched_order)
        if reordered:matches={} # reordered/ambiguous page
        keys={j:{previous[i]['key']} for j,i in matches.items()}
        # Revisit confirmed dated windows without inventing new occurrence IDs.
        # Store hashes and keys only, and reject conflicting historical triples.
        if not reordered:
            for j,triple in enumerate(new_triples):
                if None in triple or new_counts[triple]!=1 or not all(r and r.get('sentAt') for r in rows[j:j+3]):continue
                history=self.db.execute('SELECT keys FROM kakao_anchor_history WHERE target=? AND triple=?',
                                        (target,digest(triple))).fetchall()
                for record in history:
                    for offset,key in enumerate(json.loads(record[0])):
                        keys.setdefault(j+offset,set()).add(key)
        resolved={j:next(iter(values)) for j,values in keys.items() if len(values)==1}
        key_counts=Counter(resolved.values())
        resolved={j:key for j,key in resolved.items() if key_counts[key]==1}
        window=[];confirmed=[]
        for i,fp in enumerate(fingerprints):
            key=(resolved.get(i) or str(uuid.uuid4())) if fp is not None else None
            window.append({'fingerprint':fp,'key':key})
            if fp is not None and i in resolved:
                confirmed.append({**rows[i],'occurrenceKey':key,'identityQuality':'verified-anchor'})
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO kakao_windows VALUES(?,?,?)',(target,json.dumps(window),now()))
            for j,triple in enumerate(new_triples):
                if None not in triple and new_counts[triple]==1 and all(k in resolved and rows[k] and rows[k].get('sentAt') for k in range(j,j+3)):
                    self.db.execute('INSERT OR IGNORE INTO kakao_anchor_history VALUES(?,?,?)',
                                    (target,digest(triple),json.dumps([resolved[k] for k in range(j,j+3)])))
        return {'messages':confirmed,'unconfirmed':len(rows)-len(confirmed),'matchedRows':len(resolved),
                'coverageVerified':False,'editsIdentifiable':False}
