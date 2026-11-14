"""Restore the independent Lv99 collection and resonance Epic roots."""
from contextlib import closing
import hashlib,json,sqlite3
from pathlib import Path
from els_server.domain.el_search_collection import QUEST
from els_server.domain.seal_quests import acceptance_available,quest_catalog,sequence
from els_server.protocol import quest_messages as wire
from els_server.protocol.protocol_codec import encode_event


def restore_on_arrival(session,*,quest_id=QUEST):
    from els_server.domain.quest_flow import collection_source_guard,store
    from els_server.storage.el_search_collection import exists,is_active,WRITES_ENABLED
    from els_server.storage.seal_quests import _progress_connection
    if quest_id==QUEST and not WRITES_ENABLED:return []
    quest=quest_catalog().quest(quest_id)
    towns=sequence(quest['QuestCondition']['m_iEnableVillage'])
    if 0 not in towns and session.active_map not in towns:return []
    guard=collection_source_guard(session)
    state=store(session);state.account_source_guard=guard
    owner=session.account.uid
    account_scoped=bool(quest.get('m_bIsAccount'))

    def missing_root(db):
        guard(db)
        row=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
        if row is None or row[0]<quest['QuestCondition']['m_iLevel']:return False
        if quest_id==QUEST:
            if is_active(db,owner):return False
        else:
            from els_server.storage.resonance_state import snapshot
            if snapshot(db,owner,session.account.account_id)['enabled']:return False
        owners=tuple(r[0]for r in db.execute('SELECT uid FROM character_owners WHERE account_id=?',(session.account.account_id,)))if account_scoped else(owner,)
        for uid in owners:
            for table in ('character_quests','completed_quests'):
                if exists(db,table)and db.execute('SELECT 1 FROM '+table+' WHERE owner=? AND quest=?',(uid,quest_id)).fetchone():return False
            abandoned=hashlib.sha256(json.dumps([uid,'abandon',dict(quest=quest_id)],sort_keys=True).encode()).hexdigest()
            if exists(db,'quest_actions')and db.execute("SELECT 1 FROM quest_actions WHERE owner=? AND kind='abandon' AND request_hash=?",(uid,abandoned)).fetchone():return False
        if exists(db,'character_quests'):
            active=[dict(id=q)for q, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(owner,))]
            if not acceptance_available(quest,active):return False
        return True

    # Already present, completed or ineligible roles never acquire a writer.
    path=Path(state.path).resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10))as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        if not missing_root(db):return []
    with _progress_connection(path,None)as db:
        if not missing_root(db):return []
        def encode(result):
            if result['replayed']:return []
            row=next(r for r in result['state']['active']if r['id']==quest_id)
            events=[wire.accepted(row),wire.progress([row])]
            for event in events:encode_event(event)
            return events
        operation='collection-root:'+str(owner)if quest_id==QUEST else'resonance-root:'+str(session.account.account_id)
        result=state.action('accept',dict(quest=quest_id,npc=10025),operation,encode,
                            location=('town',session.active_map),transaction=db)
        return result['events']
