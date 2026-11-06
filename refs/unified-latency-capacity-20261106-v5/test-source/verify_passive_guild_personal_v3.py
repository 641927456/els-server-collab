"""Only the existing native contract scenario plus actual Agit visit and Town effects."""
from pathlib import Path
H=Path(__file__).resolve().parent
wrapper=(H/'verify_passive_guild_native_v2.py').read_text('utf8')
wrapper=wrapper[:wrapper.index("if case=='services':")]
anchor="            actor=app.playing[identities[0]['id']]"
addition='''            stage='active-personal-services-town-read'
            for index,p in ((0,master),(1,guest)):
                stage='personal-agit-enter-'+str(index)
                assert(await p.query(0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc)).payload[:4]==bytes(4)
                stage='personal-agit-map-'+str(index)
                assert(await p.query(0x225,struct.pack('>iB',25000,0),0x226)).payload[:4]==bytes(4)
                mark=len(p.received)
                stage='personal-agit-ready-'+str(index)
                assert(await p.query(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)).payload[:4]==bytes(4)
                await p.query(0x48d,b'',0x48f)
                snapshots=[e for e in p.received[mark:]if e.kind==0x3a3]
                stage='personal-agit-buffs-'+str(index)
                if not snapshots:snapshots=[await p.until(0x3a3)]
                assert all(struct.pack('>iIQ',buff,0,uids[index])in snapshots[-1].payload for buff in(1033,1034,1035))
                stage='personal-agit-exit-'+str(index)
                assert(await p.query(0x4fe,b'',0x4ff)).payload==bytes(4)
                assert(await p.query(0x225,struct.pack('>iB',20001,0),0x226)).payload[:4]==bytes(4)
                stage='personal-town-ready-'+str(index)
                assert(await p.query(0x227,struct.pack('>fffBH',1.,2.,3.,0,0),0x228)).payload[:4]==bytes(4)
                await p.query(0x48d,b'',0x48f)
                actor=app.playing[identities[index]['id']]
                assert actor.phase=='town_ready'
                with closing(sqlite3.connect(cfg.state_file))as db:
                    assert len(service.rows(db,uids[index],identities[index]['id'],int(time.time())))==3
                with closing(sqlite3.connect(cfg.state_file))as held:
                    held.execute('BEGIN IMMEDIATE')
                    events=await asyncio.wait_for(asyncio.to_thread(service.synchronize,actor),1.)
                    for event in events:encode_event(event)
                    held.rollback()
            report['steps'].append('Both actual native Agit visits emit original three personal buffs, actual Agit exit and Town admission preserve active effects, Town synchronize completes with a competing SQLite writer held')
'''
wrapper+="\nanchor="+repr(anchor)+"\naddition="+repr(addition)+"\nassert text.count(anchor)==1;text=text.replace(anchor,addition+anchor)\ntext=text.replace(\"'passive-guild-native-v2'/\",\"'passive-guild-personal-v3'/\")\nexec(compile(text,str(source),'exec'),globals())\n"
exec(compile(wrapper,str(H/'verify_passive_guild_native_v2.py'),'exec'),globals())
