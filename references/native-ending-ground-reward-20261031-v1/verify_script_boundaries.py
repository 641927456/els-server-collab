"""Relevant refusal/rollback/full-bag and actual shared source lifecycle."""
from verify_script_reward import *
from unittest.mock import patch

def saved(db):
    return [(name,db.execute('SELECT * FROM '+name).fetchall()) for(name,)in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

def boundary(s,path):
    run=s.dungeon_run;npc=rules._actor(run);event=death(npc,0);checks=[]
    with closing(sqlite3.connect(path))as db:before=saved(db)
    old=dict(run.defeated);world=dict(s.world_drops)
    def refused(name,fn):
        assert fn()==[],name;assert run.defeated==old and s.world_drops==world,name
        with closing(sqlite3.connect(path))as db:assert saved(db)==before,name
        checks.append(name)
    refused('foreign-killer',lambda:s.handle(death(npc,900000000)))
    with patch.object(s,'dungeon_failed',True):refused('failed-run',lambda:s.handle(event))
    with patch.object(s,'reward_run_id',str(uuid.uuid4())):refused('foreign-epoch',lambda:s.handle(event))
    with patch.object(s,'dungeon_substage_synced',False):refused('unloaded',lambda:s.handle(event))
    with patch.dict(npc,{'dynamic':True}):refused('dynamic-lookalike',lambda:s.handle(event))
    with patch.dict(npc,{'no_drop':True}):refused('no-drop-lookalike',lambda:s.handle(event))
    # The real encoder fails after a draw but before SQL commit/adoption.
    from els_server.protocol import protocol_codec
    with patch.object(protocol_codec,'encode_event',side_effect=ValueError('injected native encoder failure')):
        refused('encode-rollback',lambda:s.handle(event))
    from els_server.storage.inventory_state import validate_plan
    from els_server.domain.reward_rules import item_plan
    try:validate_plan([item_plan(30572,1)])
    except ValueError:checks.append('generic-acquisition-stays-closed')
    else:raise AssertionError('generic30572 opened')
    assert [e.kind for e in s.handle(event)]==[0xae,0xaf,0xcf]
    # Own isolated inventory fixture: fill the native accessory tab, preserving
    # all existing instances; the ground issue must survive a capacity refusal.
    from els_server.storage.bag_capacity import allowances
    with closing(sqlite3.connect(path))as db,db:
        capacity=allowances(db,s.account.uid)[2];occupied={r[0]for r in db.execute('SELECT slot FROM inventory_items WHERE owner=? AND bag_group=2',(s.account.uid,))}
        ids=[]
        for slot in range(capacity):
            if slot not in occupied:
                uid=900000000+s.account.uid*1000+slot;ids.append(uid)
                db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(uid,s.account.uid,30572,0,1,2,slot))
    drop=next(d for d in s.world_drops.values()if d.get('source')==rules.POLICY)
    with closing(sqlite3.connect(path))as db:full=saved(db)
    reply=s.handle(pickup(drop));assert len(reply)==1 and reply[0].kind==0xd1 and reply[0].payload==struct.pack('>i',-1)
    with closing(sqlite3.connect(path))as db:assert saved(db)==full
    assert not drop['pickup_committed'];checks.append('full-bag-no-commit')
    with closing(sqlite3.connect(path))as db,db:db.executemany('DELETE FROM inventory_items WHERE uid=?',[(i,)for i in ids])
    checks.append('space-freed-retry');result=check_claim(s,path)
    return dict(checks=checks,claim=result)

def shared_advance(c,members,clock,stop_boss=False):
    leader=members[0];room=c.app.world.dungeons.room(leader)
    for _ in range(100):
        run=leader.dungeon_run
        if stop_boss and (run.stage,run.part)==(4,0):
            for m in members:m.mailbox.drain()
            return
        for npc in list(run.current['npcs']):
            if room.phase!='active':break
            if npc.get('team',1)==0 or npc['template']==2368:continue
            if npc['key']in run.defeated:continue
            reply=leader.handle(death(npc,leader.account.uid))
            if npc['active']:assert reply and reply[0].kind==0xae,(run.stage,run.part,npc['template'],reply)
        clock[0]+=max([x['seconds']+x['delay']for x in run.current['conditions']]+[0])+1
        for m in members:m.next_periodic=0;m.periodic_notifications()
        clock[0]=max([clock[0],*[m.dungeon_run.ready_at or 0 for m in members]])+1
        for m in members:m.next_periodic=0;m.periodic_notifications()
        c.app.world.dungeons.part_wait(room)
        assert room.phase=='part_end',(run.stage,run.part,room.phase,run.current['conditions'],[(n['key'],n['template'],n['active'],n['no_drop'])for n in run.current['npcs']if n['key']not in run.defeated])
        for m in members:m.handle(Event(0x202,kind=0xbb,payload=struct.pack('>b',run.part)))
        if all(m.clear_notified for m in members):return
        for m in members:m.handle(Event(0x202,performers=(0,),kind=0xb3,payload=bytes(9)))
    raise AssertionError('Shared traversal bound')

