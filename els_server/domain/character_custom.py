"""Existing-source permanent Elsword motions/emotes and finite non-LuCiel faces.

The client owns the UI, motion, model and effect behavior. This module admits
only primary book IDs in the reviewed current qualified local ED catalog.
"""
import functools,hashlib,json,os,time
from pathlib import Path

DATE1='2001-01-01 00:00:00'
DATE2='2050-01-01 00:00:00'
# Native CUSTOMIZING_TYPE: wait motion owns slots 1/10/11/12, the face slot 2,
# skill cut-ins 3..6, hyper effect 15, skill frame 16, sitting motion 7/8/13/14,
# portrait 19, quick voices 20..23 and point marks 28. Each block shares one
# catalog family, exactly like the four wait-motion slots.
SLOT_TYPES={1:1,10:1,11:1,12:1,2:2,3:3,4:3,5:3,6:3,15:15,16:16,7:7,8:7,13:7,14:7,
            19:19,20:20,21:20,22:20,23:20,24:24,25:24,26:24,27:24,28:28}
FACE_UNITS=frozenset({1,2,3,4,5,6,7,8,9,11,12,13,14,15})
# Every playable unit shares the same native CharCustomData families; the
# per-book character restriction is carried by the item record (raw[210]),
# so the catalog admits all units and the use path enforces the record.
ALL_UNITS=frozenset(range(1,16))
COUNTS={1:855,2:321,3:289,7:1502,15:46,16:9,19:39,20:56,24:71,28:12}
BOOK_COUNT=3200
# Families whose producers exist only in the native CharCustomData table; no
# verified bag book can grant them, so they admit direct registration alone.
NATIVE_ONLY_FAMILIES=frozenset((3,15,16,19,20,28))
FREE_EMOTES=frozenset({17000,17033,17034,17035,17036})

@functools.lru_cache(maxsize=1)
def catalog():
    data=json.loads((Path(__file__).parents[1]/'data/character_custom_permanent.json').read_text(encoding='utf8'))
    if (data['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709' or len(data['books'])!=BOOK_COUNT
        or data['free_emote_ids']!=sorted(FREE_EMOTES)):
        raise ValueError('Permanent custom catalog identity')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    from els_server.game_data import client_data
    native=client_data()
    rules={}
    for r in data['books']:
        if (type(r['book']) is not int or type(r['custom_id']) is not int or r['book'] in rules
            or r['type'] not in COUNTS or r['slot']!=r['type']
            or r['unit_type'] not in (FACE_UNITS if r['type']==2 else ALL_UNITS)):
            raise ValueError('Permanent custom catalog qualification')
        if r.get('native_only'):
            # The producer exists only in the native table; pin it to the live
            # client item record instead of an inventory book classification.
            if r['type'] not in NATIVE_ONLY_FAMILIES or r['book'] in VERIFIED_TEMPLATES:
                raise ValueError('Permanent custom native source qualification')
            raw=native.item(r['book'])['record']
            if hashlib.sha256(raw).hexdigest()!=r['native_item_sha256']:
                raise ValueError('Permanent custom native item drift')
        elif (r['book'] not in VERIFIED_TEMPLATES or TEMPLATE_BAG_GROUPS[r['book']]!=4):
            raise ValueError('Permanent custom catalog qualification')
        rules[r['book']]=r
    if (len({r['custom_id'] for r in rules.values()})!=BOOK_COUNT
        or len(rules)!=BOOK_COUNT
        or {t:sum(r['type']==t for r in rules.values())for t in COUNTS}!=COUNTS
        or {0,*FREE_EMOTES,*free_catalog().values()}&{r['custom_id']for r in rules.values()}):raise ValueError('Permanent custom ID ambiguity')
    return rules

def canonical(custom_id):
    if type(custom_id) is not int or custom_id not in ({0}|FREE_EMOTES|set(free_catalog().values())|{r['custom_id'] for r in catalog().values()}):
        raise ValueError('Unqualified permanent custom ID')
    return dict(custom_id=custom_id,ability=0,date1=DATE1,date2=DATE2,variant=1)

@functools.lru_cache(maxsize=1)
def free_catalog():
    data=json.loads((Path(__file__).parents[1]/'data/character_custom_permanent.json').read_text(encoding='utf8'))
    values={int(k):v for k,v in data['free_by_class'].items()}
    from els_server.domain.character_rules import CLASSES
    if len(values)!=13 or len(set(values.values()))!=13 or any(CLASSES[k]['base_class']!=1 or type(v) is not int for k,v in values.items()):
        raise ValueError('Elsword free-motion source qualification')
    return values

def selection_type(slot):
    if type(slot) is not int or slot not in SLOT_TYPES:raise ValueError('Unsupported custom selected slot')
    return SLOT_TYPES[slot]

def custom_type(custom_id):
    canonical(custom_id)
    if custom_id==0:return None
    if custom_id in FREE_EMOTES:return 24
    if custom_id in free_catalog().values():return 1
    return next(r['type']for r in catalog().values()if r['custom_id']==custom_id)

def slot_value(slot,value):
    family=selection_type(slot)
    if value!=canonical(value.get('custom_id')) or (value['custom_id']==0 and family in (2,24)) or custom_type(value['custom_id']) not in (None,family):
        raise ValueError('Custom selected slot/family mismatch')
    return value

def free_ids(unit_class,slot=1):
    # Current11F2CB0/UI suppresses this career's own free row; ID0 is the
    # native current-career default. Prior career free motions remain selectable.
    from els_server.domain.careers import PARENTS
    from els_server.domain.character_rules import CLASSES
    if slot==2:return set()  # No face free/default producer admitted.
    family=selection_type(slot)
    if family==7:return {0}
    if family==24:return set(FREE_EMOTES)
    if family in NATIVE_ONLY_FAMILIES:return {0}
    if unit_class not in free_catalog():
        # Careers outside the reviewed Elsword free-motion table (Eve, Ain,
        # Laby and the rest) have no producer for a free default row, so only
        # the native current-career default ID 0 stays selectable.
        return {0}
    values={0};seen=set();current=unit_class
    for _ in range(CLASSES[unit_class]['stage']):
        if current in seen:raise ValueError('Custom career ancestry cycle')
        seen.add(current);current=PARENTS[current];values.add(free_catalog()[current])
    return values

def admitted(s):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    return (s.client_build=='dx11_260923' and s.item_test and s.role=='game' and s.phase=='town_ready'
            and s.account.characters is not None and s.account.store is not None and current_lease(s))

def panel_admitted(s):
    """The CharInfo opener only. Keeps the village-only Apply gate untouched.

    The client also opens the same window inside a dungeon; refusing it leaves
    the panel rendering the freshly built actor's career defaults."""
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    return (s.client_build=='dx11_260923' and s.item_test and s.role=='game'
            and s.phase in ('town_ready','dungeon_active')
            and s.account.characters is not None and s.account.store is not None and current_lease(s))

def _trace(message):
    # state/ is gitignored; this is the only view we get of the client's Apply.
    try:
        root=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root,'state','custom.log'),'a',encoding='utf-8') as handle:
            handle.write('%s %s\n'%(time.strftime('%H:%M:%S'),message))
    except Exception:pass

