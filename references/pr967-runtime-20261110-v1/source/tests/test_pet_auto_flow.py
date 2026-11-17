"""Pet automatic slots accept ordinary recovery potions and consume them.

Covers the reported symptom: a native 0x8A1 type-2 map for ordinary potions was
answered with result -1, so the slot stayed empty. Admission is now driven by
the pinned effect vector, both slots accept proportional recovery, and 0x65E
consumes the registered potion in town, field and dungeon.
"""
import sqlite3,struct,sys,tempfile,time
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.companion_state import handle as companion
from els_server.storage.pet_support import handle as support,automatic
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.quick_bindings import item_binding
from els_server.protocol.protocol_codec import Event

def use(item,pet=0):return struct.pack('>QQiiIB',item,pet,0,0,0,0)
def bindings(hp,mp):return struct.pack('>iIiiii',2,2,0,hp,1,mp)
def auto_use(slot):return struct.pack('>HBBB',slot,0,0,0)
def result(event):return struct.unpack_from('>i',event.payload)[0]

with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'petauto.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters();a.get_inventory_snapshot()
    with closing(sqlite3.connect(path)) as db,db:
        items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)
            for t,n in ((550427,1),(164566,1),(330562,1),(79063,5),(79064,5),(130165,3),(78360,2))])
    pet_item=next(i for i in items if i['template']==550427)
    expand=next(i for i in items if i['template']==164566)
    upgrade=next(i for i in items if i['template']==330562)
    bread=next(i for i in items if i['template']==79063)     # 13 proportional HP
    juice=next(i for i in items if i['template']==79064)     # 19 proportional MP
    elixir=next(i for i in items if i['template']==130165)   # 13+19 HP/MP
    orb=next(i for i in items if i['template']==78360)       # 18, not recovery
    from els_server.protocol.local_messages import wstring
    companion(path,1001,0x2e8,struct.pack('>Q',pet_item['uid'])+wstring('TestPet'),'TestPet')
    pet=next(p for p in __import__('els_server.storage.companion_state',fromlist=['snapshot']).snapshot(path,1001)['companions'])
    support(path,1001,0x219,use(expand['uid']),'expand')
    support(path,1001,0x219,use(upgrade['uid']),'upgrade')

    session=LocalSession(a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,
        gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
    session.role='game';session.phase='town_ready'

    def bind(hp,mp,sequence):
        return session.handle(Event(0x202,kind=0x8a1,payload=bindings(hp,mp)),sequence)[0]

    reply=bind(item_binding(79063),item_binding(79064),700)
    assert reply.kind==0x8a2 and result(reply)==0
    with closing(sqlite3.connect(path)) as db:
        state=automatic(db,1001)
    assert (state['hp_binding'],state['mp_binding'])==(item_binding(79063),item_binding(79064))

    reply=bind(item_binding(130165),item_binding(130165),701)
    assert result(reply)==0
    reply=bind(item_binding(79063),item_binding(78360),702)
    assert result(reply)==-1,'non-recovery orb must be refused'
    with closing(sqlite3.connect(path)) as db:
        state=automatic(db,1001)
    assert (state['hp_binding'],state['mp_binding'])==(item_binding(130165),item_binding(130165)),'rejection must keep the map'
    assert result(bind(item_binding(79063),item_binding(79064),703))==0

    companion(path,1001,0x2ec,struct.pack('>Q',pet['uid']),'summon')
    reply=session.handle(Event(0x202,kind=0x65e,payload=auto_use(0)),704)
    assert [e.kind for e in reply]==[0x65f,0x115]
    with closing(sqlite3.connect(path)) as db:
        assert next(i for i in load_items(db,1001) if i['uid']==bread['uid'])['count']==4
    session.phase='field_active'
    assert [e.kind for e in session.handle(Event(0x202,kind=0x65e,payload=auto_use(1)),705)]==[0x65f,0x115]
    with closing(sqlite3.connect(path)) as db:
        assert next(i for i in load_items(db,1001) if i['uid']==juice['uid'])['count']==4
    # A wait is not a rejection: success framing, real remaining seconds on the
    # native cooldown field, one chat line, and nothing consumed.
    blocked=session.handle(Event(0x202,kind=0x65e,payload=auto_use(0)),706)
    assert [e.kind for e in blocked]==[0x65f,0x87],'a wait must not become an empty error dialog'
    assert result(blocked[0])==0
    assert struct.unpack_from('>f',blocked[0].payload,len(blocked[0].payload)-6)[0]>0
    assert '冷却时间尚未结束' in blocked[1].payload.decode('utf-16-le',errors='ignore')
    with closing(sqlite3.connect(path)) as db:
        assert next(i for i in load_items(db,1001) if i['uid']==bread['uid'])['count']==4,'a wait consumes nothing'
        db.execute('CREATE TABLE IF NOT EXISTS pet_auto_cooldowns (owner INTEGER NOT NULL, '
                   'slot INTEGER NOT NULL, ready_at REAL NOT NULL, PRIMARY KEY(owner,slot))')
        db.execute('DELETE FROM consumable_cooldowns')
        db.execute('INSERT OR REPLACE INTO pet_auto_cooldowns VALUES (?,?,?)',(1001,0,time.time()+60))
        db.commit()
    interval=session.handle(Event(0x202,kind=0x65e,payload=auto_use(0)),707)
    assert [e.kind for e in interval]==[0x65f,0x87]
    assert result(interval[0])==0
    assert '宠物自动使用间隔尚未结束' in interval[1].payload.decode('utf-16-le',errors='ignore')
    # The same wait repeated inside the throttle window stays silent.
    quiet=session.handle(Event(0x202,kind=0x65e,payload=auto_use(0)),708)
    assert [e.kind for e in quiet]==[0x65f],'repeated waits must not flood chat'
    # A player-facing refusal is explained in chat instead of drawing an empty box.
    with closing(sqlite3.connect(path)) as db:
        db.execute('DELETE FROM pet_auto_cooldowns')
        db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(bread['uid'],1001))
        db.commit()
    refused=session.handle(Event(0x202,kind=0x65e,payload=auto_use(0)),709)
    assert [e.kind for e in refused]==[0x65f,0x87],'a refusal must not become an empty error dialog'
    assert result(refused[0])==0
    assert '背包中没有可自动使用的恢复道具' in refused[1].payload.decode('utf-16-le',errors='ignore')
print('PASS: automatic slots admit ordinary HP/MP recovery potions, explain waits and refusals in chat instead of -1, and consume one per 0x65E.')
