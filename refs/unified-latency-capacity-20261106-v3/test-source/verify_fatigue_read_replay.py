"""Original native gate, fresh SQL receipt, real writer contention and rollback."""
import runtime_fixture as h
import asyncio,contextlib,hashlib,json,sqlite3,struct,threading,time
from unittest.mock import patch
from profile_town import seed
from els_server.domain import normal_fatigue_flow as new
from els_server.storage.read_scope import committed_reads
from els_server.protocol.protocol_codec import Event
P=h.H/'experiments/fatigue-read-replay-v1'
old=h.load('owned_original_fatigue_flow_replay',P/'before-normal_fatigue_flow.py')
old.storage=h.load('owned_original_fatigue_storage_replay',P/'before-normal_fatigue.py')
probe=h.load('owned_fatigue_replay_gate',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
def contents(path):
    with contextlib.closing(sqlite3.connect(path))as db:return tuple(sorted(db.iterdump()))
async def main():
    c=h.f.FriendsTests();await c.asyncSetUp();checks=[]
    try:
        uid=seed(c,c.alice,'OwnReadGate');p=await c.peer(c.alice);await p.roster();await c.server.periodics.close()
        with patch.object(new.storage,'stage_replay',side_effect=AssertionError('B3 must retain its writer')):
            await probe.solo_load(p,uid)
        checks.append('Actual first B3 retained original durable writer')
        s=c.app.playing[c.alice['id']];await probe.clear_first(p,uid,s.dungeon_run)
        await p.send(0xb8,b'\1');await p.until(0xb9);await p.until(0xba)
        event=Event(0x202,kind=0xbb,payload=struct.pack('>b',s.dungeon_run.part),performers=(0,))
        before=contents(c.config.state_file)
        with committed_reads(connections=c.app.read_connections):expected=old.charge((s,),event)
        assert contents(c.config.state_file)==before
        with patch.object(new.storage,'_apply',side_effect=AssertionError('Known receipt opened writer')),committed_reads(connections=c.app.read_connections):actual=new.charge((s,),event)
        assert actual==expected and contents(c.config.state_file)==before
        checks.append('Fresh known receipt: original Events and complete SQL equal; _apply never called')
        entered=threading.Event();release=threading.Event();holder_errors=[]
        def hold_writer():
            try:
                with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
                    db.execute('BEGIN IMMEDIATE');entered.set();assert release.wait(5);db.rollback()
            except BaseException as error:holder_errors.append(repr(error));entered.set()
        holder=threading.Thread(target=hold_writer);holder.start();assert entered.wait(2)and not holder_errors
        try:
            began=time.perf_counter()
            with committed_reads(connections=c.app.read_connections):assert new.charge((s,),event)==expected
            held_ms=(time.perf_counter()-began)*1000
            assert not release.is_set()and holder.is_alive()
        finally:release.set();holder.join()
        assert not holder_errors and contents(c.config.state_file)==before
        checks.append(dict(case='Real other SQLite writer held throughout read replay',duration_ms=held_ms,no_writer_wait=True))
        def reject(*args,**kwargs):raise ValueError('Own replay encoding rejection')
        visible=(s._normal_fatigue_visible,s._normal_fatigue_last_check)
        with patch.object(new.storage,'encode_event',reject),committed_reads(connections=c.app.read_connections):
            try:new.charge((s,),event)
            except ValueError as error:assert str(error)=='Own replay encoding rejection'
            else:raise AssertionError('Encoding error hidden')
        assert contents(c.config.state_file)==before and visible==(s._normal_fatigue_visible,s._normal_fatigue_last_check)
        checks.append('Read replay encoding failure: no SQL or actor adoption')
        real=new.storage.stage_replay;entry=s.dungeon_run.parts[s.dungeon_run.next['part']]['npcs'][0];template=entry['template']
        def mutate(*args,**kwargs):
            result=real(*args,**kwargs);entry['template']=template+1;return result
        try:
            with patch.object(new.storage,'stage_replay',mutate),committed_reads(connections=c.app.read_connections):new.charge((s,),event)
        except ValueError as error:assert str(error)=='Ordinary fatigue native plan changed'
        else:raise AssertionError('Changed source accepted')
        finally:entry['template']=template
        assert contents(c.config.state_file)==before
        checks.append('Live target NPC change still refused by final complete source guard')
        with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
            db.execute('UPDATE character_owners SET account_id=? WHERE uid=?',(c.bob['id'],uid));db.commit()
        try:
            failures=[]
            for flow in(old,new):
                with committed_reads(connections=c.app.read_connections):
                    try:flow.charge((s,),event)
                    except ValueError as error:failures.append(str(error))
            assert len(failures)==2 and failures[0]==failures[1],failures
        finally:
            with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
                db.execute('UPDATE character_owners SET account_id=? WHERE uid=?',(c.alice['id'],uid));db.commit()
        checks.append('Other committed owner change refused exactly as original')
        operation,context,amount=new._debit(new._loading_plan(s,event)[0])
        with contextlib.closing(sqlite3.connect(c.config.state_file))as db:
            assert db.execute('DELETE FROM normal_fatigue_operations WHERE operation=?',(operation,)).rowcount==1;db.commit()
        missing=contents(c.config.state_file);apply=new.storage._apply
        def reject_after_write(*args,**kwargs):
            apply(*args,**kwargs);raise ValueError('Own original writer rollback')
        with patch.object(new.storage,'_apply',reject_after_write),committed_reads(connections=c.app.read_connections):
            try:new.charge((s,),event)
            except ValueError as error:assert str(error)=='Own original writer rollback'
            else:raise AssertionError('Writer error hidden')
        assert contents(c.config.state_file)==missing
        with patch.object(new.storage,'_apply',wraps=apply)as applied,committed_reads(connections=c.app.read_connections):new.charge((s,),event)
        assert applied.call_count==1
        committed=contents(c.config.state_file)
        with patch.object(new.storage,'_apply',side_effect=AssertionError('Repeat charged twice')),committed_reads(connections=c.app.read_connections):new.charge((s,),event)
        assert contents(c.config.state_file)==committed
        checks.append('Missing receipt retained original writer, rollback exact, next success once, repeat no extra debit')
        await p.send(0xbb,b'\1');assert(await p.until(0xbc)).payload==bytes(4);assert(await p.until(0xbd)).payload[:1]==b'\1'
        checks.append('Native BB/BC/BD completion succeeded')
    finally:await c.asyncTearDown()
    out=dict(passed=True,proposal_only=True,checks=checks,owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    (h.H/'fatigue-read-replay-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
