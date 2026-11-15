"""Vasily's original CC6/CC8 transactions for owned Artifact equipment."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct

from els_server.domain.artifact_identification import validate as validate_identification
from els_server.domain.artifact_progression import slots
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_reforge_transfer_messages import _changes_wire
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.artifact_equipment_state import replace as replace_socket
from els_server.storage.equipment_options import replace as replace_options
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.item_seals import assign as assign_seal
from els_server.storage.profession_state import require_owner

FIXED = 0xcc6
SUCCESSION = 0xcc8
MIRROR = frozenset(range(168915,168919))
MASTER_ROAD = frozenset(range(168600,168604))


def request(payload):
    # 368C480 writes the two UI-selected UIDs in source, recipient order.
    if len(payload)!=16:
        raise ValueError("Artifact transfer native request size")
    source,target=struct.unpack(">QQ",payload)
    if source==target or not all(0<uid<2**63 for uid in (source,target)):
        raise ValueError("Artifact transfer original item UIDs")
    return source,target


def acknowledgement(kind,target=0,changes=(),result=0):
    # CC7 and CC9 share native 368C0C0: result, current recipient UID, vector.
    vector,_=_changes_wire(changes)
    return Event(0x201,kind=kind+1,payload=struct.pack(">iQ",result,target)+vector)


def perform(path,owner,kind,payload,operation,*,account_id,guard):
    if kind not in (FIXED,SUCCESSION):
        raise ValueError("Unknown Artifact transfer action")
    source_uid,target_uid=request(payload)
    owner,digest=_identity(owner,kind,payload,operation)
    uri=Path(path).resolve().as_uri()+"?mode=rw"
    with closing(sqlite3.connect(uri,uri=True,timeout=10)) as db,db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        guard(db)
        require_active_character(db,owner)
        require_owner(db,owner,account_id)
        before=load_items(db,owner)
        owned={item["uid"]:item for item in before}
        old=_previous(db,operation,digest)
        if old is not None:
            changes=current_changes(db,operation,owner,kind,old,before)
            answer=acknowledgement(kind,target_uid if target_uid in owned else 0,changes)
            encode_event(answer)
            guard(db)
            return [answer]

        source,target=owned.get(source_uid),owned.get(target_uid)
        for item in (source,target):
            if (item is None or item["group"]!=1 or item["count"]!=1 or item.get("sealed")
                    or "expires_at" in item or "activation_seconds" in item):
                raise ValueError("Artifact transfer requires permanent unsealed bag equipment")
            require_current(item)
            require_unlocked(item)
        s_template,t_template=source["template"],target["template"]
        source_set=MIRROR if kind==FIXED else MASTER_ROAD
        if s_template not in source_set or t_template not in MIRROR or slots(s_template)!=slots(t_template):
            raise ValueError("Artifact transfer requires original same-part equipment")
        src_groups=source.get("option_groups",{})
        prior=target.get("option_groups",{})
        src_identification=validate_identification(s_template,src_groups.get("1",[]))
        dst_identification=validate_identification(t_template,prior.get("1",[]))
        if not src_identification or not dst_identification:
            raise ValueError("Artifact transfer effects must already exist")
        updated=dict(prior)
        if kind==FIXED:
            updated["1"]=validate_identification(t_template,[*dst_identification[:2],src_identification[2]])
            from els_server.game_data import client_data
            maximum=client_data().item(t_template)["record"][0xd7]
            if maximum!=1:raise ValueError("Original Mirror seal count")
            assign_seal(db,owner,target_uid,False,maximum)
        else:
            if not source.get("artifact_socket_open") or target.get("identified") is False:
                raise ValueError("Artifact succession requires an open source slot and identified recipient")
            from els_server.domain.local_artifact_rules import spirit_group,validate_spirit
            group=str(spirit_group(s_template))
            updated["1"]=validate_identification(t_template,[*src_identification,dst_identification[2]])
            spirit=validate_spirit(t_template,src_groups.get(group,[]))
            if spirit:
                updated[group]=spirit
            else:
                updated.pop(group,None)
            replace_socket(db,owner,target_uid,target.get("artifact_socket_open",False),True)
        replace_options(db,owner,target_uid,prior,updated)
        remove(db,owner,source)
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='artifact_spirit_previews'").fetchone():
            db.execute("DELETE FROM artifact_spirit_previews WHERE owner=? AND item_uid IN (?,?)",
                       (owner,source_uid,target_uid))
        after=load_items(db,owner)
        by_position={(i["group"],i["slot"]):i for i in after}
        positions=[(i["group"],i["slot"]) for i in (source,target)]
        answer=acknowledgement(kind,target_uid,[(point,by_position.get(point)) for point in positions])
        encode_event(answer)
        guard(db)
        _commit(db,operation,digest,owner,kind,positions,before,after)
        return [answer]
