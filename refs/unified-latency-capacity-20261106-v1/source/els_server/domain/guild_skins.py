"""Current GuildSkinTemplate ownership, original NPC purchase and skin selection."""
from functools import lru_cache
from pathlib import Path
import hashlib,json,struct
from els_server.domain import guild_rules as rules
from els_server.storage import guild_system_state as system
from els_server.protocol.social_messages import Reader
from els_server.protocol.guild_system_messages import reply

KINDS=frozenset((0x84a,0x84c))


@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/guild_skins.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='5a7fb96f8669da7a7b2d9805f515096b23cbece12f76eb12d06cabddcdc352e8':
        raise ValueError('Guild skin source changed')
    return {int(k):v for k,v in json.loads(raw)['skins'].items()}


def licenses():return {r['item']:world for world,r in catalog().items()if r['item']}


def definitions():
    from els_server.game_data import client_data
    for template,world in licenses().items():
        r=client_data().item(template)
        if (hashlib.sha256(r['record']).hexdigest()!=catalog()[world]['item_sha256']
            or(r['item_type'],r['metadata'],r['flags8'])!=(7,0,56)):
            raise ValueError('Guild skin owned reader differs from current source')
        yield dict(template=template,metadata=0,group=4,max_stack=1)


def owned(state):return {623,*map(int,state['skins'])}


def rows(state):
    selected=state['skin']or 623
    if selected not in owned(state):raise ValueError('Selected guild skin is not owned')
    # DB63E0 /325DBB0: map key is the world definition, bool selects current;
    # the intermediate i32 is ignored by that consumer and retains ctor zero.
    return tuple((world,0,world==selected)for world in sorted(owned(state)))


def unlock(saved,world,operation,template=0):
    if world not in catalog()or world in owned(saved['system']):raise ValueError('Guild skin already owned or unknown')
    saved['system']['skins'][str(world)]=dict(operation=operation,template=template)


def command(db,s,event,saved,operation,now):
    if s.phase!='guild_agit_ready':raise ValueError('Guild skin NPC requires actual GuildAgit')
    r=Reader(event.payload);world=r.scalar('i');r.end()
    if world not in catalog():raise ValueError('Unknown current guild skin')
    state=saved['system'];notes=[]
    if event.kind==0x84a:
        if not rules.permission(saved,state,3)or not catalog()[world]['coin_purchase']:
            raise ValueError('Guild skin purchase authority/currency')
        unlock(saved,world,operation)
        coins,_=system.change_currency(db,saved['id'],-catalog()[world]['coins'],0,operation,'guild-skin',now)
        notes.append(reply(0x7ec,struct.pack('>i',coins)))
    else:
        if saved['grade']not in(1,2)or world not in owned(state):raise ValueError('Guild skin selection authority/ownership')
        if world==(state['skin']or 623):raise ValueError('Guild skin already selected')
        state['skin']=world
        notes.append(reply(0x84e,struct.pack('>i',world)))
    system.write(db,saved['id'],state)
    from els_server.domain.guild_initial_profile import profile
    from els_server.protocol.guild_membership_profile import full_notification
    notes.append(full_notification(profile(saved,db=db,now=now)))
    return [reply(event.kind+1,struct.pack('>ii',0,world))],notes


def failure(kind):return reply(kind+1,struct.pack('>ii',1,0))
