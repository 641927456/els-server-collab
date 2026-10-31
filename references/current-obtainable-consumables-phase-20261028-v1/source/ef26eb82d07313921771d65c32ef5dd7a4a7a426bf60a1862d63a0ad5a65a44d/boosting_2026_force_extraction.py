"""One extractor -> one exact owned book, atomic and retry-safe."""
import sqlite3,time
from contextlib import closing
from els_server.domain.boosting_2026_force_extraction import EXTRACTOR,request,acknowledgement
from els_server.storage.boosting_2026_force_inventory import saved as owned
from els_server.storage.boosting_2026_force_equipment import _character,saved as slots
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.protocol.protocol_codec import encode_event

def action(path,owner,account,payload,operation,*,now=None):
    skill,rank=request(payload)
    if not isinstance(operation,str):raise ValueError('Force extraction operation identity')
    operation='force-extract:'+operation;owner,digest=_identity(owner,0x6ce,payload,operation)
    if type(account) is not int or not 0<account<2**63:raise ValueError('Force extraction account identity')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');character=_character(db,owner,account)
        value=int(time.time()) if now is None else now
        if type(value) is not int or not 0<=value<2**40:raise ValueError('Force extraction epoch')
        old=_previous(db,operation,digest);items=load_items(db,owner)
        if old is not None:
            if db.execute('SELECT owner,kind FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()!=(owner,0x6ce):raise ValueError('Force extraction retry owner/kind')
            # A successful old6CF would remove a newly re-learned same pair.
            # Refuse that stale mutation; recover absolute inventory and the
            # full current unit D9 in LocalSession. This is local retry policy.
            from els_server.domain.fashion_state import move_ack
            from els_server.protocol.protocol_codec import Event
            bypos={(i['group'],i['slot']):i for i in items}
            events=[acknowledgement(result=-1),Event(0x201,kind=0x105,payload=move_ack([(p,bypos.get(p)) for p in old]))]
            for e in events:encode_event(e)
            return dict(replayed=True,events=events)
        pair=next((r for r in owned(db,owner) if (r['skill'],r['rank'])==(skill,rank)),None)
        if pair is None:raise ValueError('Extraction needs an exact owned grade')
        # This runtime has one persisted force preset. Check every saved slot,
        # including a hidden third slot; never implicitly unequip to extract.
        force_slots=slots(db,owner)
        from els_server.domain.boosting_2026_force_equipment import active_skill
        type20=active_skill(skill)
        if type20:
            from els_server.game_data import client_data
            if client_data().skill(skill)['m_eType']!=20:raise ValueError('Current original type20 extraction identity')
            if (skill,rank) in force_slots[:3]:raise ValueError('Force is equipped in a real passive slot')
        elif (skill,rank) in force_slots:raise ValueError('Force is equipped')
        # Historical type20 entries in the Mod/change section are invisible
        # compatibility references, not current native equipment. Read paths
        # retain them; only this explicit exact-pair6CE may release the FK.
        legacy_type20=type20 and (skill,rank) in force_slots[3:]
        if type20:
            row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(owner,)).fetchone()
            if row:
                import struct
                if len(row[0])!=88:raise ValueError('Saved ordinary skill preset size')
                if skill in struct.unpack('>22i',row[0]):raise ValueError('Force is equipped in ordinary hotbar')
        from els_server.domain.character_rules import CLASSES
        if CLASSES[character['unit_class']]['stage']<3 or character['level']<99:raise ValueError('Third job force extraction requirement')
        if character['revision']>=2**63-1:raise ValueError('Force character revision overflow')
        balance=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None or balance[1]>=2**63-1:raise ValueError('Force extraction balance revision')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        sources=[]
        for i in items:
            if i['template']!=EXTRACTOR or i['group']!=4:continue
            try:require_current(i,now=value);require_unlocked(i,now=value)
            except ValueError:continue
            sources.append(i)
        if not sources:raise ValueError('One current unlocked force extractor required')
        # Payload has no item UID; choose the first eligible owned bag slot.
        # This deterministic selection is explicit local inventory policy.
        source=min(sources,key=lambda i:(i['slot'],i['uid']));remaining=dict(source,count=source['count']-1) if source['count']>1 else None
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,source['uid']))
        else:
            from els_server.storage.item_expiration import forget
            from els_server.storage.item_locks import forget as forget_lock
            forget(db,source['uid']);forget_lock(db,source['uid'])
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_seals'").fetchone():db.execute('DELETE FROM item_seals WHERE item_uid=?',(source['uid'],))
            db.execute('DELETE FROM inventory_items WHERE owner=? AND uid=?',(owner,source['uid']))
        from els_server.domain.reward_rules import item_plan
        changed=_return_book(db,owner,pair)
        after=load_items(db,owner);bypos={(i['group'],i['slot']):i for i in after}
        positions=sorted({(source['group'],source['slot']),*((i['group'],i['slot']) for i in changed)})
        event=acknowledgement(skill,rank,[(p,bypos.get(p)) for p in positions]);encode_event(event)
        if legacy_type20:
            db.execute('DELETE FROM selected_2026_force_slots WHERE owner=? AND skill=? AND rank=? AND slot>=3',(owner,skill,rank))
        from els_server.domain.change_force_inventory import catalog as change_catalog
        table='career_box_common_force' if pair['template']==295734 else 'selected_2026_change_force_inventory' if pair['template'] in change_catalog(include_starters=True) else 'selected_2026_force_inventory'
        if db.execute(f'DELETE FROM {table} WHERE owner=? AND skill=? AND rank=?',(owner,skill,rank)).rowcount!=1:
            raise ValueError('Force extraction exact owned row disappeared')
        db.execute('UPDATE characters SET revision=revision+1 WHERE uid=?',(owner,));db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x6ce,positions,[i for i in items if (i['group'],i['slot']) in positions],[bypos[p] for p in positions if p in bypos])
        owned(db,owner);slots(db,owner)
        return dict(replayed=False,events=[event])


