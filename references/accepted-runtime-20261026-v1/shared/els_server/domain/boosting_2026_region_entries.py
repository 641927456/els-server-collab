"""Eligible zero-progress region entry tasks for the bound growth role only.

The caller owns the SQLite transaction, participant gate and encoded replies.
Root scheduling is an explicit local compatibility rule. Native current quest
conditions, progress events, claim transaction and map admission remain in use.
"""
import json
from els_server.domain.region_quests import region_catalog
from els_server.domain.seal_quests import require_eligible,sequence,target
from els_server.protocol.quest_messages import accepted
from els_server.storage.seal_quests import ensure,load_character,completed_ids
from els_server.storage.inventory_state import load_items

ENTRIES=(26640,26650)

def resume(db,uid,account_id,*,now,location):
    if type(now) is not int or not 0<now<2**63:raise ValueError('Region entry timestamp')
    character=load_character(db,uid,account_id)
    if character['level']!=99:return []
    ensure(db);completed=completed_ids(db,uid)
    active={q for q, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,))}
    items=load_items(db,uid);catalog=region_catalog();messages=[]
    for qid in ENTRIES:
        if qid in active or qid in completed:continue
        q=catalog.data['quests'][str(qid)]['definition']
        if q['m_eQuestType']!=5 or q['m_bRepeat'] or q['m_bIsTimeEvent']:raise ValueError('Region entry source changed')
        try:require_eligible(character,q,completed,items,location=location)
        except ValueError:continue
        if len(active)>=30:break
        subs=[catalog.data['subquests'][str(i)]['definition'] for i in sequence(q['m_vecSubQuest'])]
        if not subs or any(target(s)<1 for s in subs):raise ValueError('Region entry objective definition')
        counts={s['m_iID']:0 for s in subs}
        row=dict(id=qid,owner=uid,accepted_at=now,generation=now,objectives=counts)
        message=accepted(row)
        db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(uid,qid,now,now,json.dumps(counts,sort_keys=True)))
        active.add(qid);messages.append(message)
    return messages
