"""+11/+12/+13 enhancement scrolls: consume, set level, replay and reject repeat."""
import sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.enhancement_scroll import SCROLLS,definitions,level as scroll_level
from els_server.domain.local_session import LocalAccount
from els_server.domain.normal_equipment import definitions as equipment_definitions
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,VERIFIED_TEMPLATES
from els_server.storage import enhancement_scroll as store
from els_server.storage.inventory_state import InventoryState
from els_server.storage.local_state import LocalState

assert set(SCROLLS)=={163313,117535,117534,130152,130150,130149}
equipment=next(iter(equipment_definitions()))
for SCROLL,target in ((163313,13),(117535,12),(117534,11),(130152,10),(130150,8),(130149,7)):
    assert SCROLL in VERIFIED_TEMPLATES and scroll_level(SCROLL)==target
    with tempfile.TemporaryDirectory() as directory:
        save=Path(directory)/'save.sqlite3'
        account=LocalAccount(LocalState(save));account.enable_characters();InventoryState(save)
        with closing(sqlite3.connect(save)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            from els_server.storage.item_instances import insert,next_uid
            scroll_row=insert(db,1001,dict(uid=next_uid(db),template=SCROLL,
                metadata=VERIFIED_TEMPLATES[SCROLL],count=1,group=TEMPLATE_BAG_GROUPS[SCROLL],slot=0))
            gear_row=insert(db,1001,dict(uid=next_uid(db),template=equipment,metadata=1,count=1,group=1,slot=0))
        payload=struct.pack('>QQ',scroll_row['uid'],gear_row['uid'])
        operation='scroll-test-'+str(target)
        assert store.candidate(save,1001,payload,operation)
        assert not store.candidate(save,1001,struct.pack('>QQ',gear_row['uid'],0),'other')
        events=store.use(save,1001,account.account_id,payload,operation)
        assert events and events[-1].kind==0x21a
        snapshot=InventoryState(save).snapshot()
        items={i['template']:i for i in snapshot['items']}
        assert SCROLL not in items
        assert items[equipment]['enhancement']==target
        before_replay=InventoryState(save).snapshot()
        replay=store.use(save,1001,account.account_id,payload,operation)
        assert replay and replay[-1].kind==0x21a
        assert InventoryState(save).snapshot()==before_replay
        with closing(sqlite3.connect(save)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            from els_server.storage.item_instances import insert,next_uid
            again=insert(db,1001,dict(uid=next_uid(db),template=SCROLL,
                metadata=VERIFIED_TEMPLATES[SCROLL],count=1,group=TEMPLATE_BAG_GROUPS[SCROLL],slot=0))
        try:store.use(save,1001,account.account_id,struct.pack('>QQ',again['uid'],gear_row['uid']),'again-'+str(target))
        except ValueError:pass
        else:raise AssertionError('Already upgraded equipment accepted another scroll')
        snapshot=InventoryState(save).snapshot()
        assert any(i['template']==SCROLL for i in snapshot['items'])
        assert next(i for i in snapshot['items'] if i['template']==equipment)['enhancement']==target
print('PASS: +11/+12/+13 scrolls consume, set their level, replay receipts and refuse duplicates.')
