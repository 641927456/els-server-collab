"""Original main/minor LuCiel box outputs and unchanged older box path."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
builder=W/'verify_quest_tls.py';tree=ast.parse(builder.read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
helpers=cases[:cases.index('            await accept(teacher,45002)')]
extra=r'''
            from els_server.domain.owned_reward_boxes import outputs_for,catalog as box_catalog
            from els_server.domain.ordinary_accessories import definitions as accessories
            from els_server.game_data import client_data
            for row in box_catalog()['boxes']:
                if row['template']==166572:continue
                assert row in json.loads((B/'els_server/data/owned_reward_boxes.json').read_bytes())['boxes']
            await accept(student,45040);await fixture('duel','owned-luciel-single-win',1);await claim(student,45040)
            box=read('SELECT uid FROM inventory_items WHERE owner=?AND template=166572',(uid[1],))[0][0]
            preview=await student.query(0x559,struct.pack('>iIBB',166572,0,0,0));assert preview.payload[:4]==bytes(4)
            assert struct.unpack_from('>I',preview.payload,17)[0]==8
            used=await student.query(0x196,struct.pack('>QBBBIi',box,0,0,0,0,0));assert used.payload[:4]==bytes(4)
            templates=set(range(188920,188928));data=client_data()
            rows=read('SELECT template,uid,slot FROM inventory_items WHERE owner=?AND template BETWEEN 188920 AND 188927',(uid[1],))
            assert {r[0]for r in rows}==templates
            slots=[]
            for template,item,slot in rows:
                spec=accessories()[template]
                target=spec['slots'][0]if spec['companion_only']else spec['main_slots'][0]
                ack=await student.query(0x104,struct.pack('>BiBiB',2,slot,9,target,0));assert ack.payload[-4:]==bytes(4),(template,sessions[1]._wear_rejection)
                slots.append(target)
            assert len(set(slots))==8
            report['checks'].append('Actual earned166572 LuCiel preview and use give both original four-piece sets; all8 equip in distinct main/minor native slots, without a choice or random pool')
            from els_server.storage.item_instances import next_uid,insert
            from els_server.storage.inventory_state import load_items
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE')
                occupied={i['slot']for i in load_items(db,uid[2])if i['group']==4};slot=next(n for n in range(30)if n not in occupied);old=next_uid(db)
                insert(db,uid[2],dict(uid=old,template=117542,metadata=2,group=4,slot=slot,count=1))
            before=read('SELECT COALESCE(SUM(count),0)FROM inventory_items WHERE owner=?AND template=78931',(uid[2],))[0][0]
            used=await outsider.query(0x196,struct.pack('>QBBBIi',old,0,0,0,0,0));assert used.payload[:4]==bytes(4)
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=78931',(uid[2],))==[(before+20,)]
            report['explicit_existing_owned117542_fixture']=True
            report['checks'].append('Every old fixed-box definition remains byte-equivalent; actual older117542 use still consumes one owned box and grants exactly20 existing78931 through its original source policy')
'''
foundation=W/'verify_relation_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main');source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
source=(source[:begin]+helpers+extra+source[end:]).replace("'relation-tls-'","'luciel-box-tls-'")
source=source.replace("index+1,'mentor-tls-'","(10 if index==1 else index+1),'mentor-tls-'")
source=source.replace("ServerConfig(mode='friends',host=","ServerConfig(mode='friends',normal_equipment_moves_enabled=True,host=")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);exec(compile(prefix,str(foundation),'exec'),globals())
generated=W/'generated-luciel-box-main.py';generated.write_text(source+'\n','utf8');exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
