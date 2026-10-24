"""GM scroll use queue: consume an owned +N scroll and set one equipment level."""
import sqlite3,sys,tempfile,uuid
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount
from els_server.domain.normal_equipment import definitions as equipment_definitions
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,VERIFIED_TEMPLATES
from els_server.storage import gm_scroll_queue
from els_server.storage.inventory_state import InventoryState
from els_server.storage.local_state import LocalState

SCROLL,TARGET=117535,12
equipment=next(iter(equipment_definitions()))
with tempfile.TemporaryDirectory() as directory:
    save=Path(directory)/'save.sqlite3'
    account=LocalAccount(LocalState(save));account.enable_characters();InventoryState(save)
    with closing(sqlite3.connect(save)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        from els_server.storage.item_instances import insert,next_uid
        gear=insert(db,1001,dict(uid=next_uid(db),template=equipment,metadata=1,count=1,group=1,slot=0))
        scroll=insert(db,1001,dict(uid=next_uid(db),template=SCROLL,
            metadata=VERIFIED_TEMPLATES[SCROLL],count=1,group=TEMPLATE_BAG_GROUPS[SCROLL],slot=0))
    job=dict(operation_id=str(uuid.uuid4()),uid=1001,item_uid=gear['uid'],scroll=SCROLL,reason='GM 使用卷轴测试')
    assert gm_scroll_queue.enqueue(save,job)['state']=='queued'
    assert gm_scroll_queue.process(None,save)==1
    status=gm_scroll_queue.status(save)
    assert status['done'] and not status['failed']
    snapshot=InventoryState(save).snapshot()
    items={i['template']:i for i in snapshot['items']}
    assert items[equipment]['enhancement']==TARGET
    assert SCROLL not in items
    # No scroll left: the next job fails without touching the equipment.
    second=dict(job,operation_id=str(uuid.uuid4()))
    gm_scroll_queue.enqueue(save,second)
    assert gm_scroll_queue.process(None,save)==0
    assert gm_scroll_queue.status(save)['failed']
    assert next(i for i in InventoryState(save).snapshot()['items'] if i['template']==equipment)['enhancement']==TARGET
    # A Lv.11 scroll must not downgrade a +12 item.
    with closing(sqlite3.connect(save)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        from els_server.storage.item_instances import insert,next_uid
        insert(db,1001,dict(uid=next_uid(db),template=117534,metadata=VERIFIED_TEMPLATES[117534],
            count=1,group=TEMPLATE_BAG_GROUPS[117534],slot=1))
    gm_scroll_queue.enqueue(save,dict(job,operation_id=str(uuid.uuid4()),scroll=117534))
    assert gm_scroll_queue.process(None,save)==0
    assert next(i for i in InventoryState(save).snapshot()['items'] if i['template']==equipment)['enhancement']==TARGET
print('PASS: GM scroll use consumes the scroll, sets its level, and refuses missing or downgrade scrolls.')
