"""Every native route, transaction rollback, replay, ownership and Artifact restart."""
from contextlib import closing
from pathlib import Path
import json,sqlite3,struct,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.characters import DEFAULT_CHARACTER,Characters
from els_server.domain.careers import RULES,PARENTS,transition
from els_server.domain.character_rules import CLASSES,artifact_wire
from els_server.storage.careers import use_career_item
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.protocol.protocol_codec import Event

promotions=[(t,r) for t,r in RULES.items() if r['kind'].startswith('advancement_')]
assert len(promotions)==180
for t,r in promotions:
    c=dict(DEFAULT_CHARACTER,unit_type=r['unit_type'],unit_class=PARENTS[r['target']],level=99,transcendence=r['kind']=='advancement_3',artifact=None)
    assert transition(c,t)['unit_class']==r['target']
for t,r in RULES.items():
    if r['kind']!='master_advancement':continue
    c=dict(DEFAULT_CHARACTER,unit_type=r['unit_type'],unit_class=r['target'],level=99,transcendence=True,artifact=None)
    a=transition(c,t);assert a['master'] and a['artifact']['template']==c['unit_type']
    assert len(artifact_wire(a))==40
    try:transition(a,t)
    except ValueError:pass
    else:raise AssertionError('Duplicate master advancement')
for t,r in RULES.items():
    if r['kind'] not in ('class_change','transcendence_change','master_change'):continue
    target=r['target'];meta=CLASSES[target]
    current=next(k for k,v in CLASSES.items() if k!=target and v==meta)
    c=dict(DEFAULT_CHARACTER,unit_type=r['unit_type'],unit_class=current,level=99,
           transcendence=r['kind']!='class_change' or meta['stage']==3,
           master=r['kind']=='master_change',artifact=None)
    if c['master']:c['artifact']=dict(template=c['unit_type'],evolution=2,level=7,experience=125,potentials=[0]*4)
    after=transition(c,t)
    assert after['unit_class']==target and after['artifact']==c['artifact']
    try:transition(dict(c,unit_class=CLASSES[current]['base_class']),t)
    except ValueError:pass
    else:raise AssertionError('Wrong-stage class ticket accepted')

with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'test.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
    original_character=account.character()
    other=account.characters.create('OtherRole',2,'create-other')
    t,r=next((t,r) for t,r in RULES.items() if r['kind']=='master_advancement' and r['unit_type']==2)
    def dump():
        with closing(sqlite3.connect(path)) as db:return list(db.iterdump())
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE characters SET level=99,unit_class=?,transcendence=1 WHERE uid=?',(r['target'],other['uid']))
        item=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],quantity=2,group=4)],other['uid'])[0]
    payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
    before=dump()
    try:use_career_item(path,1001,payload,'wrong-owner')
    except ValueError:pass
    else:raise AssertionError('Foreign inventory consumed')
    assert dump()==before
    receipt=use_career_item(path,other['uid'],payload,'master');assert not receipt['replayed']
    saved=dump();assert use_career_item(path,other['uid'],payload,'master')['replayed'] and dump()==saved
    try:use_career_item(path,other['uid'],payload,'second-master')
    except ValueError:pass
    else:raise AssertionError('Repeated master item consumed')
    assert dump()==saved
    c=Characters(path).get(other['uid']);assert c['master'] and c['artifact']['template']==2
    assert account.for_character(other['uid']).get_inventory_snapshot()['items'][0]['count']==1
    assert account.character()==original_character
    # Same transport sequence replays idempotently, never re-spawns spirit.
    session=LocalSession(account.for_character(other['uid']),enter_town=True,client_build='dx11_260923')
    session.item_test=True;session.role='game';session.phase='town_ready'
    fail=session.handle(Event(0x202,kind=0x219,payload=payload),request_sequence=5)
    assert len(fail)==1 and struct.unpack_from('>i',fail[0].payload)[0]!=0
    assert session.periodic_notifications()==[]
    # Fresh native item use: restore complete Artifact before stage notification.
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE characters SET master=0 WHERE uid=?',(other['uid'],))
        db.execute('DELETE FROM character_artifacts WHERE uid=?',(other['uid'],))
        # Reset the dedicated Master slot along with the artificial downgrade.
        row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(other['uid'],)).fetchone()
        if row:
            slots=list(struct.unpack('>22i',row[0]));slots[21]=0
            db.execute('UPDATE skill_slots SET payload=? WHERE uid=?',(struct.pack('>22i',*slots),other['uid']))
    success=session.handle(Event(0x202,kind=0x219,payload=payload),request_sequence=6)
    assert [e.kind for e in success]==[0x21a,0xd9,0x59f,0x55b]
    assert struct.unpack('>ii',success[-2].payload)==(0,2)
    replay=session.handle(Event(0x202,kind=0x219,payload=payload),request_sequence=6)
    assert [e.kind for e in replay]==[0x21a,0xd9]
    ordinary=LocalSession(account,enter_town=True,client_build='dx11_260923')
    ordinary.item_test=True;ordinary.role='game';ordinary.phase='town_ready'
    assert ordinary.periodic_notifications()==[]
print('PASS: all 180 advancement edges, 60 master spirits, ownership/rollback/replay and restart persistence.')
