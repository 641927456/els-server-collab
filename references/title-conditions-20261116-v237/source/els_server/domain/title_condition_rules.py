"""Source-reviewed title predicates. No title is admitted merely by its ID."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import hashlib
import json


@dataclass(frozen=True)
class Objective:
    submission: int
    target: int
    kind: int
    maps: tuple
    npcs: tuple
    condition: dict
    max_seconds: object = None
    weekly: int = 0
    ignore_bonus: bool = False
    force: bool = False


@dataclass(frozen=True)
class Rule:
    mission: int
    title: int
    level: int
    objectives: tuple
    prerequisites: tuple
    account: bool
    unit_type: int
    unit_class: int
    simultaneous: bool


@lru_cache(maxsize=1)
def rules():
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.titles import catalog
    path=Path(__file__).resolve().parents[1]/'data/title_conditions.json'
    raw=path.read_bytes()
    manifest=json.loads(path.with_suffix('.manifest.json').read_bytes())
    if hashlib.sha256(raw).hexdigest()!=manifest['sha256']:
        raise ValueError('Title condition source identity')
    data=json.loads(raw)
    native=catalog()
    routes=route_catalog()
    result=[]
    for row in data['missions']:
        objectives=[]
        for sub in row['objectives']:
            c=sub['condition']
            maps=tuple(dict.fromkeys(routes.entry_identity(d['m_eDungeonID']) for d in c.get('m_vecDungeonList',())))
            objectives.append(Objective(sub['submission'],sub['target'],sub['kind'],maps,
                tuple(c.get('m_eKillNPCID',())),c,c.get('m_iDungeonClearTime'),
                sub.get('weekly',0),sub.get('ignore_bonus',False),sub.get('force',False)))
        title=row['title']
        if title and str(title) not in native['titles']:
            raise ValueError('Title condition reward absent in current client')
        result.append(Rule(row['mission'],title,row['level'],tuple(objectives),tuple(row['prerequisites']),
            row['account'],row['unit_type'],row['unit_class'],any(o.kind==19 for o in objectives)))
    return tuple(result)


def state_count(objective,character,owned):
    """Return a current committed fact, or None for prospective event counters."""
    c=objective.condition
    if objective.kind==13:
        return int(all(t in owned for t in c['m_vecTitleID']))
    if objective.kind==12:
        return int(c['m_iQuestID'] in character.get('title_completed_quests',()))
    if objective.kind==30:
        return int(character['level']>=c['m_iAchieveLevel'])
    return None


def matches(objective,event):
    """An absent measurement never means a zero-hit or zero-revival run."""
    kind=objective.kind
    c=objective.condition
    event_kind=event['kind']
    if kind in (12,13,30):return event_kind=='state'
    if kind==14:return False  # Existing owned-coupon transaction grants the title directly.
    if kind in (2,26):
        return (event_kind==('field_kill' if kind==26 else 'kill')
            and event.get('npc') in objective.npcs
            and (not objective.maps or event.get('dungeon') in objective.maps)
            and (kind!=26 or event.get('field')==c['m_eBattleFieldID']))
    actions={1:'talk',16:'pet_feed',20:'death',21:'socket',23:'enhance',25:'dismantle'}
    if kind in actions:
        if event_kind!=actions[kind]:return False
        if kind==1:return event.get('npc')==c['m_eTalkNPCID']
        if kind==16:return event.get('grade')==c['m_eItemGrade']
        if kind==20:return event.get('reason')==c['m_eDieReason']
        if kind in (21,23):
            return event.get('item_level',-1)>=c['m_iItemLevel'] and (kind!=23 or event.get('success') is True)
        return event.get('quantity')==1 and event.get('item_level',-1)>=c.get('m_iItemLevel',0)
    if event_kind!='clear':return False
    if kind==19:return True  # The containing rule requires every predicate on this same clear.
    if event.get('dungeon') not in objective.maps:return False
    if c.get('m_bShouldWinGame') and event.get('won') is not True:return False
    if kind==8:return True
    if kind in (5,17):
        seconds=event.get('seconds')
        if c.get('m_iDungeonClearTime',0) and (seconds is None or not 0<seconds<=c['m_iDungeonClearTime']):return False
        return kind!=17 or event.get('players')==c['m_iPlayerCount']
    if kind==6:
        rank=event.get('rank')
        return rank is not None and rank>=c['m_eDungeonRank']
    if kind==7:
        targets=c.get('m_setConditionNPCID',())
        if targets:
            hits=event.get('hits_by_npc')
            if hits is None:return False
            received=sum(hits.get(npc,0) for npc in targets)
        else:received=event.get('hits')
        return received is not None and 0<=received<=c['m_iDungeonDamage']
    if kind in (18,31):
        used=event.get('resurrections')
        if used is None:return False
        return used>=c['m_iDieCount'] if kind==18 and c.get('m_bCheckResurrectionStone') else used<=c['m_iDieCount']
    raise ValueError('Unimplemented admitted title predicate')
