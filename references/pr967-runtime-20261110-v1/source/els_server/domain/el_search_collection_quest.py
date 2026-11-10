"""Restore the independent Lv99 collection quest into the native epic list."""
from contextlib import closing
import hashlib,json,sqlite3
from pathlib import Path
from els_server.domain.el_search_collection import QUEST
from els_server.domain.seal_quests import ACTIVE_QUEST_LIMIT,quest_catalog,sequence
from els_server.protocol import quest_messages as wire
from els_server.protocol.protocol_codec import encode_event


def restore_on_arrival(session):
    from els_server.domain.quest_flow import collection_source_guard,store
    from els_server.storage.el_search_collection import exists,WRITES_ENABLED
    from els_server.storage.seal_quests import _progress_connection
    if not WRITES_ENABLED:return []
    quest=quest_catalog().quest(QUEST)
    towns=sequence(quest['QuestCondition']['m_iEnableVillage'])
    if 0 not in towns and session.active_map not in towns:return []
    guard=collection_source_guard(session)
    state=store(session);state.account_source_guard=guard
    owner=session.account.uid
    abandoned=hashlib.sha256(json.dumps([owner,'abandon',dict(quest=QUEST)],sort_keys=True).encode()).hexdigest()

    def missing_root(db):
        guard(db)
        row=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
        if row is None or row[0]<quest['QuestCondition']['m_iLevel']:return False
        if exists(db,'completed_quests')and db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(owner,QUEST)).fetchone():return False
        if exists(db,'character_quests'):
            if db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=?',(owner,QUEST)).fetchone():return False
            if db.execute('SELECT count(*) FROM character_quests WHERE owner=?',(owner,)).fetchone()[0]>=ACTIVE_QUEST_LIMIT:return False
        if exists(db,'quest_actions')and db.execute("SELECT 1 FROM quest_actions WHERE owner=? AND kind='abandon' AND request_hash=?",(owner,abandoned)).fetchone():return False
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
            row=next(r for r in result['state']['active']if r['id']==QUEST)
            events=[wire.accepted(row),wire.progress([row])]
            for event in events:encode_event(event)
            return events
        result=state.action('accept',dict(quest=QUEST,npc=10025),'collection-root:'+str(owner),encode,
                            location=('town',session.active_map),transaction=db)
        return result['events']
