"""Circuit option presets and online GM item mail (queue -> letter -> claim)."""
import json,sqlite3,sys,tempfile,time,uuid
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain import equipment_circuit_rules as circuits
from els_server.domain.gm_item_options import apply,spec
from els_server.domain.local_session import LocalAccount
from els_server.storage import gm_mail_queue,mail_attachments
from els_server.storage.inventory_state import InventoryState
from els_server.storage.local_state import LocalState

TEMPLATE=118554  # L-2 上衣增幅电路（演算）
option=circuits.material(TEMPLATE)['options'][0]
choice=spec(TEMPLATE)
assert choice['kind']=='choice' and len(choice['choices'])>100
assert option in {c['id'] for c in choice['choices']}
assert apply(TEMPLATE,{'1':[option]})=={'1':[option]}
for bad in ({'1':[0]}, {'28':[0]*16}, None):
    if bad is None:assert apply(TEMPLATE,bad) is None;continue
    try:apply(TEMPLATE,bad)
    except ValueError:pass
    else:raise AssertionError('Invalid circuit option accepted')

with tempfile.TemporaryDirectory() as directory:
    save=Path(directory)/'save.sqlite3'
    LocalAccount(LocalState(save)).enable_characters();InventoryState(save)
    operation=str(uuid.uuid4())
    job=dict(operation_id=operation,uid=1001,template=TEMPLATE,quantity=1,
             option_groups={'1':[option]},title='GM 发放',body='测试邮件',
             reason='测试邮件发放',sender='GM')
    assert gm_mail_queue.enqueue(save,job)['state']=='queued'
    assert gm_mail_queue.enqueue(save,job)['state']=='queued'
    assert gm_mail_queue.process(save)==1
    status=gm_mail_queue.status(save)
    assert len(status['done'])==1 and not status['queued'] and not status['failed']
    receipt=status['done'][0]
    with closing(sqlite3.connect(save)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        changes=mail_attachments.claim(db,1001,receipt['mail_ids'][0],now=int(time.time()))
    assert [(p,(i or {}).get('count')) for p,i in changes]==[((1,0),1)]
    item=next(i for i in InventoryState(save).snapshot()['items'] if i['template']==TEMPLATE)
    assert item['option_groups']=={'1':[option]}
    # Non-stackable circuits split into one letter per instance (max 20).
    multi=str(uuid.uuid4())
    gm_mail_queue.enqueue(save,dict(job,operation_id=multi,quantity=2))
    assert gm_mail_queue.process(save)==1
    split=next(r for r in gm_mail_queue.status(save)['done'] if r['operation_id']==multi)
    assert len(split['mail_ids'])==2
    for mail_id in split['mail_ids']:
        with closing(sqlite3.connect(save)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            mail_attachments.claim(db,1001,mail_id,now=int(time.time()))
    circuits=[i for i in InventoryState(save).snapshot()['items'] if i['template']==TEMPLATE]
    assert len(circuits)==3 and all(i['option_groups']=={'1':[option]} for i in circuits)
    # A rejected option is reported, never delivered.
    bad=str(uuid.uuid4())
    gm_mail_queue.enqueue(save,dict(job,operation_id=bad,option_groups={'1':[0]}))
    assert gm_mail_queue.process(save)==0
    failed=gm_mail_queue.status(save)['failed']
    assert failed and failed[0]['operation_id']==bad and failed[0].get('error')
    # Unknown templates stay queued for the next restart; staged jobs promote.
    unseen=str(uuid.uuid4())
    staged=gm_mail_queue.directory(save)/'staged';staged.mkdir(parents=True,exist_ok=True)
    (staged/(unseen+'.json')).write_text(json.dumps(dict(job,operation_id=unseen,template=999999999)),encoding='utf8')
    gm_mail_queue.process(save)
    queued={r['operation_id'] for r in gm_mail_queue.status(save)['queued']}
    assert unseen in queued
print('PASS: circuit option presets, queue idempotence, online mail delivery/claim and rejected options.')
