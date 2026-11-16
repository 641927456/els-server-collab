"""Native104/105 wearing: owned positions, stable UIDs and connection receipts."""
from els_server.storage.item_actor import require_active_character
import hashlib,json,sqlite3,struct,uuid
from contextlib import closing
from els_server.domain.inventory_items import validate_item,FASHION_EQUIP_SLOTS,TEMPLATE_BAG_GROUPS
from els_server.domain.normal_equipment import definitions as normal_definitions
from els_server.domain.ordinary_accessories import definitions as accessory_definitions
from els_server.domain.equipment_requirements import catalog as requirements
from els_server.domain.fashion_state import move_ack
from els_server.domain.bag_capacity import wire_limit
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.bag_capacity import allowances

_DBG=str(__import__('pathlib').Path(__file__).resolve().parents[2]/'state'/'wear-debug.log')

def _dbg(text):
    # TEMPORARY: state/ is gitignored. Remove once 104 is settled.
    try:
        import time
        with open(_DBG,'a',encoding='utf-8') as handle:handle.write(time.strftime('%H:%M:%S ')+text+'\n')
    except Exception:pass


def _bag_group_ok(template,group):
    # Legacy rows may still hold an avatar piece on the sibling avatar page, so
    # a move that starts from such a row has to stay usable; where a piece lands
    # is decided by fashion_slot/swap_slot, which always file it on its own page.
    native=TEMPLATE_BAG_GROUPS[template]
    if template in FASHION_EQUIP_SLOTS and native in (7,27) and group in (7,27):return True
    return group==native

def request_positions(payload):
    if not isinstance(payload,bytes) or len(payload)!=11:raise ValueError('Wear request length')
    sg,ss,dg,ds,flag=struct.unpack('>BiBiB',payload);positions=((sg,ss),(dg,ds))
    slots=set(requirements()[1].values())|set(FASHION_EQUIP_SLOTS.values())|{s for r in accessory_definitions().values() for s in r['slots']}
    # A bag slot of -1 is the client's own "I no longer know that cell" mark: it
    # is what it sends for a piece it painted from a layout the server has since
    # re-filed. The move rules resolve such a side by the piece itself, so the
    # bound check has to let the marker through.
    if flag or positions[0]==positions[1] or any(not (g in (1,2,7,27) and (0<=s<wire_limit(g) or s==-1) or g==9 and s in slots) for g,s in positions):raise ValueError('Wear request positions')
    if sg!=dg and sg!=9 and dg!=9 and not (sg in (7,27) and dg in (7,27)):
        # A pure bag rearrangement stays inside one tab; the exception is an
        # avatar piece that drifted onto the sibling avatar page, where moving it
        # to its own page is the re-filing the client's own rule would have done.
        raise ValueError('Wear bag classification')
    return positions

def require_wearable(item,character):
    if item.get('sealed',False):raise ValueError('Unseal equipment before wearing')
    t=item['template']
    if t in normal_definitions():
        from els_server.domain.equipment_instance import require_wearable as require_normal
        require_normal(item,character)
    elif t in accessory_definitions():
        from els_server.domain.ordinary_accessories import require_wearable as require_accessory
        require_accessory(item,character)
    elif t in FASHION_EQUIP_SLOTS:
        from els_server.game_data import client_data
        from els_server.domain.equipment_requirements import class_matches
        raw=client_data().item(t)['record']
        if raw[0xd2] and raw[0xd2]!=character['unit_type'] or not class_matches(character['unit_class'],raw[0xd3]):raise ValueError('Fashion character requirement')
        if raw[8]&4 and character['unit_type']!=10:raise ValueError('Companion fashion requirement')
    else:raise ValueError('Outside ordinary wearable scope')

def move(path,payload,uid,**options):
    try:response=_move(path,payload,uid,**options)
    except Exception as error:
        _dbg('104 uid=%s req=%s REJECT %s: %s'%(uid,payload.hex() if isinstance(payload,bytes) else payload,type(error).__name__,error))
        raise
    _dbg('104 uid=%s req=%s OK ack=%dB'%(uid,payload.hex(),len(response)))
    return response

