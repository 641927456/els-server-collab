"""Current native weekly missions and season pass definitions."""
import functools, hashlib, json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CN=timezone(timedelta(hours=8))
PASS_MIN_LEVEL=10

@functools.lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).resolve().parents[1]/'data/periodic_activities.json'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='1f4efa9f7eb57ba44461ac2c2f7d13fa1e65e27818104d17389c112ccc035c85':
        raise ValueError('Periodic activities source identity')
    return json.loads(raw)

def weekly(qid):return qid in catalog()['weekly_ids']
def pass_task(qid):return qid in catalog()['pass_ids']
def ordinary_weekly(qid):return qid in catalog()['ordinary_weekly_ids']
def contains(qid):return weekly(qid)or pass_task(qid)or ordinary_weekly(qid)
def definition(qid):return catalog()['quests'][str(qid)]
def account_scoped(qid):return bool(definition(qid).get('m_bIsAccount'))

def period(now,repeat):
    if type(now)is not int or now<=0:raise ValueError('Periodic quest clock')
    day=int((now-2*3600)//86400)
    if repeat==1:return (day*86400+2*3600)
    if repeat==3:
        # Unix epoch was Thursday; CN Wednesday10 starts one day earlier.
        return ((day-6)//7*7+6)*86400+2*3600
    if repeat==6:
        # Saved season tasks remain classifiable after their season closes.
        starts=[int(datetime.fromisoformat(start).replace(tzinfo=CN).timestamp())
                for number,start,end,enabled in catalog()['periods'] if enabled]
        return max((start for start in starts if start<=now),default=0)
    raise ValueError('Unsupported periodic quest schedule')

def active_season(now):
    moment=datetime.fromtimestamp(now,CN)
    rows=[]
    for number,start,end,enabled in catalog()['periods']:
        begin=datetime.fromisoformat(start).replace(tzinfo=CN)
        finish=datetime.fromisoformat(end).replace(tzinfo=CN)
        if enabled and begin<=moment<finish:rows.append((int(begin.timestamp()),int(finish.timestamp()),number))
    if len(rows)>1:raise ValueError('Overlapping current season passes')
    return rows[0]if rows else None

def visible(qid,at,now,*,active):
    if not contains(qid):return True
    q=definition(qid)
    if weekly(qid)and active:return True
    if pass_task(qid)and active_season(now)is None:return False
    return period(at,q['m_eRepeatType'])==period(now,q['m_eRepeatType'])

def target(sub):
    kind=sub['m_eClearType'];condition=sub['m_ClearCondition']
    if kind in(87,88,89,102):return condition['m_iClearCount']
    if kind in(1,24):return 1
    if kind in(8,32):return condition['m_iDungeonClearCount']
    raise ValueError('Unsupported current pass objective')

@functools.lru_cache(maxsize=1)
def pass_objectives():
    return frozenset(sid for qid in catalog()['pass_ids']
                     for sid in definition(qid)['m_vecSubQuest'].values()if sid)

def pass_objective(sub):return sub['m_iID']in pass_objectives()

def eligible(character,q,now,tier=1):
    if weekly(q['m_iID']) and character['level']<99:raise ValueError('Weekly missions require level99')
    if pass_task(q['m_iID']):
        if character['level']<q['m_iPlayLevel']:raise ValueError('Pass quest level requirement')
        if active_season(now)is None:raise ValueError('Pass season is closed')
        if 'SPT_CASH'in q.get('FLAGS','') and tier!=2:raise ValueError('Premium pass entitlement required')

