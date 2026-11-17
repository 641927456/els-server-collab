"""Reuse the passed isolated App/TLS foundation for distinct summon paths."""
from pathlib import Path
import ast,hashlib
foundation=Path(__file__).with_name('verify_relation_tls.py')
original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
assert source.count(anchor)==1
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
cases=r'''
            await invite();accepted,starts=await answer();assert accepted.payload[-5]==1
            await after(teacher,0x1eb,starts[0]);before_relations=mentors()
            xyz=catalog()['towns']['20000']['xyz']
            assert (await student.query(0x225,struct.pack('>iB',20000,0))).payload[:4]==bytes(4)
            assert (await student.query(0x227,struct.pack('>fffBH',*xyz,0,0))).payload[:4]==bytes(4)
            assert sessions[1].active_map==20000
            before=read('SELECT *FROM location ORDER BY uid');economy=read('SELECT *FROM reward_balances ORDER BY uid')
            current=sessions[0].account.get_location()
            location=dict(map=current['map'],xyz=(current['xyz'][0]+12.25,*current['xyz'][1:]),board=current['board'])
            body=struct.pack('>ifffB',location['map'],*location['xyz'],location['board'])
            denied=await outsider.query(0x71b,body)
            assert struct.unpack('>i',denied.payload)[0]==1981
            denied=await teacher.query(0x71b,struct.pack('>i',20002)+body[4:])
            assert denied.payload!=bytes(4) and not app.world.mentors.summons.pending
            denied=await teacher.query(0x71b,body)
            assert denied.payload!=bytes(4) and not app.world.mentors.summons.pending
            # Explicit eligibility fixture, not a manufactured dungeon clear.
            # Initial foundation intentionally cold-restores level1 at20001;
            # a new cross-town summon still requires level6 and clear30092.
            from els_server.domain.dungeon_routes import route_catalog
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=10,revision=revision+1 WHERE uid=?',(uid[1],))
                db.execute('INSERT INTO dungeon_records VALUES(?,?,?)',(uid[1],route_catalog().entry_identity(30090),30))
            report['explicit_destination_level_and_clear_fixture']=True
            async def summon():
                start=len(student.received)
                ack=await teacher.query(0x71b,body);assert ack.payload==bytes(4),ack.payload.hex()
                notice=await after(student,0x71d,start)
                assert notice.payload[:17]==body and len(notice.payload)==34
                return notice.payload
            echo=await summon();start=len(teacher.received)
            await student.send(0x71f,b'\0'+echo);await barrier(student)
            assert (await after(teacher,0x723,start)).payload==b'\0'
            assert not app.world.mentors.summons.pending and read('SELECT *FROM location ORDER BY uid')==before
            report['checks'].append('Cross-town setup via actual225/227; outsider and forged destination denied; native71D consent refusal leaves both saved positions unchanged')
            echo=await summon()
            altered=echo[:-2]+bytes((echo[-2]^1,))+echo[-1:]
            failed=await student.query(0x71f,b'\1'+altered,reply=0x724)
            assert failed.payload!=bytes(4) and sessions[1]in app.world.mentors.summons.pending
            with patch.object(wire,'summoned',side_effect=ValueError('Owned late native720 encoder failure')):
                failed=await student.query(0x71f,b'\1'+echo,reply=0x724)
                assert failed.payload!=bytes(4)
            assert sessions[1].phase=='town_ready' and read('SELECT *FROM location ORDER BY uid')==before
            report['checks'].append('Frozen consent echo mismatch and late720 encoding failure preserve the original pending consent, phase and saved positions')
            start=len(teacher.received)
            arrived=await student.query(0x71f,b'\1'+echo,reply=0x720)
            assert arrived.payload==wire.summoned(location).payload
            assert (await after(teacher,0x723,start)).payload==b'\1'
            assert sessions[1].phase=='map_loading' and read('SELECT *FROM location ORDER BY uid')==before
            denied=await student.query(0x225,struct.pack('>iB',20002,0))
            assert denied.payload[:4]!=bytes(4) and sessions[1].phase=='map_loading'
            assert (await student.query(0x225,struct.pack('>iB',location['map'],0))).payload[:4]==bytes(4)
            assert (await student.query(0x227,struct.pack('>fffBH',*location['xyz'],location['board'],0))).payload[:4]==bytes(4)
            assert sessions[1].active_map==location['map'] and sessions[1].mentor_summon_transition is None
            saved=read('SELECT town,board,x,y,z FROM location WHERE uid=?',(uid[1],))
            assert saved==[(location['map'],location['board'],*location['xyz'])]
            assert app.world.members[sessions[1]]==(1,location['map'])
            assert mentors()==before_relations and read('SELECT *FROM reward_balances ORDER BY uid')==economy
            duplicate=await student.query(0x71f,b'\1'+echo,reply=0x724)
            assert duplicate.payload!=bytes(4) and sessions[1].phase=='town_ready'
            report['checks'].append('Original720 and723 success; wrong next225 denied; exact225/227 saves arrival and publishes membership; late consent cannot teleport again; no ED/XP/relation mutation')
            echo=await summon();start=len(teacher.received)
            def expired():
                app.world.mentors.summons.pending[sessions[1]].expires=time.monotonic()-1
                app.world.mentors.expire()
            await app.call(expired)
            assert (await after(teacher,0x723,start)).payload==b'\0' and not app.world.mentors.summons.pending
            echo=await summon();start=len(teacher.received)
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            await barrier(teacher)
            assert (await after(teacher,0x723,start)).payload==b'\0' and not app.world.mentors.summons.pending
            report['checks'].append('Explicit expired server consent lease and real recipient disconnect free both pending participants and report native723 refusal')
'''
source=source[:begin]+cases+source[end:]
source=source.replace("'relation-tls-'","'summon-tls-'")
source=source.replace('    app=server=None;peers=[];events=[]',
    '    report["foundation_sha256"]=FOUNDATION_SHA\n    app=server=None;peers=[];events=[]')
prefix='\n'.join(original.splitlines()[:node.lineno-1]);FOUNDATION_SHA=hashlib.sha256(foundation.read_bytes()).hexdigest()
exec(compile(prefix,str(foundation),'exec'),globals())
generated=Path(__file__).with_name('generated-summon-main.py');generated.write_text(source+'\n','utf8')
exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
