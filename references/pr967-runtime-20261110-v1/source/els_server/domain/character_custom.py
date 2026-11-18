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

@functools.lru_cache(maxsize=1)
def _qualified_ids():
    """Every admissible permanent custom ID, built once per process.

    canonical() is called once per owned row by every snapshot/registration
    build (2900+ rows on a fully unlocked character), so rebuilding the ID set
    inline turned each of those into 2900 x 3200 set insertions.
    """
    return frozenset({0}|FREE_EMOTES|set(free_catalog().values())|{r['custom_id'] for r in catalog().values()})

@functools.lru_cache(maxsize=1)
def _type_index():
    """custom_id -> native CUSTOMIZING_TYPE, so custom_type() is not a scan."""
    return {r['custom_id']:r['type'] for r in catalog().values()}

def canonical(custom_id):
    if type(custom_id) is not int or custom_id not in _qualified_ids():
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

@functools.lru_cache(maxsize=1)
def _book_index():
    """custom_id -> the book template that grants it, built once per process."""
    return {r['custom_id']:r['book'] for r in catalog().values()}

def template_of(custom_id):
    """The item template a registration should name, or 0 for a free source.

    Both openers and the book path stamp this into 0x4CD so the window can
    resolve a selected row's name and icon; a free motion or emote has no item.
    """
    if custom_id in FREE_EMOTES or custom_id in free_catalog().values():return 0
    return _book_index().get(custom_id,0)

