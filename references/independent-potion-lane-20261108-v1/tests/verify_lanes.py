"""Prove real TLS medicine progresses while the death worker is held."""
import asyncio,contextlib,json,struct,threading,time
from unittest.mock import patch
import runtime_fixture as h
import sqlite3
from profile_death import seed,death
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.quick_slots import save_request,empty
from els_server.domain.quick_bindings import item_binding

async def setup(*,low_level=False):
    c=h.f.FriendsTests();await c.asyncSetUp()
    uid=seed(c)
    if low_level:
        from els_server.storage.characters import Characters
        from els_server.game_data import client_data
        uid=Characters(c.config.state_file,c.alice['id']).create('OwnLowLane',5,'owned-low-lane')['uid']
        with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
            db.execute('UPDATE characters SET level=98,revision=revision+1 WHERE uid=?',(uid,))
            db.execute('UPDATE reward_balances SET experience=? WHERE uid=?',(client_data().thresholds[-1]-1,uid))
    with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
        grant_items(db,[dict(template=130165,metadata=2,group=6,quantity=10)],uid)
    slots=empty();slots[0]=item_binding(130165)
    save_request(c.config.state_file,struct.pack('>iI',1,len(slots))+b''.join(struct.pack('>ii',k,v)for k,v in slots.items()),uid)
    peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid)
    await wait(lambda:any(e.get('event')=='request_timing'and e.get('kind')==0x227 for e in c.events))
    s=c.app.playing[c.alice['id']];run=h.room(s)
    return c,peer,s,run,uid

def count(c,uid):
    with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
        return sum(i['count']for i in load_items(db,uid)if i['template']==130165)

async def wait(predicate):
    async with asyncio.timeout(8):
        while not predicate():await asyncio.sleep(.002)

async def blocked_death():
    c,peer,s,run,uid=await setup();entered=threading.Event();release=threading.Event()
    try:
        from els_server.domain import legacy_pve_exp
        original=legacy_pve_exp.accepted_death
        def held(*args,**kwargs):
            entered.set()
            if not release.wait(8):raise TimeoutError('Owned death gate was not released')
            return original(*args,**kwargs)
        npc=next(n for n in run.current['npcs']if n['active']and not n['no_drop']and not n.get('ally'))
        request=death(npc,uid)
        with patch.object(legacy_pve_exp,'accepted_death',held):
            await peer.send(request.kind,request.payload);await wait(entered.is_set)
            # More than the old sixteen-packet window. Authenticated repeated
            # deaths stay ordered and retain their original idempotent receipts.
            for _ in range(24):await peer.send(request.kind,request.payload)
            started=time.perf_counter();await peer.send(0x113,bytes(5))
            reply=await peer.until(0x114);await peer.until(0x115)
            latency=(time.perf_counter()-started)*1000
            assert struct.unpack_from('>i',reply.payload)[0]==0
            assert not release.is_set()and not run.defeated
            assert count(c,uid)==9
            assert any(r['event']=='request_timing'and r.get('kind')==0x113 and r.get('calls')==[{'lane':'consumable'}]for r in c.events)
            release.set();await peer.until(0xae)
            await wait(lambda:any(r.get('sequence')==38 and r.get('event')=='request_timing'for r in c.events))
        assert len(run.defeated)==1 and count(c,uid)==9
        return dict(case='medicine-overtakes-24-queued-deaths',ok=True,potion_ms=latency,
            death_worker_still_blocked_at_success=True,original_native_sequence_valid=True)
    finally:
        release.set();await c.asyncTearDown()

async def writer_guard():
    c,peer,s,run,uid=await setup();db=sqlite3.connect(c.config.state_file)
    try:
        db.execute('BEGIN IMMEDIATE')
        await peer.send(0x113,bytes(5))
        await wait(lambda:c.app.consumables.queue.inflight>0)
        assert count(c,uid)==10
        s.dungeon_substage_synced=False
        db.rollback()
        reply=await peer.until(0x114)
        assert struct.unpack_from('>i',reply.payload)[0]!=0
        assert count(c,uid)==10
        assert not any(e['received']==0x115 for e in peer.observed)
        with contextlib.closing(sqlite3.connect(c.config.state_file))as cold:
            present=cold.execute("SELECT 1 FROM sqlite_master WHERE name='consumable_uses'").fetchone()
            assert not present or cold.execute('SELECT COUNT(*) FROM consumable_uses WHERE owner=?',(uid,)).fetchone()[0]==0
        return dict(case='writer-wait-rechecks-scene-before-debit',ok=True)
    finally:
        db.close();await c.asyncTearDown()

