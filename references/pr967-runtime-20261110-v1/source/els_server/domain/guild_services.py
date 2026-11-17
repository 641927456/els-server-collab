"""Owned service contracts and grants earned by an actual GuildAgit visit."""
from contextlib import closing
import json,sqlite3,struct,time
from els_server.storage import guild_system_state as system
from els_server.storage.guild_membership_state import snapshot

# Current KIM special subtypes59/60/58; qualified Enum/BuffTemplet IDs.
CONTRACTS={135862:(1034,1115,3600),135863:(1035,1116,3600),135864:(1033,1114,86400)}
BUFFS={b:(t,f,period)for t,(b,f,period)in CONTRACTS.items()}


def extend(saved,template,operation,now):
    buff,_,duration=CONTRACTS[template];state=saved['system']
    old=state['services'].get(str(buff),{})
    end=max(now,old.get('end',0))+duration
    if end>now+48*3600:raise ValueError('Guild service exceeds current48hour maximum')
    row=dict(template=template,start=now,end=end,operation=operation)
    state['services'][str(buff)]=row
    return row


def source(db,guild,buff,row):
    template=BUFFS[buff][0]
    proof=db.execute('SELECT guild_id,kind,result,created_at FROM native_guild_operations_v2 WHERE operation=?',
                     (row['operation'],)).fetchone()
    if (proof is None or proof[:2]!=(guild,0x219)or row['template']!=template
        or row['start']!=proof[3]or not row['start']<row['end']<=row['start']+48*3600):
        raise ValueError('Guild service source receipt')
    result=json.loads(proof[2])
    if result.get('template')!=template or result.get('service')!=row:raise ValueError('Guild service receipt differs from grant')


def visit(db,saved,now):
    """Caller has guarded the actual504 or currently ready GuildAgit scene."""
    state=saved['system'];member=system.member(state,saved['owner'])
    current=member.setdefault('services',{});changed=False
    for key,row in state['services'].items():
        buff=int(key)
        if buff not in BUFFS:raise ValueError('Unknown guild service')
        if not row['start']<=now<row['end']:continue
        source(db,saved['id'],buff,row)
        if current.get(key)!=row:current[key]=dict(row);changed=True
    if changed:system.write(db,saved['id'],state)
    return changed


def rows(db,owner,account,now):
    saved=snapshot(db,owner,account)
    if saved is None:return []
    result=[]
    grants=saved['system']['member_details'].get(str(owner),{}).get('services',{})
    for key,row in grants.items():
        buff=int(key)
        if buff not in BUFFS:raise ValueError('Unknown saved guild service grant')
        if not row['start']<=now<row['end']:continue
        source(db,saved['id'],buff,row)
        result.append(dict(owner=owner,template=buff,start=row['start'],end=row['end'],_guild=True,
                           source_operation=row['operation'],guild=saved['id']))
    return sorted(result,key=lambda r:r['template'])


def world_rows(s,db,now):return rows(db,s.account.uid,s.account.account_id,now)

