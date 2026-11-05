"""Atomic same-owner existing-task dialogue count; no acceptance or reward writes."""
from contextlib import closing
import hashlib,json,sqlite3
from els_server.domain.tutorial_dialogue import DIALOGUE_PREDECESSORS,NPC,TOWN,SUBQUEST
from els_server.domain.seal_quests import quest_catalog,require_eligible,sequence
from els_server.storage.seal_quests import ensure,load_character,completed_ids,_state
from els_server.storage.inventory_state import load_items
from els_server.protocol import quest_messages,tutorial_dialogue_messages
from els_server.domain.tutorial_progression import CAREER_SUBQUEST

def interact(store,npc,operation):
    if npc!=NPC or not isinstance(operation,str) or not 1<=len(operation)<=200:raise ValueError('Tutorial dialogue identity')
    with closing(sqlite3.connect(store.path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        character=load_character(db,store.uid,store.account_id)
        from els_server.game_data import client_data
        if character['unit_type']!=15 or client_data().unit(character['unit_class'])['unitType']!=15:raise ValueError('Tutorial dialogue character')
        if db.execute('SELECT town FROM location WHERE uid=?',(store.uid,)).fetchone()!=(TOWN,):raise ValueError('Tutorial dialogue scene')
        ensure(db);items=load_items(db,store.uid);state=_state(db,store.uid,items)
        candidates=[r for r in state['active'] if r['id'] in DIALOGUE_PREDECESSORS]
        if len(candidates)!=1:raise ValueError('Tutorial dialogue missing/ambiguous active task')
        active=candidates[0];quest=active['id'];objective=SUBQUEST['m_iID'];done=completed_ids(db,store.uid)
        predecessor=DIALOGUE_PREDECESSORS[quest];q=quest_catalog().quest(quest)
        expected=(SUBQUEST,CAREER_SUBQUEST) if quest==28210 else (SUBQUEST,)
        if (quest_catalog().objectives(quest)!=expected or q['m_eStartNPCID']!=NPC or q['m_eEndNPCID']!=NPC
            or sequence(q['QuestCondition']['m_vecBeforeQuestID'])!=(predecessor,)):
            raise ValueError('Tutorial dialogue source')
        if predecessor not in done:raise ValueError('Tutorial dialogue predecessor')
        require_eligible(character,q,done,items,location=('town',TOWN))
        # Existing generations use second timestamps. Bind the accepted action
        # and last abandon receipt as well, so a same-second abandon/reaccept
        # cannot reuse the previous interaction's receipt.
        signatures=[hashlib.sha256(json.dumps([store.uid,'accept',dict(quest=quest,npc=value)],sort_keys=True).encode()).hexdigest() for value in (NPC,10025)]
        accepted=db.execute('SELECT COALESCE(MAX(rowid),0) FROM quest_actions WHERE owner=? AND kind=? AND request_hash IN (?,?)',(store.uid,'accept',*signatures)).fetchone()[0]
        signature=hashlib.sha256(json.dumps([store.uid,'abandon',dict(quest=quest)],sort_keys=True).encode()).hexdigest()
        abandoned=db.execute('SELECT COALESCE(MAX(rowid),0) FROM quest_actions WHERE owner=? AND kind=? AND request_hash=?',(store.uid,'abandon',signature)).fetchone()[0]
        event=dict(kind='npc_talk',npc=NPC,town=TOWN,quest=quest,accepted_at=active['accepted_at'],generation=active['generation'],accepted_action=accepted,abandoned_action=abandoned)
        raw=json.dumps(event,sort_keys=True);digest=hashlib.sha256(raw.encode()).hexdigest()
        old=db.execute('SELECT proof_hash,event_json FROM quest_progress_events WHERE owner=? AND event_id=?',(store.uid,operation)).fetchone()
        if old and old!=(digest,raw):raise ValueError('Conflicting tutorial dialogue generation/retry')
        if old and active['objectives'].get(objective)!=1:raise ValueError('Inconsistent tutorial dialogue retry')
        counts=dict(active['objectives']);counts[objective]=1
        if not old:
            db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=?',(json.dumps(counts,sort_keys=True),store.uid,quest))
            db.execute('INSERT INTO quest_progress_events VALUES (?,?,?,?)',(store.uid,operation,digest,raw))
        row=dict(active,objectives=counts)
        events=[quest_messages.progress([row]),tutorial_dialogue_messages.acknowledgement(quest)]
        if any(not isinstance(e.payload,bytes) or len(e.payload)>65536 for e in events):raise ValueError('Tutorial dialogue response bound')
        return events