async def main():
    out=dict(ok=False,actual_App=True,TLS_admission=True,synthetic_deaths=True,natural_multiplayer=False,rows=[])
    if '--group-only' not in sys.argv:
        c=t.FriendsTests();await c.asyncSetUp()
        try:
            row=dict(kind='solo-boundaries',ok=False);out['rows'].append(row)
            try:
                s,clock=await admit(c,10)
                def exercise():advance(s,clock,stop_boss=True);return boundary(s,c.config.state_file)
                row.update(await c.app.call(exercise));row['ok']=True
            except Exception as e:row.update(error=repr(e),traceback=traceback.format_exc(limit=12))
        finally:await c.asyncTearDown()
    # Independent owned room; no previous client or saved account reused.
    if '--solo-only' not in sys.argv:
        c=t.FriendsTests();await c.asyncSetUp()
        try:
            row=dict(kind='two-member-room',ok=False);out['rows'].append(row)
            try:
                # Seed actual owned prerequisites before the first roster/town load,
                # so native admission sees the same saved and loaded character.
                regions=region_catalog().data['dungeons']['33891'];reqs={region_catalog().data['regions'][str(x)]['requirement'].get('RequireQuestID')for x in regions}-{0,None}
                for account in(c.alice,c.bob):
                    uid=Characters(c.config.state_file,account['id']).create('Player'+str(account['id']),1,'trueend-shared:'+str(account['id']))['uid']
                    QuestState(c.config.state_file,uid,account_id=account['id']).snapshot()
                    with closing(sqlite3.connect(c.config.state_file))as db,db:
                        db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.executemany('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',[(uid,q,1,'{}')for q in reqs])
                alice,bob,a,b=await c.coop_pair()
                await alice.send(0x145,struct.pack('>ibb',33891,0,0));assert (await alice.until(0x146)).payload==bytes(4)
                await c.coop_start(alice,bob,33891);await c.coop_load(alice,bob)
                members=(c.app.playing[c.alice['id']],c.app.playing[c.bob['id']]);clock=[0.]
                for m in members:m.dungeon_run.clock=lambda:clock[0]
                def exercise_shared():
                    shared_advance(c,members,clock,True);leader,guest=members;dummy=rules._actor(leader.dungeon_run);event=death(dummy,0)
                    assert guest.handle(event)==[]
                    before=[dict(m.dungeon_run.defeated)for m in members]
                    from els_server.domain import party_commands
                    with patch.object(party_commands,'encode_event',side_effect=ValueError('second member precommit encoding')):
                        reply=leader.handle(event);assert reply==[],('injected-encode',[(e.kind,e.payload.hex()[:20])for e in reply],rules.__file__,[m.dungeon_run.defeated.get(dummy['key'])==event.payload for m in members])
                    assert [m.dungeon_run.defeated for m in members]==before
                    with closing(sqlite3.connect(c.config.state_file))as db:assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='dungeon_equipment_loot_issues'").fetchone()==(0,)
                    # Deliberately delay the true-ending witness until both members
                    # have committed the existing original C1 clear transaction.
                    shared_advance(c,members,clock);assert all(m.clear_notified for m in members)
                    for m in members:m.mailbox.drain()
                    reply=leader.handle(event);row['leader_delivery']=[e.kind for e in reply];assert row['leader_delivery'][:3]==[0xae,0xaf,0xcf] and all(e==0xf3 for e in row['leader_delivery'][3:]),row['leader_delivery']
                    assert [e.kind for e in leader.handle(event)]==[0xae]
                    row['guest_delivery']=[e.kind for e in guest.mailbox.drain()];assert row['guest_delivery']==[0xaf,0xcf]
                    row['claims']=[check_claim(m,c.config.state_file)for m in members]
                    row['member_count']=2;row['shared_atomic_rollback']=True;row['guest_death_refused']=True;row['after_C1']=True
                await c.app.call(exercise_shared);row['ok']=True
            except Exception as e:row.update(error=repr(e),traceback=traceback.format_exc(limit=12))
        finally:await c.asyncTearDown()
    out['ok']=all(row['ok']for row in out['rows']);out['private_environment_closed']=True
    (O/('script-reward-solo-boundaries.json' if '--solo-only' in sys.argv else 'script-reward-boundaries.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