def _move(path,payload,uid,*,account_id,session_id,sequence,validate=lambda:None,notice=None):
    uid=character_uid(uid);source,destination=request_positions(payload)
    if type(account_id) is not int or account_id<=0 or type(session_id) is not str:raise ValueError('Wear account/session')
    connection=uuid.UUID(session_id)
    if connection.version!=4 or str(connection)!=session_id or type(sequence) is not int or not 1<=sequence<2**32:raise ValueError('Wear operation identity')
    operation=session_id+':wear104:'+str(uid)+':'+str(sequence)
    digest=hashlib.sha256(struct.pack('>Q',uid)+payload).hexdigest();positions_json=json.dumps((source,destination),separators=(',',':'))
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,uid);validate()
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Wear owner mismatch')
        row=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(uid,)).fetchone()
        if row is None:raise ValueError('Wear character missing')
        character=dict(unit_type=row[0],unit_class=row[1],level=row[2])
        from els_server.game_data import client_data
        if client_data().unit(character['unit_class'])['unitType']!=character['unit_type']:raise ValueError('Wear actor class identity')
        limits=allowances(db,uid)
        if any(g!=9 and s>=limits[g] for g,s in (source,destination)):raise ValueError('Wear unowned bag position')
        before=load_items(db,uid);positions={(i['group'],i['slot']):i for i in before}
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wear_move_receipts'").fetchone()
        old=db.execute('SELECT owner,account_id,request_hash,positions_json FROM wear_move_receipts WHERE operation_id=?',(operation,)).fetchone() if exists else None
        if old is not None:
            if old!=(uid,account_id,digest,positions_json):raise ValueError('Wear receipt conflict')
            response=move_ack([(source,positions.get(source)),(destination,positions.get(destination))]);validate()
            if notice is not None:
                for position in dict.fromkeys((source,destination)):
                    notice.append((positions.get(position),position))
            return response
        reported=source
        first,second=positions.get(source),positions.get(destination)
        if source[0] in (7,27) and destination[0]==9 and (
                first is None or FASHION_EQUIP_SLOTS.get(first['template'],destination[1])!=destination[1]):
            # The page slot a client reports drifts from the persisted slot as
            # soon as grants or the login re-filing reorder the tab, and the
            # drift can land on an empty slot or on a different body part. Both
            # shapes mean the same thing on the wire - "wear the piece that
            # belongs to this equipment slot" - so resolve the source by the
            # destination slot: the reported page first, then its sibling page,
            # nearest slot to the reported one.
            best=None
            for group in (source[0],27 if source[0]==7 else 7):
                for (g,s),item in positions.items():
                    if g!=group or FASHION_EQUIP_SLOTS.get(item['template'])!=destination[1]:continue
                    try:
                        # Only consider a candidate that can really go there: a
                        # handful of templates carry both an ordinary and an
                        # avatar equip slot, and a bag can hold pieces this
                        # character cannot wear.
                        require_wearable(validate_item({**item,'group':9,'slot':destination[1]}),character)
                    except ValueError:continue
                    key=(group!=source[0],abs(s-source[1]),s)
                    if best is None or key<best[0]:best=(key,(g,s),item)
            if best is not None:source,first=best[1],best[2]
        if first is None and source[0] in (7,27) and source[1]<0 and destination[0] in (7,27):
            # Unknown cell on a bag page, dropped onto the sibling avatar page:
            # that is a drifted piece being sent home. Take the one piece on the
            # reported page whose own page is the destination, and only when it
            # is unambiguous.
            fits=[(g,s) for (g,s),item in positions.items()
                  if g==source[0] and TEMPLATE_BAG_GROUPS.get(item['template'])==destination[0]]
            if len(fits)==1:source=fits[0];first=positions[source]
        if first is None:raise ValueError('Wear empty source')
        # From here on the reported cell has to be a real one: a -1 marker cannot
        # be echoed back in the105 vector or in the inventory rows, and the cell
        # the move really emptied is the resolved source.
        if reported[1]<0:reported=source
        # Re-filing a drifted avatar piece onto its own page: the piece the drop
        # landed on is already filed correctly, so it stays put instead of being
        # pushed onto a page it does not belong to.
        refile=(source[0] in (7,27) and destination[0] in (7,27) and source[0]!=destination[0]
                and TEMPLATE_BAG_GROUPS.get(first['template'])==destination[0])
        if refile:second=None
        from els_server.domain.item_expiration import require_current
        for item,position in ((first,source),(second,destination)):
            if item is None:continue
            require_current(item)
            t=item['template'];bag_only=source[0]==destination[0] and source[0]!=9
            if t not in normal_definitions() and t not in accessory_definitions() and t not in FASHION_EQUIP_SLOTS:
                # Existing artifact/chip bag1 rearrangement remains available.
                from els_server.domain.artifact_progression import slots as artifact_slots
                from els_server.domain.equipment_chip_rules import material as chip_material
                if not (bag_only and source[0]==1 and (artifact_slots(t) or chip_material(t))):raise ValueError('Wear item scope')
            if position[0]!=9 and not _bag_group_ok(t,position[0]):raise ValueError('Wear item bag classification')
        def fashion_slot(item,group,slot):
            # Native fashion lives in bag 7 or bag 27. A piece only has to move
            # when the requested page is not its own or the requested cell is
            # unknown (the client's -1 mark); on its own page the cell is used
            # as asked, occupied or not, because the other side of the move is
            # what swaps out of it.
            want=TEMPLATE_BAG_GROUPS[item['template']]
            if group not in (7,27):return group,slot
            relocate=slot<0 or group!=want
            if relocate and (slot<0 or positions.get((want,slot)) not in (None,item)):
                slot=next((n for n in range(limits[want]) if (want,n) not in positions),None)
                if slot is None:raise ValueError('Outgoing item bag is full')
            return want,slot
        def swap_slot(item):
            # The outgoing piece returns to the exact cell the client painted,
            # but only when that cell sits on the piece's own avatar page - the
            # reported cell can be on the sibling page, and honouring it is how
            # an ordinary avatar piece ended up filed in the cash tab. Same slot
            # on its own page first, otherwise the first free one. A105 reply may
            # only name the cells it was asked about, so a relocation is covered
            # by the absolute inventory rows the caller forwards.
            native=TEMPLATE_BAG_GROUPS[item['template']]
            vacant=lambda g,s:(g,s) not in positions or positions[(g,s)] is first
            for group,slot in ((reported[0],reported[1]),(source[0],source[1])):
                if group==native and vacant(group,slot):return group,slot
            group,slot=reported if reported[0] in (7,27) else source
            return fashion_slot(item,group,slot)
        mg,ms=fashion_slot(first,destination[0],destination[1])
        if refile and positions.get((mg,ms)) not in (None,first):
            # The cell the drop landed on holds a correctly filed piece that is
            # staying put, so the piece being sent home takes the first free one
            # instead of pushing it back onto the wrong page.
            ms=next((n for n in range(min(limits[mg],wire_limit(mg))) if (mg,n) not in positions),None)
            if ms is None:raise ValueError('Own avatar bag is full')
        moved=validate_item({**first,'group':mg,'slot':ms})
        swapped=None;swap_pos=(reported,None) if reported not in positions else (source,None)
        if second is not None:
            group,slot=swap_slot(second)
            swapped=validate_item({**second,'group':group,'slot':slot});swap_pos=((group,slot),swapped)
        for item in (moved,swapped):
            if item and item['group']==9:require_wearable(item,character)
        from els_server.domain.ring_wear import require_compatible
        projected={i['uid']:i for i in before};projected.update({i['uid']:i for i in (moved,swapped) if i})
        for item in (moved,swapped):
            if item:require_compatible(item,projected.values())
        # When the resolved source is not the reported slot, clear that slot only
        # if it is really empty now; a drift can also have pointed at a different
        # piece, which has to stay where it is.
        _dbg('104 %s reported=%s resolved=%s dest=%s -> %r'%(character,
            reported,source,destination,[swap_pos,(destination,moved)]))
        # Exactly two records, at the two positions the request named - the same
        # shape move_bag_items replies with. The client repaints from these, so
        # an extra record for a slot it never asked about made an accepted swap
        # look like nothing happened.
        response=move_ack([swap_pos,(destination,moved)]);validate()
        from els_server.storage.spell_socket_pending import invalidate_moved
        invalidate_moved(db,uid,[first,second],[moved,swapped])
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_engrave_previews'").fetchone():
            db.execute('DELETE FROM equipment_engrave_previews WHERE item_uid IN (SELECT uid FROM inventory_items WHERE owner=? AND uid IN (?,?))',(uid,first['uid'],second['uid'] if second else 0))
        for item in (first,second):
            if item and db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',(-item['uid'],item['uid'],uid)).rowcount!=1:raise ValueError('Wear retained UID owner')
        for item in (moved,swapped):
            if item and db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=? AND owner=?',(item['group'],item['slot'],item['uid'],uid)).rowcount!=1:raise ValueError('Wear position owner')
        after=load_items(db,uid);expected={i['uid']:i for i in before};expected.update({i['uid']:i for i in (moved,swapped) if i})
        if expected!={i['uid']:i for i in after}:raise ValueError('Wear changed item state')
        db.execute("CREATE TABLE IF NOT EXISTS wear_move_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL CHECK(length(request_hash)=64),positions_json TEXT NOT NULL)")
        db.execute('INSERT INTO wear_move_receipts VALUES (?,?,?,?,?)',(operation,uid,account_id,digest,positions_json));validate()
        if notice is not None:
            # Absolute final rows for every cell this move really changed. The105
            # vector is matched against the request, so a cell that changed but
            # was not asked about (the piece being filed on its own avatar page
            # instead of the requested page) leaves the client holding a phantom
            # there and the next click on it resolves to nothing. Callers forward
            # this as the plain inventory updater, which overwrites by position.
            # Only the cells the two pieces actually left or reached are named:
            # an empty row for a cell that still holds an untouched piece would
            # erase it from the client's tab.
            landed={}
            for item in (moved,swapped):
                if item:landed[(item['group'],item['slot'])]=item
            emptied={(item['group'],item['slot']) for item in (first,second) if item is not None}
            touched=(reported,source,destination,swap_pos[0],
                (moved['group'],moved['slot']),
                (swapped['group'],swapped['slot']) if swapped else None)
            for position in dict.fromkeys(p for p in touched if p is not None):
                # A cell that held nothing before the move can always be sent as
                # empty: it also clears the phantom the client painted there from
                # a layout the server had already re-filed.
                if landed.get(position) is not None or position in emptied or position not in positions:
                    notice.append((landed.get(position),position))
        return response
