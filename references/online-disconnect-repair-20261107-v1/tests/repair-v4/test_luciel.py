"""Current FullUser capture contract through owned authentication/TLS and expiry."""
from pathlib import Path
import argparse,asyncio,hashlib,importlib.abc,importlib.util,json,sqlite3,struct,sys,time,traceback
from contextlib import closing
H=Path(__file__).resolve().parent;W=H.parent
parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path);parser.add_argument('--case',choices=['admission','expiry'],default='admission');args=parser.parse_args()
if args.candidate:
    class CandidateFinder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            source=args.candidate/Path(*fullname.split('.')).with_suffix('.py')
            if source.is_file():return importlib.util.spec_from_file_location(fullname,source)
    sys.meta_path.insert(0,CandidateFinder())
sys.argv=[sys.argv[0]]+(['--candidate',str(args.candidate)]if args.candidate else[])
spec=importlib.util.spec_from_file_location('current_owned_setup',W/'reproduce_tutorial_late_death.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
from els_server.protocol import dungeon_messages as dm
from els_server.storage.inventory_state import grant_items
from els_server.storage.item_expiration import assign
from els_server.game_data import client_data
from els_server.protocol.luciel_messages import preference

async def run():
    f=r.f.FriendsTests();await f.asyncSetUp()
    original_log=f.server.log
    def own_error_trace(event,**fields):
        original_log(event,**fields)
        if event in ('worker_error','notification_error','protocol_error'):
            (H/(args.case+'-owned-error-trace.txt')).write_text(traceback.format_exc(),'utf8')
    f.server.log=own_error_trace
    result=dict(ok=False,case=args.case,candidate=args.candidate is not None,actual_Application=True,actual_TLS=True,production_modified=False)
    try:
        uid=r.f.Characters(f.config.state_file,f.alice['id']).create('LuCielOwned',10,'owned-luciel-fix')['uid'];ring=None
        with closing(sqlite3.connect(f.config.state_file))as db,db:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
            if args.case=='expiry':
                ring=grant_items(db,[dict(template=92112,metadata=0,group=2,quantity=1)],uid)[0]
                db.execute('UPDATE inventory_items SET bag_group=9,slot=17 WHERE owner=? AND uid=?',(uid,ring['uid']))
                db.execute('BEGIN')if not db.in_transaction else None
                assign(db,uid,ring['uid'],int(time.time())+3600)
        peer=await f.peer(f.alice);await peer.roster()
        try:await r.admit(peer,uid,34060)
        except asyncio.IncompleteReadError:
            errors=[e.get('error')for e in f.events if e['event']in ('worker_error','notification_error')]
            (H/(args.case+'-observed-errors.json')).write_text(json.dumps(errors,indent=2)+'\n','utf8')
            result.update(reproduced=True,errors=errors)
            if args.candidate:raise
            assert "ValueError('LuCiel admitted member spans')"in errors or "ValueError('Missing authoritative LuCiel state')"in errors
            result['ok']=True;return result
        assert args.candidate,'Expected the current capture contract failure'
        s=f.app.playing[f.alice['id']];source=s.luciel_dungeon_hp_source
        assert source is not None and set(source[2])=={'0x198','0x1b4','0x1d1','0x5ec'}
        before=source[1];maximum=s.luciel_dungeon_hp_max
        message=dm.luciel_hp_notification(source,maximum/2,1)
        allowed=set()
        for key in ['0x198','0x1b4']:
            offset,size=source[2][key];assert size==28;allowed.update(range(offset,offset+4))
        allowed.add(source[2]['0x1d1'][0])
        assert len(before)==len(message.payload) and all(before[i]==message.payload[i]for i in range(len(before))if i not in allowed)
        offset,size=source[2]['0x5ec'];assert before[offset:offset+size]==message.payload[offset:offset+size]
        assert s.luciel_dungeon_hp_source is source
        if ring is not None:
            with closing(sqlite3.connect(f.config.state_file))as db,db:db.execute('UPDATE item_expiration SET expires_at=?WHERE item_uid=?',(int(time.time())-1,ring['uid']))
            s.expiration_checked=None
            notices=await f.app.call(s.expiration_notifications)
            assert any(e.kind==0x105 for e in notices) and any(e.kind==0x70d for e in notices),[e.kind for e in notices]
            assert s.luciel_dungeon_hp_max<maximum
            with closing(sqlite3.connect(f.config.state_file))as db:assert db.execute('SELECT 1 FROM inventory_items WHERE uid=?',(ring['uid'],)).fetchone()is None
            repeat=await f.app.call(s.expiration_notifications);assert not any(e.kind in (0x105,0x70d)for e in repeat)
            result.update(expired_worn_accessory_removed=True,HP_refresh_after_commit=True,repeat_no_duplicate_refresh=True)
        await peer.send(0x48d);await peer.until(0x48f)
        assert not any(e['event']in ('worker_error','notification_error','protocol_error')for e in f.events)
        result.update(ok=True,admitted=True,captured_fields=sorted(source[2]),unrelated_wire_bytes_preserved=True,opaque_5ec_preserved=True,connection_kept=True)
        return result
    finally:await f.asyncTearDown()

if __name__=='__main__':
    result={}
    try:result=asyncio.run(run())
    except BaseException:result=dict(ok=False,case=args.case,error=traceback.format_exc());raise
    finally:
        (H/(args.case+('-fixed'if args.candidate else'-baseline')+'.json')).write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
