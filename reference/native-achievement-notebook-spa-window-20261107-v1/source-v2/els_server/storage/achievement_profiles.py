"""Recover attained levels and owned collections from existing server authorities."""
import hashlib,json
from els_server.domain.achievement_catalog import catalog
from els_server.storage import achievements as state
from els_server.storage import profession_state,resonance_state
from els_server.storage.achievement_collections import counts as collection_counts
from els_server.storage.achievement_history import counts as history_counts,couple_duration

CONDITION_TYPES=frozenset((2,4,5,6,7,10,15,16,18,19,20,23,24,25,26,27,28,29,30,32,34,35,36,37,38,39,42,43,44,45,50,51,52,53,56,57,58,60,61,62,63,66,67,68))


def reconcile(db,account,owner,now,*,condition_types=CONDITION_TYPES):
    """Caller owns the authenticated character transaction and response encoding.

    This never accepts client counters, grants profile XP or constructs an
    alternate progression authority. Historical account attainment is retained.
    """
    if not db.in_transaction:raise ValueError('Achievement profile reconciliation requires transaction')
    levels={}
    if 6 in condition_types and profession_state.exists(db):
        levels=dict(db.execute('SELECT p.profession,MAX(p.level)FROM character_professions p '
            'JOIN character_owners o ON o.uid=p.uid WHERE o.account_id=?GROUP BY p.profession',(account,)))
    resonance=resonance_state.snapshot(db,owner,account)if 15 in condition_types else None
    collections=collection_counts(db,account,owner,now,condition_types)
    history=history_counts(db,account,condition_types)
    duration=couple_duration(db,account,now)if 20 in condition_types else None
    couple_due=None
    old={}
    if state.exists(db):
        old={(a,c):(v,bool(done))for a,c,v,done in db.execute(
            'SELECT achievement,condition,value,complete FROM native_achievement_progress WHERE account_id=?',(account,))}
    updates=[]
    for identity,definition in sorted(catalog().items()):
        for condition in definition['conditions']:
            kind=condition['type'];parameters=condition['parameters']
            if kind not in condition_types:continue
            if kind==2:
                best=history.get((2,parameters['m_iDungeonID']))
                value=int(best is not None and best<=parameters['m_fTime'])
            elif kind in(4,5):value=history.get((kind,parameters['m_ePvpChannelClass']),0)
            elif kind==6:value=levels.get(parameters['m_eProfessionType'],0)
            elif kind==7:value=history.get((7,parameters['m_eBuffTempletID']),0)
            elif kind==15:value=resonance['level']
            elif kind==20:value=duration[0]
            elif kind in(10,18,19,23,24,25,26,27,28,29,30,36,43,44,45,51,52,53,56,57,58,60,61,63):value=history.get((kind,0),0)
            elif kind in(16,62):value=history.get((kind,parameters['m_iItemID']),0)
            elif kind==32:value=history.get((kind,parameters['m_iLevel']),0)
            elif kind==35:value=history.get((kind,parameters['m_iGroupID']),0)
            elif kind in(37,38):value=collections.get((kind,parameters['m_eUnitType']),0)
            elif kind==39:value=collections[(39,0)]
            elif kind==34:value=history.get((34,parameters['m_iItemID']),0)
            elif kind==50:value=collections[(50,identity)]
            elif kind==66:value=history.get((66,parameters['m_iNpcId']),0)
            elif kind==42:value=collections.get((42,parameters['m_eTitleTypeID']),0)
            elif kind==67:value=collections[(67,parameters['m_iClassLine'])]
            elif kind==68:value=collections[(68,0)]
            else:continue
            previous=old.get((identity,condition['id']),(0,False))
            value=max(value,previous[0])
            target=1 if kind in(2,66)else parameters['m_iLevel'if kind in(6,15,57)else'm_iCount']
            complete=value>=target
            if kind==20 and not complete and duration[1]is not None:
                due=duration[1]+target*86400
                couple_due=due if couple_due is None else min(couple_due,due)
            if (value,complete)==previous:continue
            updates.append(dict(achievement=identity,condition=condition['id'],value=value,complete=complete))
    result=dict(completed=[],replayed=False)
    if updates:
        proof=json.dumps(updates,sort_keys=True,separators=(',',':')).encode()
        operation=f'achievement-profile:{account}:{owner}:'+hashlib.sha256(proof).hexdigest()
        result=state.record(db,account,owner,updates,operation,now)
    if duration is not None:result['couple_due']=couple_due
    return result
