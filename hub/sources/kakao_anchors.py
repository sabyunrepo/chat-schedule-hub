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

    def observe(self, target, rows):
        """Rows must contain actual observed text/date/author only. No raw text persists here.

        First view establishes provisional occurrence IDs. Only unambiguous 3-row overlaps
        on another observation confirm them. New/unmatched rows require another view.
        Changed text cannot identify which old message was edited, so is left unconfirmed.
        """
        require(3<=len(rows)<=500,'need 3..500 observed rows')
        fingerprints=[digest({k:r.get(k) for k in ('text','sentAt','authorRef','authorDisplayName','contentKind')}) for r in rows]
        record=self.db.execute('SELECT window FROM kakao_windows WHERE target=?',(target,)).fetchone()
        previous=json.loads(record[0]) if record else []
        old=[r['fingerprint'] for r in previous]
        old_triples=[tuple(old[i:i+3]) for i in range(len(old)-2)]
        new_triples=[tuple(fingerprints[i:i+3]) for i in range(len(fingerprints)-2)]
        old_counts=Counter(old_triples);new_counts=Counter(new_triples)
        positions={triple:i for i,triple in enumerate(old_triples) if old_counts[triple]==1}
        candidates={}
        for j,triple in enumerate(new_triples):
            if new_counts[triple]!=1 or triple not in positions:continue
            i=positions[triple]
            for offset in range(3):candidates.setdefault(j+offset,set()).add(i+offset)
        # Both directions must agree; no collapsing repeated identical messages.
        matches={j:next(iter(indices)) for j,indices in candidates.items() if len(indices)==1}
        used=Counter(matches.values())
        matches={j:i for j,i in matches.items() if used[i]==1}
        matched_order=[matches[j] for j in sorted(matches)]
        if matched_order!=sorted(matched_order):matches={} # reordered/ambiguous page
        window=[];confirmed=[]
        for i,fp in enumerate(fingerprints):
            key=previous[matches[i]]['key'] if i in matches else str(uuid.uuid4())
            window.append({'fingerprint':fp,'key':key})
            if i in matches:
                confirmed.append({**rows[i],'occurrenceKey':key,'identityQuality':'verified-anchor'})
        with self.db:self.db.execute('INSERT OR REPLACE INTO kakao_windows VALUES(?,?,?)',(target,json.dumps(window),now()))
        return {'messages':confirmed,'unconfirmed':len(rows)-len(confirmed),'matchedRows':len(matches),
                'coverageVerified':False,'editsIdentifiable':False}