async def barrier():
    c,peer,s,run,uid=await setup();entered=threading.Event();release=threading.Event()
    try:
        from els_server.storage import consumables
        original=consumables.use
        def held(*args,**kwargs):
            entered.set()
            if not release.wait(8):raise TimeoutError('Owned potion gate was not released')
            return original(*args,**kwargs)
        peer.observed.clear()
        with patch.object(consumables,'use',held):
            await peer.send(0x113,bytes(5));await wait(entered.is_set)
            await peer.send(0x67,struct.pack('>i',0x72)+bytes(96))
            await asyncio.sleep(.05)
            assert s.phase=='dungeon_active'and count(c,uid)==10
            assert not any(e['received']==0x68 for e in peer.observed)
            release.set();reply=await peer.until(0x114);await peer.until(0x115)
            assert struct.unpack_from('>i',reply.payload)[0]==0
            await peer.until(0x68)
        kinds=[e['received']for e in peer.observed]
        assert kinds.index(0x114)<kinds.index(0x115)<kinds.index(0x68)
        assert count(c,uid)==9
        return dict(case='native-exit-drains-potion-and-effect-first',ok=True)
    finally:
        release.set();await c.asyncTearDown()

async def automatic():
    c,peer,s,run,uid=await setup()
    try:
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        from els_server.storage.companion_state import handle as companion,snapshot
        from els_server.storage.pet_support import handle as pet
        from els_server.protocol.local_messages import wstring
        with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
            items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)
                for t,n in((550427,1),(164566,1),(330562,1),(77000,8))],uid)
        got={i['template']:i for i in items}
        companion(c.config.state_file,uid,0x2e8,struct.pack('>Q',got[550427]['uid'])+wstring('OwnLanePet'),'owned-pet-activate')
        active=snapshot(c.config.state_file,uid)['companions'][0]['uid']
        for template in(164566,330562):
            pet(c.config.state_file,uid,0x219,struct.pack('>QQiiIB',got[template]['uid'],0,0,0,0,0),'owned-pet-'+str(template))
        pet(c.config.state_file,uid,0x661,struct.pack('>QBBbiiBBB',0,100,100,1,0,0,40,0,0),'owned-pet-settings')
        pet(c.config.state_file,uid,0x8a1,struct.pack('>iIiiii',2,2,0,item_binding(77000),1,0),'owned-pet-bind')
        companion(c.config.state_file,uid,0x2ec,struct.pack('>Q',active),'owned-pet-summon')
        await peer.send(0x65e,bytes(5));reply=await peer.until(0x65f)
        assert struct.unpack_from('>i',reply.payload)[0]==0
        effect=await peer.until(0x115);assert struct.unpack_from('>Qi',effect.payload)==(uid,77000)
        with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
            assert sum(i['count']for i in load_items(db,uid)if i['template']==77000)==7
        await peer.send(0x65e,bytes(5));reply=await peer.until(0x65f)
        assert struct.unpack_from('>i',reply.payload)[0]==1369
        assert any(r.get('kind')==0x65e and r.get('calls')==[{'lane':'consumable'}]for r in c.events)
        return dict(case='entitled-pet-native-65E-65F-and-cooldown',ok=True)
    finally:await c.asyncTearDown()

