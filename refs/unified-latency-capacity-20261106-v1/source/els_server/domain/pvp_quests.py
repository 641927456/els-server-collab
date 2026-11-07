"""Exact seven current Camilla tasks; original rewards remain untouched.

This leaf is not an outcome producer and never accepts player counters. The
settlement writer uses only the original admitted room's sealed result.
"""
import functools
import hashlib
import json
from pathlib import Path

QUESTS = frozenset((32000,32010,32020,32030,32040,32070,32090))

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/pvp_seven.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'bb1d8ff4108dda77347351aff8a57421fb4cd277bc15d6f9296a1e639ddaffeb':
        raise ValueError('PvP seven exact source changed')
    data=json.loads(raw)
    if {int(q) for q in data['quests']} != QUESTS:
        raise ValueError('PvP seven source scope')
    return data

def target(sub):
    exact=catalog()['subquests'].get(str(sub.get('m_iID')))
    if exact is None or sub != exact:
        raise ValueError('Unsupported PvP original objective')
    kind=sub['m_eClearType'];c=sub['m_ClearCondition']
    return c['m_iPVPPlay'] if kind==9 else c['m_iPVPWin'] if kind==10 else 1

def advance(db, uid, level, profile, win, *, played=True):
    """Called in the same writer as both profiles/XP/immutable result receipt.

    Only already accepted exact tasks progress. Never grants rank, autoaccepts,
    claims rewards, backfills past matches, or opens unrelated type10 tasks.
    """
    if not db.in_transaction or type(win) is not bool:
        raise ValueError('PvP quest original result transaction')
    profile.checked()
    if not played:return []
    if level < 75:return []
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return []
    changed=[]
    for q,at,g,raw in db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? ORDER BY quest',(uid,)):
        if q not in QUESTS:continue
        quest=catalog()['quests'][str(q)]
        ids={v for k,v in quest['m_vecSubQuest'].items() if k!='0' and v is not None}
        counts={int(k):v for k,v in json.loads(raw).items()}
        if set(counts)!=ids:raise ValueError('PvP saved objective identity')
        updated=dict(counts)
        for sid in ids:
            sub=catalog()['subquests'][str(sid)];limit=target(sub);value=counts[sid]
            if type(value) is not int or not 0<=value<=limit:
                raise ValueError('PvP saved objective count')
            kind=sub['m_eClearType']
            # Rank progress is evidence of actual resulting rank, never an
            # instruction to award SSS. A previously achieved flag is retained.
            increment=1 if kind==9 else int(win) if kind==10 else int(profile.rank>=sub['m_ClearCondition']['m_ePvpRank'])
            updated[sid]=min(limit,value+increment)
        if updated!=counts:
            db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=? AND generation=?',(json.dumps(updated,sort_keys=True),uid,q,g))
            changed.append(dict(id=q,owner=uid,accepted_at=at,generation=g,objectives=updated))
    return changed
