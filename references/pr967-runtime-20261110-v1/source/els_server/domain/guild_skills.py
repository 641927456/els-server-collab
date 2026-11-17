"""Native guild skill pages; the client retains skill calculation and effects."""
from pathlib import Path
from functools import lru_cache
import hashlib,json,struct,copy
from els_server.domain import guild_rules as rules
from els_server.storage import guild_system_state as system
from els_server.protocol.social_messages import Reader
from els_server.protocol.guild_system_messages import reply,result
from els_server.protocol.guild_membership_profile import _string

KINDS=frozenset((0x2a2,0x2a5,0x843,0x846,0xac6,0xe44))
READS=frozenset((0xe44,))

@lru_cache(maxsize=1)
def tree():
    raw=(Path(__file__).resolve().parents[1]/'data/guild_skill_tree.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='5c11a24afbbf2f433d24a33de4c57700ece3e8fe3bcba417c25e3afd6fb47f4a':raise ValueError('Guild skill tree source changed')
    return {r['m_iSkillID']:r for r in json.loads(raw)}

def effective(page,now):
    page=copy.deepcopy(page)
    if page['cash_expires']<=now:
        for skill,rank in page.get('cash_skills',{}).items():
            remaining=page['skills'][skill]-rank
            if remaining:page['skills'][skill]=remaining
            else:page['skills'].pop(skill)
        page.update(cash_points=0,cash_expires=0,cash_skills={})
    return page

def page_profile(state,page,now):
    from datetime import datetime,timezone,timedelta
    page=effective(page,now);cash=page.get('cash_skills',{})
    return dict(skills=tuple((int(k),v,cash.get(k,0))for k,v in sorted(page['skills'].items(),key=lambda r:int(r[0]))),
        points=rules.level(state['experience'])-sum(page['skills'].values())+sum(cash.values()),
        cash_points=page['cash_points']-sum(cash.values()),max_cash_points=page['cash_points'],
        expiry=''if not page['cash_expires']else datetime.fromtimestamp(page['cash_expires'],timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),alias=page['alias'])

def pages_notification(state,now):
    from els_server.protocol.guild_membership_profile import pages_wire
    return reply(0x845,pages_wire({int(k):page_profile(state,p,now)for k,p in state['pages'].items()}))

def command(db,s,event,saved,operation,now):
    state=saved['system'];kind=event.kind;r=Reader(event.payload);owner=saved['owner']
    for key,p in tuple(state['pages'].items()):state['pages'][key]=effective(p,now)
    if kind==0xe44:
        # 1116370/BE51F0: request token, text, purpose; response adds result
        # and remote rejection count. Purpose25 returns to the native guild
        # alias callback, which retains its original client word filter.
        token=r.scalar('Q');text=r.text();purpose=r.scalar('i');r.end()
        if saved['grade']not in(1,2)or purpose!=25:raise ValueError('Guild alias text purpose/authority')
        return [reply(0xe45,struct.pack('>iQi',0,token,0)+_string(text)+struct.pack('>i',purpose))],[]
    if kind==0xac6:
        # C55250/DB5C10: map<signed page byte,wstring>;9BD750 ACK=result only.
        count=r.scalar('I');aliases={}
        if saved['grade']not in(1,2)or not 1<=count<=3:raise ValueError('Guild alias authority/map')
        for _ in range(count):
            index=r.scalar('b');text=r.text()
            if str(index)not in state['pages']or index in aliases:raise ValueError('Guild alias owned unique page')
            aliases[index]=text
        r.end()
        for index,text in aliases.items():state['pages'][str(index)]['alias']=text
        answer=[result(0xac7)];notes=[pages_notification(state,now)]
    elif kind==0x843:
        count=r.scalar('b');r.end()
        if not rules.permission(saved,state,3)or count!=len(state['pages'])+1 or count not in(2,3):raise ValueError('Guild page expansion authority/count')
        cost=rules.calls('SetGuildSkillPage')[0][0]['EXPAND_COST'][str(count-1)]['GUILD_COIN']
        system.change_currency(db,saved['id'],-cost,0,operation,'current guild skill page expansion',now)
        expiry=max(p['cash_expires']for p in state['pages'].values())
        state['pages'][str(count)]=dict(skills={},cash_points=5 if expiry>now else 0,cash_expires=expiry,alias='')
        answer=[reply(0x844,struct.pack('>ib',0,count))];notes=[pages_notification(state,now)]
    elif kind==0x846:
        index=r.scalar('b');r.end()
        if str(index)not in state['pages']:raise ValueError('Unowned guild skill page')
        system.member(state,owner)['page']=index
        answer=[reply(0x847,struct.pack('>ib',0,index))];notes=[]
    else:
        skill=r.scalar('i');index=r.scalar('b');r.end();key=str(skill)
        if not rules.permission(saved,state,2 if kind==0x2a2 else 3)or str(index)not in state['pages']or skill not in tree():raise ValueError('Guild skill authority/page/skill')
        page=state['pages'][str(index)];cash=page.setdefault('cash_skills',{});rank=page['skills'].get(key,0);row=tree()[skill]['m_iRowIndex']
        points=page_profile(state,page,now)
        if kind==0x2a2:
            if rank>=tree()[skill]['m_iMasterLevel']or sum(page['skills'].values())<row*5 or points['points']+points['cash_points']<1:raise ValueError('Guild skill rank/row/available GSP')
            if points['points']<1:cash[key]=cash.get(key,0)+1
            page['skills'][key]=rank+1;points=page_profile(state,page,now)
            answer=[result(0x2a3)];notes=[reply(0x2a4,struct.pack('>iiiiiQb',skill,rank+1,cash.get(key,0),points['points'],points['cash_points'],owner,index))]
        else:
            if rank<1:raise ValueError('Guild skill has no invested point')
            if cash.get(key,0) and any(tree()[int(k)]['m_iRowIndex']>row and v for k,v in page['skills'].items()):raise ValueError('Recover lower bonus guild skill first')
            from els_server.storage.inventory_state import load_items
            from els_server.storage.item_instances import remove
            from els_server.storage.inventory_actions import _commit
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            before=load_items(db,owner);flute=next((i for i in before if i['template']==110857),None)
            if flute is None:raise ValueError('Owned flute required to recover one GSP')
            require_current(flute,now=now);require_unlocked(flute,now=now)
            if flute['count']==1:remove(db,owner,flute)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,flute['uid']))
            bonus=int(cash.get(key,0)>0)
            if bonus:cash[key]-=1
            if rank==1:page['skills'].pop(key);cash.pop(key,None)
            else:page['skills'][key]=rank-1
            positions=[(flute['group'],flute['slot'])];after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
            digest=hashlib.sha256(str(owner).encode()+b':'+str(kind).encode()+b':'+event.payload).hexdigest()
            _commit(db,operation,digest,owner,kind,positions,before,after)
            from els_server.domain.guild_shop import changed
            answer=[reply(0x2a6,bytes(4)+changed([(p,current.get(p))for p in positions]))]
            notes=[reply(0x2a7,struct.pack('>iiiQb',skill,1-bonus,bonus,owner,index))]
    system.write(db,saved['id'],state)
    return answer,notes

def replay(db,saved,kind,payload,operation,digest,now):
    if kind!=0x2a5:return None
    from els_server.storage.inventory_actions import _previous
    from els_server.storage.inventory_state import load_items
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.domain.guild_shop import changed
    positions=_previous(db,operation,digest)
    if positions is None:raise ValueError('Guild skill recovery lost inventory receipt')
    return [reply(0x2a6,bytes(4)+changed(current_changes(db,operation,saved['owner'],kind,positions,load_items(db,saved['owner']))))]

def failure(kind):
    if kind==0xe44:return reply(0xe45,struct.pack('>iQiIi',1,0,0,0,25))
    if kind==0x2a5:return reply(0x2a6,struct.pack('>iI',1,0))
    if kind in(0x843,0x846):return reply(kind+1,struct.pack('>ib',1,0))
    return result(kind+1,1)