def _envelope(event,sequence,performers=((),(0,))):
    """Native envelope. The audited 634 opener stamps exactly one zero
    performer; the 4CB Apply of the same build also stamps (0,), which the
    original guard read as "non-empty" and answered with -1."""
    return (event.event_id==0x202 and type(sequence)is int and 1<=sequence<2**32
            and event.performers in performers and event.uid==2**64-1
            and event.target_uid==2**64-1 and event.payload_mode==0)

def _replay_selection(s):
    """The three messages a freshly opened window paints its rows from.

    The 635 opener only carries the published cash catalog, so a window opened
    in town showed every tab on the career default while the save already held
    the chosen border or motion: the game itself had applied it through the
    login 18E, the panel just never heard about it. Replay what the dungeon
    opener in this same handler already sends: the 4CD registration of every
    owned value, the 4CC map the rows use and the 18E actor notice. Read-only,
    and optional: if the store is unreadable the window still opens.
    """
    try:
        from contextlib import closing
        import sqlite3
        from els_server.protocol.character_custom_messages import (
            acknowledgement,registered,selected_notice)
        from els_server.storage.character_custom import snapshot as store_snapshot
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            db.execute('BEGIN')
            fresh=store_snapshot(db,s.account.uid)
        owned=fresh['owned'];selected=dict(fresh['selected'])
        if not selected:return []
        title=int(s.account.character().get('title',0) or 0)
        return ([registered(value) for family in sorted(owned) for value in owned[family]]
                +[acknowledgement(selected),selected_notice(s.account.uid,title,selected)])
    except Exception as error:
        _trace('opener selection unavailable: %r'%error)
        return []

