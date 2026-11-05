"""Native 634 opener / 4CB Apply for permanent character customization.

Regression: the client stamps a single zero performer on 4CB (exactly like the
634 opener), but the handler's envelope guard demanded an empty performer list,
so every Apply was answered with result -1 and the 定制 window silently did
nothing. Evidence: state/wire-debug.log 11:21:09
`kind=0x4cb ... performers=(0,) ... payload 101 bytes` followed by a 72-byte
0x4CC frame (result + empty map).
"""
import sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain import character_custom as custom
from els_server.storage import character_custom as store
from els_server.protocol.protocol_codec import Event
from els_server.protocol.character_custom_messages import selection_map

OWNER=1001
BOOK=450000          # 无聊的艾索德 -> custom_id 11001, wait motion slot 1
CUSTOM_ID=11001
OTHER_CUSTOM=11002   # 勤修精进的艾索德, same family, never registered

def use_payload(uid):return struct.pack('>QQiiIB',uid,0,0,0,0,0)
def apply_event(slot,custom_id,sequence,performers=(0,)):
    value=custom.canonical(custom_id)
    return Event(0x202,performers=performers,kind=0x4cb,
                 payload=selection_map({slot:value})),sequence
def snap():
    with closing(sqlite3.connect(path)) as db:
        return store.snapshot(db,OWNER)
def result_of(events):
    assert events,events
    assert events[0].kind==0x4cc,events[0]
    return struct.unpack_from('>i',events[0].payload)[0]

with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'custom.sqlite3'
    account=LocalAccount(LocalState(path));account.enable_characters();account.get_inventory_snapshot()
    with closing(sqlite3.connect(path)) as db,db:
        # Match the reported save: 艾索德 3rd job (151/152) so the book's native
        # role mask and the career free-motion table are exercised for real.
        db.execute('UPDATE characters SET unit_class=152,level=99 WHERE uid=?',(OWNER,))
        role=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(OWNER,)).fetchone()
    assert role[0]==1 and role[1]==152,role
    with closing(sqlite3.connect(path)) as db,db:
        items=grant_items(db,[dict(template=BOOK,metadata=VERIFIED_TEMPLATES[BOOK],
            group=TEMPLATE_BAG_GROUPS[BOOK],quantity=1)])
    book=next(i for i in items if i['template']==BOOK)

    session=SimpleNamespace(client_build='dx11_260923',item_test=True,role='game',
        phase='town_ready',shop_session_id='custom-test',
        account=SimpleNamespace(characters=account.characters,
            store=SimpleNamespace(path=path,uid=OWNER),uid=OWNER,account_id=account.account_id))

    with patch('els_server.domain.dungeon_equipment_loot_flow.current_lease',lambda s:True), \
         patch('els_server.domain.avatar_set_flow.context',lambda s:object()), \
         patch('els_server.domain.avatar_set_flow.validate',lambda s,captured:None):

        # 1) Using the book registers it (0x219 -> 0x21A + 0x4CD).
        receipt=store.use_book(path,OWNER,account.account_id,use_payload(book['uid']),'book-1')
        assert receipt is not None and [e.kind for e in receipt['events']]==[0x21a,0x4cd],receipt
        assert snap()['owned']=={1:[custom.canonical(CUSTOM_ID)]},snap()

        # 2) The reported frame: slot 1 with the client's single zero performer.
        event,sequence=apply_event(1,CUSTOM_ID,221)
        events=custom.handle(session,event,sequence)
        assert result_of(events)==0,events
        assert [e.kind for e in events]==[0x4cc,0x18e],events
        selected=snap()['selected']
        assert selected=={1:custom.canonical(CUSTOM_ID)},selected

        # 3) An empty performer list (the older contract) stays accepted.
        event,sequence=apply_event(1,CUSTOM_ID,222)
        assert result_of(custom.handle(session,event,sequence))==0

        # 4) Wait-motion slots 2..4 share the same catalog and persist per slot.
        for sequence,slot,want in ((223,10,2),(224,11,3),(225,12,4)):
            event,sequence=apply_event(slot,CUSTOM_ID,sequence)
            events=custom.handle(session,event,sequence)
            assert result_of(events)==0,(slot,)
            # The reply carries the whole window state, not just this slot:
            # answering with one slot made the other rows fall back to the
            # career default, which read as "only one slot can be used".
            assert int.from_bytes(events[0].payload[4:8],'big')==want,events[0]
        selected=snap()['selected']
        assert sorted(selected)==[1,10,11,12],selected
        with closing(sqlite3.connect(path)) as db:
            rows=db.execute('SELECT slot,custom_id FROM character_custom_permanent_selection_slots '
                            'WHERE owner=? ORDER BY slot',(OWNER,)).fetchall()
        assert rows==[(10,CUSTOM_ID),(11,CUSTOM_ID),(12,CUSTOM_ID)],rows

        # 5) A customization that was never registered is still refused.
        event,sequence=apply_event(1,OTHER_CUSTOM,226)
        assert result_of(custom.handle(session,event,sequence))==-1

        # 6) Replaying the same operation is idempotent, not a second write.
        event,sequence=apply_event(1,CUSTOM_ID,221)
        events=custom.handle(session,event,sequence)
        assert result_of(events)==0 and [e.kind for e in events]==[0x4cc,0x18e],events

        # 7) The saved selection is what login replays: 0x18E carries the actor.
        character=dict(uid=OWNER,title=0,character_custom=snap())
        notices=custom.restored(character)
        assert len(notices)==1 and notices[0].kind==0x18e,notices
        assert int.from_bytes(notices[0].payload[:8],'big')==OWNER

        # 8) An empty slot makes the window send an empty map; echo, never fail.
        empty=Event(0x202,performers=(0,),kind=0x4cb,payload=bytes(4))
        events=custom.handle(session,empty,250)
        assert result_of(events)==0 and [e.kind for e in events]==[0x4cc],events
        assert snap()['selected']=={1:custom.canonical(CUSTOM_ID),10:custom.canonical(CUSTOM_ID),
                                   11:custom.canonical(CUSTOM_ID),12:custom.canonical(CUSTOM_ID)},snap()

        # 9) A native-only producer (CharCustomData entry, no bag book) is
        # registered directly and applies on its own slot family.
        rule=next(r for r in custom.catalog().values() if r['type']==20)
        with closing(sqlite3.connect(path)) as db,db:
            db.execute('INSERT OR IGNORE INTO character_custom_permanent VALUES (?,?,?)',
                       (OWNER,rule['custom_id'],rule['book']))
        event,sequence=apply_event(20,rule['custom_id'],260)
        assert result_of(custom.handle(session,event,sequence))==0
        assert snap()['selected'][20]==custom.canonical(rule['custom_id']),snap()

        # 10) The opener still answers with the empty cash catalog (0x635).
        opener=custom.handle(session,Event(0x202,performers=(0,),kind=0x634,payload=b''),300)
        assert [e.kind for e in opener]==[0x635],opener

print('character custom apply: PASS')
