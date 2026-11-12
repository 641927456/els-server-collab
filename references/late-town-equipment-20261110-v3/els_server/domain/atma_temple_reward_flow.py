"""Use a native Spirit Lord's Temple reward restoration tag."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import time

TAGS = {
    720852:"1e0a467ddb664ed7a7b583a34b2ef7593334921b42c7802aa006b97f3bf2adec",
    720853:"a4bc2d1f7e79dbd5de3c7cc2002aa4af89eb5f30841df3c38b9896b54427e00b",
    720854:"b4c4178f84360d99f24972b3aa4fb4abc6fc71df561ab5ce7d1bc87cf43e557b",
    720855:"e991f057202bd40c108a8fe8761c5eddaf892a14f1d0cf6d659f7f7c8f0e4722",
}


def handle(session,event,sequence):
    if ((event.event_id,event.kind)!=(0x202,0x219) or len(event.payload)<8
            or session.phase!="town_ready" or not session.item_test or session.client_build!="dx11_260923"):
        return None
    account=session.account
    if account.store is None:
        return None
    uid,=struct.unpack_from(">Q",event.payload)
    if not 0<uid<2**63:
        return None
    owner=account.uid
    uri=Path(account.store.path).resolve().as_uri()
    operation=f"{session.shop_session_id}:atma-temple-restore:{owner}:{sequence}"
    from els_server.storage.inventory_actions import _identity,_previous,_commit
    with closing(sqlite3.connect(uri+"?mode=ro",uri=True)) as db:
        item=db.execute("SELECT template FROM inventory_items WHERE uid=? AND owner=?",(uid,owner)).fetchone()
        known=item is not None and item[0] in TAGS
        if not known and not db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone():
            return None
        if not known and not db.execute("SELECT 1 FROM inventory_action_receipts WHERE operation_id=? AND owner=?",
                                        (operation,owner)).fetchone():
            return None

    from els_server.domain.housing_access_flow import capture
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    from els_server.protocol.career_messages import use_ack,use_request
    from els_server.protocol.protocol_codec import encode_event
    from els_server.protocol.weekly_dungeon_counts import notification
    from els_server.storage.atma_temple_weekly import restore
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import remove
    from els_server.storage.npc_trade import balances
    from els_server.storage.profession_state import require_owner

    try:
        same,guard=capture(session)
        if (event.performers not in ((),(0,)) or event.uid!=event.target_uid or event.uid!=2**64-1
                or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32
                or use_request(event.payload)!=uid):
            raise ValueError("Temple restoration tag native request")
        owner,digest=_identity(owner,0x219,event.payload,operation)
        with closing(sqlite3.connect(uri+"?mode=rw",uri=True,timeout=10)) as db,db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            guard(db)
            require_owner(db,owner,account.account_id)
            before=load_items(db,owner)
            ed=balances(db,owner)['ed']
            previous=_previous(db,operation,digest)
            if previous is not None:
                import json
                saved=db.execute("SELECT before_json FROM inventory_action_receipts WHERE operation_id=?",
                                 (operation,)).fetchone()
                template=next(i["template"] for i in json.loads(saved[0]) if i["uid"]==uid)
                answer=use_ack(current_changes(db,operation,owner,0x219,previous,before),template,ed)
                encode_event(answer)
                counts=notification(db,owner)
                guard(db)
                return [answer,counts]

            item=next((i for i in before if i["uid"]==uid),None)
            if item is None or item["template"] not in TAGS or item["group"]!=4 or item.get("sealed"):
                raise ValueError("Owned usable Temple restoration tag required")
            now=int(time.time())
            require_current(item,now=now)
            require_unlocked(item,now=now)
            restore(db,owner,now)
            if item["count"]==1:
                remove(db,owner,item)
            else:
                db.execute("UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?",(uid,owner))
            after=load_items(db,owner)
            position=(item["group"],item["slot"])
            updated=next((i for i in after if i["uid"]==uid),None)
            answer=use_ack([(position,updated)],item["template"],ed)
            encode_event(answer)
            counts=notification(db,owner)
            guard(db)
            _commit(db,operation,digest,owner,0x219,[position],before,after)
            return [answer,counts]
    except (ValueError,sqlite3.Error):
        return [use_ack(result=-1)] if "same" in locals() and same() else []
