"""One atomic debit, native warp position, and existing durable receipt."""
from contextlib import closing
import hashlib,json,sqlite3,uuid
from els_server.domain import town_travel as rules
from els_server.domain.item_expiration import expired
from els_server.storage.inventory_state import load_items
from els_server.storage.seal_quests import load_character,completed_ids
from els_server.storage.reward_state import validate_balances,RewardConflict
from els_server.protocol import town_travel_messages as wire

def travel(path,uid,account_id,source,payload,operation,*,now):
    if str(uuid.UUID(operation))!=operation:raise ValueError('Town warp receipt identity')
    destination,free,special,growth=wire.request(payload)
    if type(source) is not int or type(now) is not int or now<0:raise ValueError('Town warp source clock')
    proof=json.dumps(dict(owner=uid,account=account_id,source=source,payload=payload.hex()),sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(proof.encode()).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');character=load_character(db,uid,account_id)
        previous=db.execute('SELECT proof_sha256,grant_json,response,balance_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
        if previous:
            grant=json.loads(previous[1])
            if previous[0]!=digest or grant.get('kind')!='town_warp' or grant.get('owner')!=uid:raise RewardConflict('Conflicting town warp receipt')
            return dict(response=bytes(previous[2]),balances=json.loads(previous[3]),grant=grant,replayed=True)
        saved=db.execute('SELECT town FROM location WHERE uid=?',(uid,)).fetchone()
        if saved!=(source,) or str(source) not in rules.catalog()['towns']:raise ValueError('Town warp current source mismatch')
        if source==destination:raise ValueError('Town warp same destination')
        records={r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(uid,))}
        point=rules.require_destination(destination,character,completed_ids(db,uid),records)
        items=load_items(db,uid)
        passes=[i for i in items if i['template']==118149 and i['group']==4 and i['count']>0 and not expired(i,now=now)]
        # An owned, live118149 is a bag-presence waiver. No consumption/VIP timer.
        if free and not passes:raise ValueError('Town warp free entitlement expired or absent')
        fee=0 if passes else rules.price(source,destination,character['level'])
        before=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
        if before['ed']<fee:raise ValueError('Town warp insufficient ED')
        after=dict(before,ed=before['ed']-fee,revision=before['revision']+1)
        if after['revision']>=2**63:raise ValueError('Town warp revision overflow')
        grant=dict(kind='town_warp',owner=uid,source=source,destination=destination,fee=fee,pass_uid=passes[0]['uid'] if passes else None,flags=[free,special,growth])
        response=wire.acknowledgement(destination,after['ed']).payload
        if not isinstance(response,bytes) or len(response)!=32:raise ValueError('Town warp response encoding')
        # Store the source-defined IsWarp coordinates with the charge. A
        # disconnect before225/227 therefore cold-loads the paid destination.
        db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=?',(after['ed'],after['revision'],uid))
        db.execute('UPDATE location SET town=?,board=0,progress=0,x=?,y=?,z=?,revision=revision+1 WHERE uid=?',(destination,*point['xyz'],uid))
        db.execute('INSERT INTO reward_receipts VALUES (?,?,?,?,?)',(operation,digest,json.dumps(grant,sort_keys=True),response,json.dumps(after,sort_keys=True)))
        return dict(response=response,balances=after,grant=grant,replayed=False)
