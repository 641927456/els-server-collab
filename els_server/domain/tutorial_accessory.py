"""Three exact original starter accessories and their main/minor applications."""
import functools,hashlib
from els_server.game_data import client_data

TEMPLATE=92110
TEMPLATES=frozenset((92110,92111,92112))
RECORDS={
 92110:('b7289025b7117826403420f5c020cd3076c9082981c6a5c7bad6674214b4306c',20,14,29,(0.,0.,0.,0.,0.,2.,0.)),
 92111:('a95a2f72642a42fbef323b3b0358660d2b65a69346ecb7b951125fce02f10038',22,16,31,(0.,2.,0.,0.,0.,0.,0.)),
 92112:('5b3137e276c91a9e6dca68a23385126549339dcf24f2e9c6d8e9ace48345e63b',23,17,32,(100.,0.,0.,0.,0.,0.,0.)),
}
RECORD_SHA256=RECORDS[TEMPLATE][0]
SLOT_STYLE={slot:side for record in RECORDS.values() for side,slot in enumerate(record[2:4])}
APPLICATION_VERIFIED=True  # Finite default records; full combat is a separate gate.

@functools.lru_cache(maxsize=3)
def definition(template=TEMPLATE):
    if template not in TEMPLATES:raise ValueError('Outside verified accessory scope')
    pin,position,main,minor,stats=RECORDS[template]
    source=client_data().item(template);raw=source['record']
    if (hashlib.sha256(raw).hexdigest()!=pin or source['item_type']!=3 or source['metadata']!=0
        or source['equip_position']!=position or source['stats']!=stats or any(source['stat_bonus'])
        or raw[0xd1:0xd4]!=bytes(3) or int.from_bytes(raw[0x34:0x38],'little')!=0):
        raise ValueError('Tutorial accessory source identity')
    return dict(template=template,metadata=0,group=2,max_stack=1,record_sha256=pin,slots=(main,minor),native=[dict(count=1,ok=1,consumed=304)])

def accepts_equipped(item):
    if item.get('template') not in TEMPLATES:return False
    rule=definition(item['template'])
    return (APPLICATION_VERIFIED and item['metadata']==0 and item['count']==1
            and item['group']==9 and item['slot'] in rule['slots'])

def effective_style(character):
    from els_server.protocol.luciel_messages import preference,active_preference
    if 'luciel_style' not in character or 'luciel_active_unit' not in character:
        raise ValueError('Missing authoritative LuCiel state')
    value=preference(character)
    return active_preference(character) if value==2 else value

def require_wearable(item,character,*,style=None):
    if not APPLICATION_VERIFIED or not accepts_equipped(item):raise ValueError('Accessory equipped position')
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    require_current(item);require_unlocked(item)
    family=client_data().unit(character['unit_class'])['unitType']
    if family!=character['unit_type'] or type(character['level']) is not int or not 1<=character['level']<=99:
        raise ValueError('Accessory owner identity')
    main,minor=definition(item['template'])['slots']
    if family==10:effective_style(character)
    elif item['slot']!=main:raise ValueError('Minor accessory belongs to LuCiel')
    if set(item)-{'uid','template','metadata','count','group','slot','expires_at','lock_until'}:
        raise ValueError('Nondefault tutorial accessory instance')

def contributes(item,character):
    from els_server.domain.item_expiration import expired
    if expired(item) or not accepts_equipped(item):return False
    family=client_data().unit(character['unit_class'])['unitType']
    if family!=character['unit_type']:raise ValueError('Accessory contribution family')
    main,minor=definition(item['template'])['slots']
    if family!=10:return item['slot']==main
    selected=effective_style(character)
    # Native897440/861F10 use both sides for HP; attack/defense select one.
    return item['template']==92112 or SLOT_STYLE[item['slot']]==selected

def wear_context(s):
    if (not s.item_test or s.client_build!='dx11_260923' or s.role!='game' or s.phase!='town_ready'
        or s.account.store is None or s.account.characters is None or 0x227 not in s.completed
        or s.account.get_location()['map']!=s.active_map):raise ValueError('Accessory town actor not ready')
    app=getattr(s,'application',None);room=None;entry=None
    if app is not None:
        if (s.released or app.playing.get(s.identity['id']) is not s or s.identity['id']!=s.account.account_id
            or s.social_overflow or s.coop_error):raise ValueError('Accessory current lease')
        world=app.world;room=world.room(s);entry=room.get(s)
        if world.members.get(s)!=(1,s.active_map) or entry is None or entry[0]['uid']!=s.account.uid:raise ValueError('Accessory town membership')
    return (s.account,s.account.store,s.account.characters,app,room,entry,
            s.account.uid,s.account.account_id,s.shop_session_id,s.active_map,repr(s.account.get_location()))

def validate_wear_context(s,captured):
    now=wear_context(s)
    if any(a is not b for a,b in zip(now[:6],captured[:6])) or now[6:]!=captured[6:]:raise ValueError('Accessory actor changed before commit')
