"""Earned189800 original718/719/71A use, extension and current native slot."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
builder=W/'verify_quest_tls.py';tree=ast.parse(builder.read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
helpers=cases[:cases.index('            await accept(teacher,45002)')]
extra=r'''
            from els_server.storage import resonance_period as period,resonance_state as resonance
            from els_server.domain.resonance_allocation_flow import profiles
            from els_server.domain.housing_access_flow import capture
            for cycle in range(6):
                await accept(teacher,45002);await fixture('duel','owned-blessing-earned:'+str(cycle),3);await claim(teacher,45002)
            items=read('SELECT uid FROM inventory_items WHERE owner=?AND template=189800 ORDER BY uid',(uid[0],))
            assert len(items)==6
            body=lambda item,stat=1:struct.pack('>QiB',item,stat,1)
            failed=await teacher.query(0x718,body(items[0][0]));assert failed.payload[:4]!=bytes(4)
            assert len(read('SELECT uid FROM inventory_items WHERE owner=?AND template=189800',(uid[0],)))==6
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE')
                resonance.ensure(db)
                db.execute('INSERT INTO account_resonance VALUES(?,1,0,1)ON CONFLICT(account_id)DO UPDATE SET enabled=1,revision=revision+1',(values[0]['account_id'],))
            await teacher.query(0x213,struct.pack('>i',0));await barrier(teacher)
            def saved():
                with closing(sqlite3.connect(cfg.state_file))as db:return period.snapshot(db,values[0]['account_id'],uid[0],mentor=True)
            def dump():
                # The ordinary online-time observer may advance independently
                # after a refused request. Compare all remaining SQL state.
                with closing(sqlite3.connect(cfg.state_file))as db:return [row for row in db.iterdump()if '"activity518_'not in row]
            stamp=int(time.time());before=dump()
            with patch.object(period,'notice',side_effect=ValueError('Owned late blessing71A encoding failure')):
                failed=await teacher.query(0x718,body(items[0][0]));assert failed.payload[:4]!=bytes(4)
            assert dump()==before
            starts=len(teacher.received)
            with patch.object(period.time,'time',return_value=stamp):
                used=await teacher.query(0x718,body(items[0][0]));assert used.payload[:4]==bytes(4)
                notice=await after(teacher,0x71a,starts)
                assert struct.unpack('>iiQB',notice.payload)==(1,5,stamp+7*86400,1)
                first=saved();assert first[:3]==(1,5,stamp+7*86400)
                operation=read('SELECT operation_id FROM inventory_action_receipts WHERE owner=?AND kind=1816 ORDER BY rowid DESC LIMIT 1',(uid[0],))[0][0]
                def replay():
                    same,guard=capture(sessions[0])
                    return period.use(cfg.state_file,uid[0],values[0]['account_id'],body(items[0][0]),operation,guard)
                await app.call(replay);assert saved()==first
                failed=await teacher.query(0x718,body(items[1][0],2));assert failed.payload[:4]!=bytes(4)
                assert saved()==first
                for index,days in enumerate((14,21,28,30),1):
                    answer=await teacher.query(0x718,body(items[index][0]));assert answer.payload[:4]==bytes(4)
                    assert saved()[:3]==(1,5,stamp+days*86400)
                before=dump()
                failed=await teacher.query(0x718,body(items[5][0]));assert failed.payload[:4]!=bytes(4)
                current=dump()
                assert current==before,{'removed':[line[:180]for line in before if line not in current][:6],
                    'added':[line[:180]for line in current if line not in before][:6]}
            assert len(read('SELECT uid FROM inventory_items WHERE owner=?AND template=189800',(uid[0],)))==1
            report['checks'].append('Earned189800 refuses unopened ERP; late71A failure rolls back all; original718/719/71A adds exactly5 temporary points for7days; exact replay adds nothing; same native stat extends14/21/28/30days, different active stat and30day cap never consume')
            with closing(sqlite3.connect(cfg.state_file))as db:
                db.execute('BEGIN IMMEDIATE')
                p=profiles(db);state=p.synchronize(account=values[0]['account_id'],character=uid[0])
                assert(state.field21,state.field25,state.field29)==(1,5,stamp+30*86400)
                assert period.bonus(state)==((1,5),)
                assert all(value==0 for stat,value in p.pages.read(values[0]['account_id'],uid[0]).selected().points)
                assert period.active(db,values[0]['account_id'],uid[0],now=stamp+30*86400-1)is not None
                assert period.active(db,values[0]['account_id'],uid[0],now=stamp+30*86400)is None
            await teacher.close();peers.remove(teacher)
            deadline=time.monotonic()+5
            while app.playing.get(values[0]['account_id'])is sessions[0]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            teacher=await connect(values[0],peers);sessions[0]=app.playing[values[0]['account_id']]
            assert saved()[:3]==(1,5,stamp+30*86400)
            report['checks'].append('Existing610 projection and allocation bonus use the temporary slot without permanent investment; authenticated cold restore retains expiry; explicit30day clock has exact active/expired boundary')
            from els_server.storage.item_instances import next_uid,insert
            from els_server.storage.inventory_state import load_items
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');resonance.ensure(db)
                db.execute('INSERT INTO account_resonance VALUES(?,1,0,1)ON CONFLICT(account_id)DO UPDATE SET enabled=1,revision=revision+1',(values[2]['account_id'],))
                used={i['slot']for i in load_items(db,uid[2])if i['group']==4};legacy=[]
                for index in range(2):
                    slot=next(n for n in range(30)if n not in used);used.add(slot);item=next_uid(db)
                    insert(db,uid[2],dict(uid=item,template=712417,metadata=0,group=4,slot=slot,count=1));legacy.append(item)
            report['explicit_existing_owned712417_fixture']=True
            answer=await outsider.query(0x718,body(legacy[0]));assert answer.payload[:4]==bytes(4)
            with closing(sqlite3.connect(cfg.state_file))as db:
                original=period.snapshot(db,values[2]['account_id'],uid[2]);assert original[2]-original[3]==30*86400
                assert period.snapshot(db,values[2]['account_id'],uid[2],mentor=True)is None
            failed=await outsider.query(0x718,body(legacy[1]));assert failed.payload[:4]!=bytes(4)
            assert read('SELECT uid FROM inventory_items WHERE uid=?',(legacy[1],))==[(legacy[1],)]
            report['checks'].append('Existing owned712417 regression: its original30day row/schema stays separate, first use succeeds, a second active use never debits; new7day source does not change the approved old policy')
'''
foundation=W/'verify_relation_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main');source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
source=(source[:begin]+helpers+extra+source[end:]).replace("'relation-tls-'","'blessing-tls-'")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);exec(compile(prefix,str(foundation),'exec'),globals())
generated=W/'generated-blessing-main.py';generated.write_text(source+'\n','utf8');exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