def ui_notification(db,saved,now):
    # 325F930/DCEC70 ACC is a vector<pair<buff ID,local end datetime>>.
    # It updates GuildManager+298 and the native Guild Buff Benefit tab.
    # These are global contracts; personal combat buffs still require visit().
    from datetime import datetime,timezone,timedelta
    from els_server.protocol.guild_system_messages import reply,text
    active=[]
    if saved is not None:
        for key,row in saved['system']['services'].items():
            buff=int(key)
            if buff not in BUFFS:raise ValueError('Unknown guild contract UI source')
            if not row['start']<=now<row['end']:continue
            source(db,saved['id'],buff,row)
            active.append((buff,datetime.fromtimestamp(row['end'],timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')))
    return reply(0xacc,struct.pack('>I',len(active))+b''.join(struct.pack('>i',buff)+text(end)for buff,end in sorted(active)))


def wire_row(owner,row):
    buff=row['template']
    if(row.get('_guild')is not True or row['owner']!=owner or buff not in BUFFS
       or not 1<=row['start']<row['end']<2**31 or row['end']-row['start']>48*3600):
        raise ValueError('Guild world service row')
    return bytes(8)+struct.pack('>iIQfBif?if?iiiQQ',buff,0,owner,0.,1,0,0.,False,BUFFS[buff][1],1.,False,-1,0,0,row['start'],row['end'])


def synchronize(s):
    from els_server.domain.elixir_flow import enabled,ready,context,prepare
    if not enabled(s)or not ready(s):return []
    from els_server.storage.world_elixirs import _state
    from els_server.protocol.protocol_codec import encode_event
    now=int(time.time());old=getattr(s,'_guild_service_sent',None);old_ui=getattr(s,'_guild_contract_sent',None)
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        try:
            db.execute('BEGIN');guard=None
            saved=snapshot(db,s.account.uid,s.account.account_id)
            if s.phase=='guild_agit_ready'and saved is not None and any(
                row['end']>now and system.member(saved['system'],saved['owner']).get('services',{}).get(key)!=row
                for key,row in saved['system']['services'].items()):
                from els_server.domain.guild_agit_flow import bank_capture
                same,guard=bank_capture(s)
                db.rollback()
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
                now=int(time.time())
                saved=snapshot(db,s.account.uid,s.account.account_id)
                visit(db,saved,now)
            current=world_rows(s,db,now)
            stamp=(context(s),tuple((r['template'],r['start'],r['end'])for r in current))
            answer=[]if stamp==old or not current and old is None else prepare(s)(db,_state(db,s.account.uid,now),None)
            ui=ui_notification(db,saved,now);ui_stamp=(context(s),ui.payload)
            if ui_stamp!=old_ui and(saved is not None or old_ui is not None):answer.append(ui)
            progress_stamp=None if saved is None else (context(s),saved['id'],saved['system']['experience'])
            previous_progress=getattr(s,'_guild_profile_progress',None)
            if progress_stamp is not None and previous_progress is not None and progress_stamp!=previous_progress:
                from els_server.domain.guild_initial_profile import profile
                from els_server.protocol.guild_membership_profile import full_notification
                answer.append(full_notification(profile(saved,db=db,now=now)))
            for e in answer:encode_event(e)
            if guard is not None:guard(db)
            if not enabled(s)or stamp[0]!=context(s):raise ValueError('Guild service current actor changed')
            db.commit()
        except BaseException:db.rollback();raise
    s._guild_service_sent=stamp
    s._guild_contract_sent=ui_stamp
    s._guild_profile_progress=progress_stamp
    return answer


def economy(db,owner,account,now):
    active=rows(db,owner,account,now)
    return dict(experience_rate=.5 if any(r['template']==1034 for r in active)else 0.,
                profession_rate=.2 if any(r['template']==1035 for r in active)else 0.,services=active)


def profession_xp(db,owner,account,amount):
    # The existing profession curve and cap still own advancement and rounding.
    if type(amount)is not int or not 0<=amount<2**31:raise ValueError('Guild profession original XP amount')
    if not amount:return 0
    now=int(time.time())
    contract=bool(economy(db,owner,account,now)['profession_rate'])
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_expiration import expired
    # Static714298 identity is already qualified by guild_quests.definitions.
    candidates=db.execute('SELECT uid FROM inventory_items WHERE owner=?AND template=714298',(owner,)).fetchall()
    medal=False
    for(uid,)in candidates:
        for item in load_items(db,owner,item_uid=uid):
            if(item['template'],item['metadata'],item['group'],item['count'])!=(714298,0,4,1):raise ValueError('Held profession medal source shape')
            if 'expires_at'not in item:raise ValueError('Three-day profession medal lost source expiry')
            medal=medal or not expired(item,now=now)
    count=int(contract)+int(medal)
    if count==2:
        from pathlib import Path
        choice=json.loads((Path(__file__).resolve().parents[1]/'data/guild_profession_policy.json').read_bytes())['held_badge_and_contract']
        if choice not in('additive','maximum'):raise ValueError('Combined profession badge and contract policy requires explicit decision')
        if choice=='maximum':count=1
    return amount+amount*count//5
