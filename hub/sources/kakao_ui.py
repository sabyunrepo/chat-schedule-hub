"""Pure parsing and progress checks for host-supplied full Kakao AX observations.

This module never controls a computer or reads Kakao's private storage.
"""
import re
from datetime import datetime, timezone, timedelta
from ..core import digest, require


def parse_window(state):
    title=re.search(r'^Window: "(.*?)", App:',state)
    require(title is not None,'full AX window required, not a diff')
    table=re.search(r'\n\t\t\d+ 표[^\n]*\n(.*?)(?=\n\t\t\d+ 스크롤 막대|\Z)',state,re.S)
    require(table is not None,'message table not found')
    rows=[]
    for block in re.split(r'\n?\t{3}\d+ row[^\n]*\n',table[1])[1:]:
        # Kakao exposes either Value: 오후 2:51 or an unread count followed by a time line.
        date=re.search(r'Help: (\d{4})\. (\d+)\. (\d+)\., Value: (?:\d+\n)?(오전|오후) (\d+):(\d+)',block)
        sent=None
        if date:
            y,mo,d,amp,h,minute=date.groups()
            sent=datetime(int(y),int(mo),int(d),int(h)%12+(12 if amp=='오후' else 0),int(minute),tzinfo=timezone(timedelta(hours=9))).isoformat()
        text=[]
        include_continuation=False
        for raw in block.splitlines():
            element=re.match(r'^\t+\d+ (.*)$',raw)
            if not element:
                if include_continuation:text.append(raw.rstrip())
                continue
            line=element[1].strip()
            include_continuation=False
            if not line or re.match(r'^(셀|버튼|이미지|link |스크롤|(?:텍스트|text) Help:)',line):continue
            line=re.sub(r'^(텍스트 엔트리 영역|텍스트|text) ','',line)
            if line.isdigit():continue # unread count, never message identity
            include_continuation=True
            text.append(line)
        if text:
            rows.append({'text':'\n'.join(text),'sentAt':sent,'authorRef':None})
    bar=re.search(r'스크롤 막대 \(settable, float\) ([\d.]+)',state)
    return {'title':title[1],'rows':rows,'scrollPosition':float(bar[1]) if bar else None}


def progress(before,after):
    """Scrolling is observation progress, never a persistence checkpoint."""
    a=parse_window(before);b=parse_window(after)
    if a['title']!=b['title']:return {'state':'target-changed','advanceCheckpoint':False}
    # Ignore AX indices and unread-count churn. Position alone does not prove content progress.
    changed=digest(a['rows'])!=digest(b['rows'])
    return {'state':'content-changed' if changed else 'no-content-progress',
            'beforeRows':len(a['rows']),'afterRows':len(b['rows']),
            'positionChanged':a['scrollPosition']!=b['scrollPosition'],'advanceCheckpoint':False}