def _return_book(db,owner,pair):
    """One selected return, preserving seal history and exact stack identity.

    The generic acquisition allocator predates instance seal metadata and may
    merge into a different history. Keep this change local to selected forces.
    """
    from els_server.domain.boosting_2026_force_inventory import seal_used
    from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS,validate_item
    from els_server.domain.reward_rules import item_plan
    from els_server.storage.bag_capacity import allowances
    from els_server.storage.inventory_state import InventoryFull
    from els_server.storage.item_seals import assign
    used=seal_used(pair['template'],pair.get('seal_used',0))
    plan=item_plan(pair['template'],1);base={k:plan[k] for k in ('template','metadata','group')}
    if base['group']!=4 or base['metadata']!=0:raise ValueError('Selected returned force-book class')
    items=load_items(db,owner);cap=TEMPLATE_MAX_STACKS[pair['template']]
    for item in items:
        identity={k:v for k,v in item.items() if k not in ('uid','slot','count','sealed','seal_used')}
        if (identity==base and not item.get('sealed',False) and item.get('seal_used',0)==used and item['count']<cap):
            db.execute('UPDATE inventory_items SET count=count+1 WHERE uid=? AND owner=?',(item['uid'],owner))
            return [dict(item,count=item['count']+1)]
    occupied={i['slot'] for i in items if i['group']==4}
    slot=next((i for i in range(allowances(db,owner)[4]) if i not in occupied),None)
    if slot is None:raise InventoryFull('Selected force return needs matching history or a free special slot')
    uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
    if type(uid) is not int or not 1<=uid<2**63-1:raise ValueError('Force return UID sequence bound')
    item=dict(base,uid=uid,count=1,slot=slot)
    if used:item.update(sealed=False,seal_used=used)
    validate_item(item)
    db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
    db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(uid,owner,item['template'],item['metadata'],1,4,slot))
    if used:assign(db,owner,uid,False,used)
    return [item]
