"""Atomic same-owner source NPC progress; acceptance and rewards stay separate."""
from contextlib import closing
import hashlib,json,sqlite3
from els_server.domain.town_dialogue import catalog
from els_server.domain.seal_quests import quest_catalog,require_eligible,sequence
from els_server.storage.seal_quests import load_character,completed_ids,_state
from els_server.storage.inventory_state import load_items
from els_server.protocol import quest_messages,tutorial_dialogue_messages

def interact(store,npc,operation):
    if type(npc) is not int or str(npc) not in catalog()['npc_bindings'] or not isinstance(operation,str) or not 1<=len(operation)<=200:raise ValueError('Town dialogue identity')
    with closing(sqlite3.connect(store.path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        character=load_character(db,store.uid,store.account_id)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return None
        supported={int(q) for q in catalog()['quests']}
        from els_server.storage import account_contract26780_scope as contract26780
        if not any(q in supported for q, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(store.uid,))) and not contract26780.has_active(db,store.uid):return None
        saved=db.execute('SELECT town FROM location WHERE uid=?',(store.uid,)).fetchone()
        if saved is None or str(saved[0]) not in catalog()['npc_bindings'][str(npc)]['towns']:raise ValueError('Town dialogue scene')
        items=load_items(db,store.uid);state=_state(db,store.uid,items)
        matches=[];generations=[];contract_sources=[]
        for active in state['active']:
            identity=active['id']
            if identity not in supported:continue
            q=quest_catalog().quest(identity);subs=quest_catalog().objectives(identity)
            if not any(s['m_eClearType']==1 and s['m_ClearCondition'].get('m_eTalkNPCID')==npc for s in subs):continue
            expected=tuple(catalog()['subquests'][str(s)] for s in sequence(q['m_vecSubQuest']))
            if q!=catalog()['quests'][str(identity)] or subs!=expected:raise ValueError('Town dialogue source')
            require_eligible(character,q,completed_ids(db,store.uid),items,location=('town',saved[0]))
            provenance=None
            if identity==contract26780.CONTRACT:
                provenance=contract26780.dialogue_source(db,store,active,npc,saved[0]);contract_sources.append(active)
            elif db.execute('SELECT owner,kind FROM quest_actions WHERE rowid=?',(active['generation'],)).fetchone()!=(store.uid,'accept'):raise ValueError('Town dialogue accepted generation')
            counts=dict(active['objectives'])
            for sub in subs:
                if sub['m_eClearType']==1 and sub['m_ClearCondition'].get('m_eTalkNPCID')==npc:counts[sub['m_iID']]=1
            matches.append(dict(active,objectives=counts))
            generation=dict(quest=identity,accepted_at=active['accepted_at'],accepted_action=active['generation'])
            if provenance is not None:generation.update(contract26780=provenance)
            generations.append(generation)
        if not matches:return None
        # Keep the original single-quest13 receipt shape byte for byte, so old
        # accepted generations and retries remain valid after this extension.
        event=dict(kind='npc_talk',npc=npc,town=saved[0])
        if len(matches)==1:event.update(generations[0])
        else:event['quests']=generations
        raw=json.dumps(event,sort_keys=True);digest=hashlib.sha256(raw.encode()).hexdigest()
        old=db.execute('SELECT proof_hash,event_json FROM quest_progress_events WHERE owner=? AND event_id=?',(store.uid,operation)).fetchone()
        if old and old!=(digest,raw):raise ValueError('Conflicting town dialogue generation/retry')
        if old and any(next(r for r in state['active'] if r['id']==changed['id'])['objectives']!=changed['objectives'] for changed in matches):raise ValueError('Inconsistent town dialogue retry')
        if not old:
            for changed in matches:
                owner=changed['owner'] if changed['id']==contract26780.CONTRACT else store.uid
                updated=db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=?',(json.dumps(changed['objectives'],sort_keys=True),owner,changed['id'])).rowcount
                if changed['id']==contract26780.CONTRACT and updated!=1:raise ValueError('Contract26780 canonical row retired')
            db.execute('INSERT INTO quest_progress_events VALUES (?,?,?,?)',(store.uid,operation,digest,raw))
        # A single source task can request its detail. With multiple matches,
        # leave focus0 rather than inventing a priority between source tasks.
        events=[quest_messages.progress(matches),tutorial_dialogue_messages.acknowledgement(matches[0]['id'] if len(matches)==1 else 0)]
        if contract_sources:
            from els_server.protocol.protocol_codec import encode_event
            for active in contract_sources:contract26780.dialogue_source(db,store,active,npc,saved[0])
            for event in events:encode_event(event)
            for active in contract_sources:contract26780.dialogue_source(db,store,active,npc,saved[0])
        if any(not isinstance(e.payload,bytes) or len(e.payload)>65536 for e in events):raise ValueError('Town dialogue response bound')
        return events