def custom_type(custom_id):
    canonical(custom_id)
    if custom_id==0:return None
    if custom_id in FREE_EMOTES:return 24
    if custom_id in free_catalog().values():return 1
    return _type_index()[custom_id]

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
    # Book-use follows the panel: the client opens the same custom window inside
    # a dungeon (panel_admitted already admits it), but registering a book there
    # answered -1 and the client renders nothing for -1, so it looked like the
    # use never happened. Storage still checks ownership, level/class and the
    # exact catalogued book, so the dungeon write lands on the same row.
    return (s.client_build=='dx11_260923' and s.item_test and s.role=='game'
            and s.phase in ('town_ready','dungeon_active')
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

def dungeon_entry(s,ticket=False):
    """The customisation burst that rides along with dungeon entry.

    This lives here instead of inside LocalSession on purpose. Storage's 0x4CB
    path resolves this module inside the function body, so a reload of this
    module takes effect on the next request; LocalSession itself can never be
    hot-reloaded because live sessions hold its class. Keeping the burst here
    means tuning it no longer needs a server restart or a dropped client.

    Returns ``(values, before_start, after_start, note)``:

    * ``values``       the member DTO's variable-length slot payload
    * ``before_start`` registrations, the selection ack and the actor notice,
                       emitted while the client is still in its town state so
                       its town handlers accept them
    * ``after_start``  an empty map followed by the full map, replayed once the
                       dungeon actor exists
    """
    import sqlite3
    from contextlib import closing
    from els_server.storage.character_custom import snapshot as store_snapshot
    from els_server.protocol.character_custom_messages import (
        acknowledgement,registered,selected_notice)

    def report(values,events,note,selected):
        # A silent empty tuple and a full set the client ignored look identical
        # in the game, so always record what was built.
        _trace('dungeon dto custom=%d events=%d %s ids=%r ticket=%r'
               %(len(values),len(events),note,sorted(set(values))[:4],ticket))
        if selected:_trace('dungeon reannounce empty->full slots=%d'%len(selected))

    account=getattr(s,'account',None)
    if not (getattr(s,'item_test',False) and getattr(account,'characters',None) is not None
            and getattr(account,'store',None) is not None):
        report((),(),'gate',{})
        return (),(),(),'gate'
    note='ok';values=();events=();after=();selected={}
    try:
        with closing(sqlite3.connect(account.store.path,timeout=10)) as db:
            db.execute('BEGIN')
            fresh=store_snapshot(db,account.uid)
        selected=dict(fresh['selected'])
        values=tuple(entry['custom_id'] for entry in selected.values()
                     if isinstance(entry,dict) and type(entry.get('custom_id'))is int
                     and entry['custom_id']>0)
        if values:
            # Selected rows only: one 4CD per owned row is thousands of events
            # on a fully unlocked save, and a burst that size is dropped whole.
            title=int(account.character().get('title',0) or 0)
            events=tuple([registered(value,0,family=slot)
                          for slot,value in sorted(selected.items())]
                         +[acknowledgement(selected),
                           selected_notice(account.uid,title,selected)])
            # The burst above paints the town actor; the dungeon actor is built
            # from the member DTO afterwards. Replaying an identical map was
            # measured inert, so announce an empty map first to rule out the
            # client returning early on "same selection as the one I hold".
            # The selector experiment is over: the 15:01:26 entry sent a third
            # frame with selector 1 (2141 bytes, `payload=2141 uid=1001
            # selector=1 title=12620 slots=21`) and the dungeon actor still
            # rendered career defaults, so 0 remains the only selector this
            # build answers to and the extra frame is gone.
            after=(selected_notice(account.uid,title,{}),
                   selected_notice(account.uid,title,selected))
    except (sqlite3.Error,ValueError,KeyError) as error:
        values=();events=();after=();selected={};note='read:%s'%type(error).__name__
    events=_live(events);after=_live(after)
    report(values,events,note,selected)
    return values,events,after,note

def _window_rows(s):
    """The messages a freshly opened window paints its rows from, split by order.

    The 635 opener only carries the published cash catalog, so a window opened
    in town showed every tab on the career default while the save already held
    the chosen border or motion. The rows were being replayed *after* the 635
    on the assumption that a live window absorbs later registrations; the two
    town screenshots of 20261108 disprove it. The panel listed the four saved
    cut-ins (ELS uniform / natural white swimsuit / April butler & maid /
    EL★STAR2 -- four distinct items in `character_custom_permanent_selection_slots`)
    as four identical "Immortal advanced skill cut-in" rows, the career default
    every row falls back to when it has no granting item. So the window builds
    its rows from whatever is registered at creation time: 4CD has to precede
    the 635.

    Returns ``(registrations, notices)``: the 4CD burst to emit *before* the
    opener, and the 4CC selection map plus 18E actor notice to emit after it.
    Read-only, and optional: if the store is unreadable the window still opens.
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
        if not selected:return [],[]
        title=int(s.account.character().get('title',0) or 0)
        # Only the selected values are registered here. A fully unlocked save
        # owns thousands (2902 on the live one), and replaying one 4CD per owned
        # row built a 145 KB burst that the client dropped whole: the window
        # opened on the career defaults. The owned map already reaches the
        # client in 2A, so the opener only has to make the *chosen* rows
        # resolvable.
        registrations=[registered(value,0,family=slot) for slot,value in sorted(selected.items())]
        # Compact here, not after the encode probe below: while 0x18E is
        # suppressed `selected_notice` is None, and `encode_event(None)` would
        # raise inside the probe, whose fallback returns ([], []) -- the window
        # would then open with no registrations at all.
        notices=[event for event in (acknowledgement(selected),selected_notice(s.account.uid,title,selected))
                 if event is not None]
        # The opener reply carries all of this in one frame burst; an event that
        # only fails at encode time would take the whole reply down with it,
        # including the 635 the window is waiting for. Prove each one here and
        # fall back to the bare opener instead of dying in the writer.
        from els_server.protocol.protocol_codec import encode_event
        for event in registrations+notices:encode_event(event)
        # Record the row-type byte we actually put on the wire for every row.
        # `payload[4]` is the byte right after the granting-item i32, i.e. the
        # value the client buckets the row by. It has to equal the row's own
        # slot; a folded family byte instead is what made every multi-slot tab
        # paint its 2nd..4th row with the career default (2026-11-08).
        rows=[(slot,event.payload[4])for (slot,_),event in zip(sorted(selected.items()),registrations)]
        _trace('opener replay owned=%d slots=%d registered=%d rows=%s'
               %(sum(len(v) for v in owned.values()),len(selected),len(registrations),
                 ' '.join('%d:%d'%row for row in rows)))
        return registrations,notices
    except Exception as error:
        _trace('opener selection unavailable: %r'%error)
        return [],[]

def _live(events):
    """Drop the suppressed 0x18E placeholders (see character_custom_messages).

    `selected_notice` returns None while ELS_ENABLE_18E_NOTICE is off, so every
    list of notices has to be compacted before it reaches the wire.
    """
    return tuple(event for event in events if event is not None)


def _split_notices(notices):
    """Divide the opener tail into "must precede the 635" and "must follow it".

    Measured 2026-11-08 16:15: the window lists every owned cut-in in its row
    dropdown (so the 4CD replay reaches the manager) but every row still paints
    the career default. The dropdown proves registration works; what the row
    *shows* is the manager's current selection, and the window reads that when
    the 635 creates it. The 18E selection map used to be emitted after the 635,
    i.e. after the rows had already been painted, and an Apply re-sends the same
    three frames into an already-built window, which is why one Apply never
    changed a row. 18E therefore goes before the opener; the 4CC Apply reply
    stays after it.
    """
    before=[event for event in notices if event is not None and event.kind==0x18e]
    after=[event for event in notices if event is not None and event.kind!=0x18e]
    return before,after

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
                # Selected rows only. One 4CD per owned row is 2902 events on a
                # fully unlocked save, and the client drops such a burst whole -
                # the window then opens on the career defaults. There is no
                # other carrier in the dungeon reply, so both openers replay the
                # same shape.
                registrations=[registered(value,0,family=slot) for slot,value in sorted(selected.items())]
                notices=[]
                if selected:
                    notices=[event for event in (acknowledgement(selected),
                             selected_notice(s.account.uid,int(character.get('title',0) or 0),selected))
                             if event is not None]
                before,after=_split_notices(notices)
                events=registrations+before+opening_info(s.account.store.path,s.account.uid,s.account.account_id)+after
                rows=[(slot,event.payload[4])for (slot,_),event in zip(sorted(selected.items()),registrations)]
                _trace('opener ok phase=dungeon owned=%d slots=%d rows=%d notices=%d bytes=%s'
                       %(sum(len(v) for v in owned.values()),len(selected),len(registrations),len(notices),
                         ' '.join('%d:%d'%row for row in rows)))
                return events
            from els_server.domain.avatar_set_flow import context,validate
            captured=context(s)
            registrations,notices=_window_rows(s)
            # Order matters: the 4CD rows exist before the window is created,
            # the 18E selection map goes in before the 635 reads it (see
            # _split_notices), and the 4CC Apply reply follows it.
            before,after=_split_notices(notices)
            events=registrations+before+opening_info(s.account.store.path,s.account.uid,s.account.account_id,validate=lambda:validate(s,captured))+after
            _trace('opener ok rows=%d notices=%d'%(len(registrations),len(notices)))
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
    # Which login reply this fired in is the whole question right now: the town
    # actor never takes the selection, and the 0x18E used to go out only on the
    # 0x227 "actor ready" ack, i.e. after the actor already exists. The 0x28
    # reply now carries one right behind 0x2A as well, so both calls are logged
    # with their slot count to tell them apart in state/custom.log.
    _trace('custom notice uid=%r slots=%d'%(character.get('uid'),len(values)))
    if not values:return []
    return _live([selected_notice(character['uid'],character.get('title',0),values)])