async def disconnect():
    c,peer,s,run,uid=await setup();entered=threading.Event();release=threading.Event()
    try:
        from els_server.storage import consumables
        original=consumables.use
        def held(*args,**kwargs):
            entered.set()
            if not release.wait(8):raise TimeoutError('Owned disconnect gate was not released')
            return original(*args,**kwargs)
        with patch.object(consumables,'use',held):
            await peer.send(0x113,bytes(5));await wait(entered.is_set)
            await peer.close();await asyncio.sleep(.04)
            assert c.app.playing.get(c.alice['id'])is s
            assert c.app.consumables.queue.inflight==1
            release.set();await wait(lambda:c.alice['id']not in c.app.playing)
        assert c.app.consumables.queue.inflight==0 and count(c,uid)==9
        return dict(case='disconnect-retires-real-potion-worker-before-lease-release',ok=True)
    finally:
        release.set();await c.asyncTearDown()

async def rollback():
    c,peer,s,run,uid=await setup()
    try:
        from els_server.storage.consumables import use
        checked=[]
        def authorize(db):
            checked.append(db.in_transaction)
            if len(checked)==2:raise ValueError('Owned authority invalidated before commit')
        try:
            use(c.config.state_file,uid,bytes(5),'owned-late-guard',allow_apples=True,
                account_id=c.alice['id'],authorize=authorize)
        except ValueError as error:assert str(error)=='Owned authority invalidated before commit'
        else:raise AssertionError('Final authority failure was not returned')
        assert checked==[True,True]and count(c,uid)==10
        with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
            for table in('consumable_uses','consumable_cooldowns'):
                exists=db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone()
                assert not exists or db.execute('SELECT COUNT(*) FROM '+table+' WHERE owner=?',(uid,)).fetchone()[0]==0
        return dict(case='final-authority-failure-rolls-back-count-cooldown-and-receipt',ok=True)
    finally:await c.asyncTearDown()

async def level_up():
    c,peer,s,run,uid=await setup(low_level=True);entered=threading.Event();release=threading.Event()
    try:
        from els_server.domain import legacy_pve_exp
        original=legacy_pve_exp.accepted_death
        def held(*args,**kwargs):
            entered.set()
            if not release.wait(8):raise TimeoutError('Owned level-up gate was not released')
            return original(*args,**kwargs)
        npcs=[n for n in run.current['npcs']if n['active']and not n['no_drop']and not n.get('ally')]
        peer.observed.clear()
        with patch.object(legacy_pve_exp,'accepted_death',held):
            first=death(npcs[0],uid);second=death(npcs[1],uid)
            await peer.send(first.kind,first.payload);await wait(entered.is_set)
            await peer.send(second.kind,second.payload);await peer.send(0x113,bytes(5))
            await wait(lambda:getattr(s,'_consumable_pending',0)>0)
            await asyncio.sleep(.03)
            assert count(c,uid)==10 and not any(e['received']==0x114 for e in peer.observed)
            release.set();af=await peer.until(0xaf)
            assert struct.unpack_from('>I',af.payload,17)[0]==1
            assert struct.unpack_from('>Qi',af.payload,21)==(uid,1)
            reply=await peer.until(0x114);await peer.until(0x115)
            assert struct.unpack_from('>i',reply.payload)[0]==0
            assert npcs[0]['key']in run.defeated and npcs[1]['key']not in run.defeated
            with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
                assert db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()==(99,)
            kinds=[e['received']for e in peer.observed]
            assert kinds.index(0xaf)<kinds.index(0x114)
            await wait(lambda:len(run.defeated)==2)
        assert count(c,uid)==9
        return dict(case='below-cap-level-up-reply-before-potion-before-next-death',ok=True)
    finally:
        release.set();await c.asyncTearDown()

async def main():
    rows=[]
    selected=[arg.split('=',1)[1]for arg in h.sys.argv if arg.startswith('--case=')]
    for case in(blocked_death,writer_guard,barrier,automatic,disconnect,rollback,level_up):
        if selected and case.__name__ not in selected:continue
        rows.append(await case());print(json.dumps(rows[-1]),flush=True)
    result=dict(ok=True,cases=rows,all_owned_runtime_removed=True)
    suffix='-'+','.join(selected)if selected else''
    (h.H/('lane-verification'+suffix+'.json')).write_text(json.dumps(result,indent=2)+'\n','utf8')

if __name__=='__main__':asyncio.run(main())
