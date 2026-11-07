"""Reuse approved native guild test inputs on the current isolated proposal."""
from pathlib import Path
import sys
H=Path(__file__).resolve().parent;case=sys.argv.pop(1)
assert case in('expedition','service_hud','services')
source=Path('G:/els/analysis/guild-full-system-20261105-v1')/('verify_'+case+'_tls.py')
text=source.read_text('utf8')
assert text.count('import overlay\n')==1;text=text.replace('import overlay\n','import bootstrap as overlay\n')
anchor="OUT = Path(__file__).resolve().parent"
assert text.count(anchor)==1;text=text.replace(anchor,"OUT = Path(__file__).resolve().parent/'passive-guild-native-v2'/"+repr(case)+"\nOUT.mkdir(parents=True,exist_ok=True)")
anchor="point = {'release':json.loads((OUT/'source.json').read_bytes())['release']+' + guild candidate'}"
assert text.count(anchor)==1;text=text.replace(anchor,"point = {'release':BASE.name+' + private passive-read proposal'}")
anchor="sys.path[:0] = [str(BASE), str(BASE/'vendor'), str(ROOT/'tools/pylibs'), str(ROOT)]"
assert text.count(anchor)==1;text=text.replace(anchor,'# The current bootstrap already pins the free-threaded dependencies and source.')
if case=='services':
    anchor="            report['ok']=True"
    addition='''            # Keep the original actual Agit visit, then exercise active personal buffs
            # through the ordinary Town read-only synchronization path as well.
            for index,p in ((0,master),(2,luciel)):
                assert(await p.query(0x4fe,b'',0x4ff)).payload==bytes(4)
                assert(await p.query(0x225,struct.pack('>iB',20001,0),0x226)).payload[:4]==bytes(4)
                assert(await p.query(0x227,struct.pack('>fffBH',1.,2.,3.,0,0),0x228)).payload[:4]==bytes(4)
                await p.query(0x48d,b'',0x48f)
                actor=app.playing[identities[index]['id']]
                assert actor.phase=='town_ready'
                with closing(sqlite3.connect(cfg.state_file))as db:
                    assert len(service.rows(db,uids[index],identities[index]['id'],int(__import__('time').time())))==3
                # An actual competing SQLite writer must not block this passive read.
                with closing(sqlite3.connect(cfg.state_file))as held:
                    held.execute('BEGIN IMMEDIATE')
                    events=await asyncio.wait_for(asyncio.to_thread(service.synchronize,actor),1.)
                    for event in events:encode_event(event)
                    held.rollback()
            report['steps'].append('Actual native Agit exit and Town admission retain three active personal guild effects; Town synchronize completes with a real competing SQLite writer held')
'''
    assert text.count(anchor)==1;text=text.replace(anchor,addition+anchor)
exec(compile(text,str(source),'exec'),globals())