def handle(s,event,sequence):
    if event.kind==0x634:
        # Original CharInfo opener requests cash purchase availability, not
        # registered ownership, inventory books or an application permission.
        if (event.event_id!=0x202 or event.payload
            or not _envelope(event,sequence,((0,),)) or not panel_admitted(s)):
            _trace('opener rejected phase=%r role=%r performers=%r uid=%#x mode=%r len=%d'
                   %(getattr(s,'phase',None),getattr(s,'role',None),tuple(event.performers or ()),
                     event.uid,event.payload_mode,len(event.payload or b'')))
            return []
        try:
            from els_server.storage.character_custom import opening_info
            if getattr(s,'phase',None)=='dungeon_active':
                # The same native window opens inside a dungeon, but there is no
                # village context to validate against, and the dungeon actor is
                # built from the FullUser member DTO: no owned set, no selection.
                # Read the save directly instead of the session's cached role
                # projection (that copy predates later registrations), then replay
                # the 0x4CD capacity notices the book path emits, the 0x4CC Apply
                # reply the rows use and the 0x18E actor notice. Read-only.
                from contextlib import closing
                import sqlite3
                from els_server.protocol.character_custom_messages import (
                    acknowledgement,registered,selected_notice)
                from els_server.storage.character_custom import snapshot as store_snapshot
                character=s.account.character()
                with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
                    db.execute('BEGIN')
                    fresh=store_snapshot(db,s.account.uid)
                owned=fresh['owned'];selected=dict(fresh['selected'])
                capacity=[registered(value) for family in sorted(owned) for value in owned[family]]
                notices=list(capacity)
                if selected:
                    notices.append(acknowledgement(selected))
                    notices.append(selected_notice(s.account.uid,int(character.get('title',0) or 0),selected))
                events=notices+opening_info(s.account.store.path,s.account.uid,s.account.account_id)
                _trace('opener ok phase=dungeon owned=%d slots=%d notices=%d'
                       %(len(capacity),len(selected),len(notices)))
                return events
            from els_server.domain.avatar_set_flow import context,validate
            captured=context(s)
            events=_replay_selection(s)+opening_info(s.account.store.path,s.account.uid,s.account.account_id,validate=lambda:validate(s,captured))
            _trace('opener ok')
            return events
        except ValueError as error:
            _trace('opener failed: %s'%error)
            return []
    if event.event_id!=0x202 or event.kind!=0x4cb:return None
    from els_server.protocol.character_custom_messages import acknowledgement
    if not _envelope(event,sequence) or not panel_admitted(s):
        _trace('apply rejected envelope/phase=%r lease=%r performers=%r'
               %(getattr(s,'phase',None),getattr(s,'role',None),tuple(event.performers or ())))
        return [acknowledgement(result=-1)]
    if event.payload==bytes(4):
        # A slot with no value makes the window send an empty selection map.
        # The old decode refused it, so that slot's Apply looked dead. Echo the
        # current projection instead: nothing is written, nothing is lost.
        try:
            import sqlite3
            from contextlib import closing
            from els_server.storage.character_custom import snapshot as custom_snapshot
            with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
                current=custom_snapshot(db,s.account.uid)['selected']
        except Exception as error:
            _trace('apply empty selection unreadable: %s'%error)
            current={}
        _trace('apply empty selection -> echo %d slots'%len(current))
        return [acknowledgement(current)]
    from els_server.storage.character_custom import select
    try:
        # Reuse the existing stable village/actor generation contract. This is
        # independent of avatar presets; no preset business action is invoked.
        if getattr(s,'phase',None)=='dungeon_active':
            # Same window, no village context to capture. select() still checks
            # ownership against the saved catalog before it writes anything, so
            # only the village-lease guard is skipped here.
            result=select(s.account.store.path,s.account.uid,s.account.account_id,event.payload,
                          s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence))
            slot=event.payload[4];value=int.from_bytes(event.payload[5:9],'big',signed=True)
            _trace('apply ok (dungeon) slot=%d custom=%d replayed=%r'%(slot,value,result['replayed']))
            return result['events']
        from els_server.domain.avatar_set_flow import context,validate
        captured=context(s)
        result=select(s.account.store.path,s.account.uid,s.account.account_id,event.payload,
                      s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence),validate=lambda:validate(s,captured))
        slot=event.payload[4];value=int.from_bytes(event.payload[5:9],'big',signed=True)
        _trace('apply ok slot=%d custom=%d replayed=%r'%(slot,value,result['replayed']))
        return result['events']
    except ValueError as error:
        _trace('apply failed slot=%r payload=%s: %s'
               %(event.payload[4] if len(event.payload)>4 else None,event.payload[:13].hex(),error))
        return [acknowledgement(result=-1)]

def require_admitted(s):
    if admitted(s):return
    # The client renders nothing when a book use is refused, and this same
    # admission also gates the panel, so record which clause refused it.
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    try:lease=bool(current_lease(s))
    except Exception:lease='ERR'
    _trace('book not admitted build=%r item_test=%r role=%r phase=%r characters=%r store=%r lease=%r'%(
        getattr(s,'client_build',None),getattr(s,'item_test',None),getattr(s,'role',None),
        getattr(s,'phase',None),getattr(getattr(s,'account',None),'characters',None) is not None,
        getattr(getattr(s,'account',None),'store',None) is not None,lease))
    raise ValueError('Custom book requires current DX11 town game lease')

def restored(character):
    from els_server.protocol.character_custom_messages import selected_notice
    values=character.get('character_custom',{}).get('selected',{})
    if not values:return []
    return [selected_notice(character['uid'],character.get('title',0),values)]
