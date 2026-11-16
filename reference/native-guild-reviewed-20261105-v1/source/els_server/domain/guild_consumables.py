"""Owned guild capacity card and Great Gnosis, through current219/21A."""
from contextlib import closing
import sqlite3,struct,hashlib,json
from els_server.storage import guild_system_state as system
from els_server.storage.inventory_state import load_items,owned_template
from els_server.protocol.career_messages import use_request,use_ack
from els_server.domain import guild_rules,guild_skills

from els_server.domain import guild_services,guild_skins
TEMPLATES=frozenset((110846,110859))|guild_services.CONTRACTS.keys()|guild_skins.licenses().keys()
KINDS=frozenset((0x219,))

def handles(s,event,sequence):
    if len(event.payload)<8 or s.account.store is None:return False
    owner=s.account.uid;operation=s.shop_session_id+':guild-system:'+str(owner)+':'+str(sequence)
    with closing(sqlite3.connect(s.account.store.path))as db:
        if system.exists(db,'native_guild_operations_v2'):
            row=db.execute('SELECT owner,kind,result FROM native_guild_operations_v2 WHERE operation=?',(operation,)).fetchone()
            if row and row[:2]==(owner,0x219)and json.loads(row[2]).get('template')in TEMPLATES:return True
        return owned_template(db,owner,struct.unpack_from('>Q',event.payload)[0])in TEMPLATES

def command(db,s,event,saved,operation,now):
    uid=use_request(event.payload);owner=saved['owner'];state=saved['system']
    before=load_items(db,owner);item=next((i for i in before if i['uid']==uid),None)
    if item is None or item['template']not in TEMPLATES or not guild_rules.permission(saved,state,3):raise ValueError('Owned guild service item and authority required')
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    require_current(item,now=now);require_unlocked(item,now=now)
    if item['template']==110846:
        if state['capacity']>=300:raise ValueError('Guild member capacity already maximal')
        state['capacity']=min(300,state['capacity']+10)
    elif item['template']in guild_skins.licenses():
        guild_skins.unlock(saved,guild_skins.licenses()[item['template']],operation,item['template'])
    elif item['template']in guild_services.CONTRACTS:
        guild_services.extend(saved,item['template'],operation,now)
    else:
        expiry=max([now]+[p['cash_expires']for p in state['pages'].values()])+15*86400
        if expiry>now+90*86400:raise ValueError('Guild Gnosis duration exceeds90days')
        for key,page in tuple(state['pages'].items()):
            page=guild_skills.effective(page,now);page.update(cash_expires=expiry,cash_points=5);state['pages'][key]=page
    from els_server.storage.item_instances import remove
    if item['count']==1:remove(db,owner,item)
    else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,uid))
    after=load_items(db,owner);position=(item['group'],item['slot']);current=next((i for i in after if(i['group'],i['slot'])==position),None)
    from els_server.storage.inventory_actions import _commit
    digest=hashlib.sha256(str(owner).encode()+b':'+str(event.kind).encode()+b':'+event.payload).hexdigest()
    _commit(db,operation,digest,owner,event.kind,[position],before,after)
    system.write(db,saved['id'],state)
    from els_server.domain.guild_initial_profile import profile
    from els_server.protocol.guild_membership_profile import full_notification
    return [use_ack([(position,current)],item['template'],db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0])],[full_notification(profile(saved,db=db,now=now))],item['template']

def replay(db,saved,kind,payload,operation,digest,now,template):
    from els_server.storage.inventory_actions import _previous
    from els_server.storage.equipment_receipt_state import current_changes
    positions=_previous(db,operation,digest)
    if positions is None:raise ValueError('Guild service lost inventory receipt')
    return [use_ack(current_changes(db,operation,saved['owner'],kind,positions,load_items(db,saved['owner'])),template,db.execute('SELECT ed FROM reward_balances WHERE uid=?',(saved['owner'],)).fetchone()[0])]
