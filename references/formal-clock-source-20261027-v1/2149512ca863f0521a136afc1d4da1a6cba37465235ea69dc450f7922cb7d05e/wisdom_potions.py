"""One original reward transaction: debit singleton, EXP/level, native ACK/D9."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,struct,uuid
from els_server.domain.wisdom_potions import admitted,definitions,request,read_existing,PAYLOAD_SHA
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event

def recognizes(path,owner,payload,operation):
    if type(payload)is not bytes or len(payload)<8:return False
    uid=struct.unpack_from('>Q',payload)[0]
    with closing(sqlite3.connect(path,timeout=10))as db:
        r=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,uid)).fetchone()
        if r and r[0]in admitted():return True
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone()and db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=?',(operation,owner,0x219)).fetchone())

def perform(path,owner,account,payload,operation,reward,*,prepare,notice):
    item_uid=request(payload);owner,digest=_identity(owner,0x219,payload,operation)
    from els_server.storage.reward_state import RewardState
    if type(reward)is not RewardState or reward.uid!=owner or Path(reward.path).resolve()!=Path(path).resolve():raise ValueError('Wisdom original reward writer/save')
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    from els_server.storage.inventory_state import load_items
    from els_server.storage.npc_trade import balances
    from els_server.game_data import client_data
    award=str(uuid.uuid5(uuid.NAMESPACE_OID,'owned-wisdom-exp-v1:'+operation))
    proof=b'owned-wisdom-exp-v1\0'+bytes.fromhex(PAYLOAD_SHA)+struct.pack('>QQ',account,owner)+payload
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,owner);require_owner(db,owner,account);prepare(db)
        old=_previous(db,operation,digest);items=load_items(db,owner);wallet=balances(db,owner)
        if old is not None:
            source=db.execute('SELECT before_json,after_json FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=?',(operation,owner,0x219)).fetchone()
            before,after=(json.loads(v)for v in source)
            if len(before)!=1 or after or before[0]['uid']!=item_uid or before[0]['template']not in definitions():raise ValueError('Wisdom original consumed singleton receipt')
            read_existing(dict(before[0]))
            saved=db.execute('SELECT proof_sha256 FROM reward_receipts WHERE run_id=?',(award,)).fetchone()
            if saved!=(hashlib.sha256(proof).hexdigest(),):raise ValueError('Wisdom committed EXP receipt missing')
            events=[use_ack(current_changes(db,operation,owner,0x219,old,items),ed=wallet['ed']),notice(db,items,wallet)]
            for event in events:encode_event(event)
            prepare(db);return events
        if db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(award,)).fetchone():raise ValueError('Orphan wisdom EXP receipt')
        item=next((i for i in items if i['uid']==item_uid),None)
        if item is None or item['template']not in admitted():raise ValueError('Owned wisdom potion required')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item);require_unlocked(item)
        if item.get('sealed',False):raise ValueError('Sealed wisdom potion')
        level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
        if not 1<=level<99:raise ValueError('Wisdom potion excludes maximum level')
        current=client_data().level_progress(wallet['experience']);rule=definitions()[item['template']]
        if current['level']!=level or level<rule['minimum_level']or current['required']<=0:raise ValueError('Wisdom consistent current level/EXP required')
        maximum=client_data().thresholds[-1]
        if not 0<maximum<=2**31-1:raise ValueError('Native ordinary EXP ceiling')
        amount=min(current['required']*rule['percent']//100,maximum-wallet['experience'])
        if amount<=0:raise ValueError('Wisdom EXP target full')
        from els_server.storage.item_instances import remove
        remove(db,owner,item);events=[]
        def encode(updated):
            current_items=load_items(db,owner);events.extend([use_ack([((item['group'],item['slot']),None)],item['template'],updated['ed']),notice(db,current_items,updated)])
            for event in events:encode_event(event)
            prepare(db);return events[0].payload
        result=reward.grant(award,proof,0,amount,encode,transaction=db,experience_limit=maximum)
        if result['replayed']or len(events)!=2:raise ValueError('Wisdom original award did not prepare its full response')
        _commit(db,operation,digest,owner,0x219,[(item['group'],item['slot'])],[dict(item)],[])
        prepare(db);return events
