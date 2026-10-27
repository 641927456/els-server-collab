"""Restore eligible starters/deferred admitted story edges, never rewards."""
from contextlib import closing
import json,sqlite3,time
from els_server.domain.seal_quests import quest_catalog,require_eligible,sequence,ACTIVE_QUEST_LIMIT
from els_server.storage.seal_quests import load_character,ensure,_state
from els_server.storage.inventory_state import load_items
from els_server.protocol import quest_messages as wire

STARTERS={**{t:(100000,20000) for t in range(1,13)},13:(25000,20011),14:(26800,20012),15:(28000,20014)}

def starter(unit_type):
    if type(unit_type) is not int or unit_type not in STARTERS:raise ValueError('Tutorial character identity')
    qid,town=STARTERS[unit_type];catalog=quest_catalog();quest=catalog.quest(qid)
    types=sequence(quest['QuestCondition']['m_eUnitType'])
    expected=tuple(range(1,13)) if unit_type<=12 else (unit_type,)
    objectives=catalog.objectives(qid)
    if (quest['m_eQuestType']!=5 or set(types)!=set(expected)
        or sequence(quest['QuestCondition']['m_iEnableVillage'])!=(town,)
        or len(objectives)!=1 or objectives[0]['m_eClearType']!=24
        or sequence(objectives[0]['m_ClearCondition']['m_eVillageID'])!=(town,)):
        raise ValueError('Tutorial source contract changed')
    return quest,town

def starting_town(unit_type):return starter(unit_type)[1]

def unprogressed_tutorial_creation(db,uid,character):
    """Existing normal creation/clear evidence; saved town is not arrival."""
    from els_server.storage.characters import BASE_CLASSES
    from els_server.domain.first_story_entry import MAPS
    unit=character['unit_type']
    if (unit not in MAPS or character['unit_class']!=BASE_CLASSES[unit]
        or character['level']!=1
        or db.execute('SELECT experience FROM reward_balances WHERE uid=?',(uid,)).fetchone()!=(0,)
        or not db.execute('SELECT 1 FROM character_creation_receipts WHERE uid=? LIMIT 1',(uid,)).fetchone()):return False
    if db.execute('SELECT 1 FROM dungeon_records WHERE uid=? AND map_id=?',(uid,MAPS[unit])).fetchone():return False
    return not db.execute("SELECT 1 FROM reward_receipts WHERE json_extract(grant_json,'$.owner')=? AND json_extract(grant_json,'$.dungeon_clear[0]')=? LIMIT 1",(uid,MAPS[unit])).fetchone()

def first_arrival_pending(state):
    # Never rewrite an existing ready/completed/unknown historical task. This
    # read only prevents an unprogressed creation from skipping its tutorial
    # via a town load; the existing committed clear receipt ends the gate.
    with closing(sqlite3.connect(state.path.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('BEGIN')
        character=load_character(db,state.uid,state.account_id)
        qid=STARTERS[character['unit_type']][0]
        row=db.execute('SELECT objectives FROM character_quests WHERE owner=? AND quest=?',(state.uid,qid)).fetchone()
        if row is None or db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(state.uid,qid)).fetchone():return False
        if any(json.loads(row[0]).values()):return False
        return unprogressed_tutorial_creation(db,state.uid,character)

def restore_initialization(state,*,live=False,defer_starter_arrival=False):
    """Encode a same-owner snapshot before committing any missing root.

    Existing locations and all quest progress remain authoritative. Unknown
    historical IDs also block restoration, so a partial catalog never sends
    a character with unclassified progress back to the start of its story.
    """
    with closing(sqlite3.connect(state.path,timeout=10)) as db:
        with write_transaction(db):
            character=load_character(db,state.uid,state.account_id);ensure(db)
            items=load_items(db,state.uid);snapshot=_state(db,state.uid,items)
            previous={row['id'] for row in snapshot['active']}
            quest,town=starter(character['unit_type']);qid=quest['m_iID'];catalog=quest_catalog()
            progress={r['id'] for key in ('active','completed') for r in snapshot[key]}
            has_story=any(i not in catalog.quests or catalog.quest(i)['m_eQuestType']==5 for i in progress)
            saved=db.execute('SELECT town FROM location WHERE uid=?',(state.uid,)).fetchone()
            restored=False
            if saved==(town,) and not has_story and len(snapshot['active'])<ACTIVE_QUEST_LIMIT:
                try:require_eligible(character,quest,{r['id'] for r in snapshot['completed']},items,location=('town',town))
                except ValueError:pass
                else:
                    now=int(time.time())
                    if not 0<now<2**63:raise ValueError('Tutorial timestamp')
                    # Only this new root may defer its first arrival. Existing
                    # progress is never lowered; a default saved town alone is
                    # insufficient for an owned new tutorial creation.
                    # No completed row, reward, EXP or inventory grant is written.
                    arrived=not (defer_starter_arrival and unprogressed_tutorial_creation(db,state.uid,character))
                    counts={s['m_iID']:int(arrived) for s in catalog.objectives(qid)}
                    db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(state.uid,qid,now,now,json.dumps(counts,sort_keys=True)))
                    snapshot=_state(db,state.uid,items);restored=True
            # The existing validated selection/town-ready callers also recheck
            # delayed current after-edges. Same-owner saved location supplies the
            # context; map-panel selection never calls this path.
            if saved is not None:
                from els_server.storage.epic_followups import restore_deferred
                now=int(time.time())
                if not 0<now<2**63:raise ValueError('Story restoration timestamp')
                accepted=restore_deferred(db,state.uid,character,items,('town',saved[0]),now)
                if accepted:
                    snapshot=_state(db,state.uid,items);restored=True
            event=wire.initialization(snapshot)
            if not isinstance(event.payload,bytes) or len(event.payload)>65536:raise ValueError('Tutorial initialization bound')
            if live:
                # F0 invokes the original live quest/UI callbacks. Build all new
                # acceptance notices before committing the deferred acceptance.
                events=[event]+[wire.accepted(row) for row in snapshot['active'] if row['id'] not in previous]
                from els_server.domain.tutorial_memory8_finale import ready_hidden_receipt
                ready=ready_hidden_receipt([row for row in snapshot['active'] if row['id'] not in previous])
                if ready:events.append(wire.progress(ready))
                from els_server.protocol.protocol_codec import encode_event
                for notice in events:encode_event(notice)
                return events,restored
            return event,restored

from els_server.storage.sqlite_timing import write_transaction
