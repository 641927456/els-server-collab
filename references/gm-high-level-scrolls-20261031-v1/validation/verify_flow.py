from pathlib import Path
from contextlib import closing
import asyncio,hashlib,importlib.util,json,sqlite3,struct,sys,tempfile

ROOT=Path('G:/els');WORK=Path(__file__).resolve().parent
binding=json.loads((WORK/'binding.json').read_bytes());BASE=Path(binding['parent_root']);SOURCE=WORK/'source'
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
import els_server,els_server.domain,els_server.storage
for package,relative in ((els_server,'els_server'),(els_server.domain,'els_server/domain'),(els_server.storage,'els_server/storage')):
    package.__path__.insert(0,str(SOURCE/relative))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.protocol.protocol_codec import Event
from els_server.domain.session_dispatch import priority_handlers
from els_server.game_data import client_data

# This exact catalog implementation was read back from the running online GM.
catalog_file=ROOT/'analysis/gm-console-01a14617/candidate-v2/gm_console/catalog.py'
assert hashlib.sha256(catalog_file.read_bytes()).hexdigest()=='f53c17a875101f357f3d3132ecfb9d74c83d2875f1e07a565bfb6abc06822d63'
spec=importlib.util.spec_from_file_location('verified_online_catalog',catalog_file)
catalog=importlib.util.module_from_spec(spec);spec.loader.exec_module(catalog)
for template in (117534,117535,163313,710092):
    result=catalog.search(str(template))
    assert result['rows'][0]['id']==template
assert any(row['id']==710092 for row in catalog.search('贤者 卷轴')['rows'])

async def check(path):
    account=LocalAccount(LocalState(path));account.enable_characters();account.get_inventory_snapshot()
    app=Application(ServerConfig(state_file=path,log_dir=path.parent/'logs'));app.account=account
    session=await app.session()
    try:
        session.role='game';session.phase='town_ready';session.completed.update((0x28,0x225,0x227))
        assert session.item_test and session.client_build=='dx11_260923'
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE characters SET level=4 WHERE uid=1001')
            db.execute('UPDATE reward_balances SET experience=? WHERE uid=1001',(client_data().thresholds[3],))
            item=grant_items(db,[dict(template=710092,metadata=2,group=4,quantity=3)],1001)[0]
        event=Event(0x202,kind=0x219,payload=struct.pack('>QQiiIB',item['uid'],2,0,0,0,1))
        events=priority_handlers(session,event,500)
        assert [e.kind for e in events]==[0x21a,0xd9] and struct.unpack_from('>i',events[0].payload)[0]==0
        with closing(sqlite3.connect(path))as db:
            assert db.execute('SELECT level FROM characters WHERE uid=1001').fetchone()==(6,)
            assert db.execute('SELECT count FROM inventory_items WHERE uid=?',(item['uid'],)).fetchone()==(1,)
            frozen=list(db.iterdump())
        session.phase='dungeon_active'
        refused=priority_handlers(session,event,501)
        assert len(refused)==1 and struct.unpack_from('>i',refused[0].payload)[0]!=0
        with closing(sqlite3.connect(path))as db:assert list(db.iterdump())==frozen
        session.phase='town_ready'
        session._chip_reset_local_live=False
        refused=priority_handlers(session,event,502)
        assert len(refused)==1 and struct.unpack_from('>i',refused[0].payload)[0]!=0
        with closing(sqlite3.connect(path))as db:assert list(db.iterdump())==frozen
    finally:
        await app.release(session);app.close()

with tempfile.TemporaryDirectory(prefix='gm-scroll-flow-',dir=WORK)as directory:
    asyncio.run(check(Path(directory)/'private.sqlite3'))
result=dict(ok=True,gm_catalog_exact_live_source=True,gm_search_all_four_templates=True,original_session_dispatch=True,batch_debit_and_level=True,dungeon_and_expired_session_refused=True,private_only=True,online_mutations=0)
(WORK/'flow-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps(result))
