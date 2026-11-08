"""Deterministic enchant transaction behind an explicit feature gate.

Only native-verified default-record equipment templates are admitted. Random crystals,
equipped items, special equipment and event fee waivers remain pending.
"""
from contextlib import closing
import hashlib,json,sqlite3
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.reward_state import validate_balances
from els_server.storage.equipment_attributes import replace_attributes
from els_server.domain.equipment_attributes import validate_slots
from els_server.domain.normal_equipment import definitions as normal_equipment_definitions
from els_server.domain.enchant_rules import attribute_quote,normal_item_quote
from els_server.game_data import client_data
from els_server.protocol.enchant_messages import request,acknowledgement,EnchantResult,EnchantRejected

SUPPORTED_EQUIPMENT=frozenset(normal_equipment_definitions())


def change_attribute(path,owner,payload,operation_id):
    """Caller must authenticate owner/phase and supply a transport operation ID.

    Replays return current balances and a required absolute inventory snapshot,
    never historical deltas that could undo later purchases or attribute edits.
    """
    owner=character_uid(owner);item_uid,slot,target=request(payload)
    if target==7:raise EnchantRejected(EnchantResult.NOT_ALLOWED)
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Enchant operation identity')
    digest=hashlib.sha256(str(owner).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone():raise EnchantRejected(EnchantResult.UNKNOWN_CHARACTER)
        balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
        items=load_items(db,owner)
        db.execute('''CREATE TABLE IF NOT EXISTS attribute_enchant_receipts (
            operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
            owner INTEGER NOT NULL REFERENCES characters(uid), item_uid INTEGER NOT NULL,
            evidence_json TEXT NOT NULL)''')
        previous=db.execute('SELECT request_hash,owner FROM attribute_enchant_receipts WHERE operation_id=?',(operation_id,)).fetchone()
        if previous:
            if previous!=(digest,owner):raise ValueError('Conflicting enchant retry')
            return dict(replayed=True,response=acknowledgement(balance['ed']),balances=balance,
                        requires_inventory_sync=True,inventory=items)
        item=next((i for i in items if i['uid']==item_uid),None)
        if item is None:raise EnchantRejected(EnchantResult.ITEM_NOT_OWNED)
        from els_server.domain.item_expiration import expired
        if expired(item):raise EnchantRejected(EnchantResult.NOT_ALLOWED)
        if item['template'] not in SUPPORTED_EQUIPMENT or item['group']!=1 or item['count']!=1:
            raise EnchantRejected(EnchantResult.NOT_ALLOWED)
        definition=client_data().item(item['template'])
        if definition['flags4']&0xa1:raise EnchantRejected(EnchantResult.NOT_ALLOWED)
        before=validate_slots(item['template'],item.get('attributes',[0]*4))
        if target:
            if before[slot]:raise EnchantRejected(EnchantResult.OCCUPIED_SLOT)
            quote=attribute_quote(item['template'],before,target)
            if not quote['can_add_by_slot_rules'] or slot!=quote['first_empty_slot']:raise EnchantRejected(EnchantResult.NOT_ALLOWED)
            material=quote['material']
        else:
            if not before[slot]:raise EnchantRejected(EnchantResult.EMPTY_SLOT)
            # OnClick_Remove sends the selected slot and target0. The same
            # 2E8A040 price function counts existing slots before removal.
            # Preserve the other slot indices; do not invent a material refund.
            quote=normal_item_quote(item['template'],before);material=None
        cost=quote['normal_ed_cost']
        if type(cost) is not int or cost<0:raise ValueError('Invalid enchant ED quote')
        if balance['ed']<cost:raise EnchantRejected(EnchantResult.INSUFFICIENT_ED if target else EnchantResult.INSUFFICIENT_REMOVE_ED)
        if balance['revision']==2**63-1:raise ValueError('Enchant revision overflow')
        stacks=sorted((i for i in items if material and i['template']==material['template'] and i['group']==4 and not expired(i)),key=lambda i:i['slot'])
        needed=material['quantity'] if material else 0
        if material and (type(needed) is not int or needed<=0 or sum(i['count'] for i in stacks)<needed):raise EnchantRejected(EnchantResult.INSUFFICIENT_CRYSTALS)
        after=list(before);after[slot]=target;validate_slots(item['template'],after)
        changes=[((item['group'],item['slot']),dict(item,attributes=after))];debits=[]
        for stack in stacks:
            used=min(stack['count'],needed);remaining=stack['count']-used;needed-=used
            debits.append(dict(uid=stack['uid'],template=stack['template'],quantity=used))
            if remaining:
                db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',(remaining,stack['uid'],owner))
                updated=dict(stack,count=remaining)
            else:
                from els_server.storage.item_expiration import forget
                forget(db,stack['uid'])
                db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(stack['uid'],owner));updated=None
            changes.append(((stack['group'],stack['slot']),updated))
            if not needed:break
        replace_attributes(db,owner,item_uid,before,after)
        balance=dict(balance,ed=balance['ed']-cost,revision=balance['revision']+1)
        db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=?',(balance['ed'],balance['revision'],owner))
        # Encoding and a full post-change validation precede commit. Any failure
        # rolls back currency, all material stacks, the attribute and the receipt.
        inventory=load_items(db,owner);response=acknowledgement(balance['ed'],changes)
        if not isinstance(response,bytes) or not 30<=len(response)<=65536:raise ValueError('Enchant response bounds')
        evidence=dict(operation='add' if target else 'remove',slot=slot,template=item['template'],before=before,after=after,ed_cost=cost,
                      materials=debits,quote=quote,normal_fee=True)
        db.execute('INSERT INTO attribute_enchant_receipts VALUES (?,?,?,?,?)',
                   (operation_id,digest,owner,item_uid,json.dumps(evidence,sort_keys=True)))
        return dict(replayed=False,response=response,balances=balance,
                    requires_inventory_sync=False,inventory=inventory,evidence=evidence)
