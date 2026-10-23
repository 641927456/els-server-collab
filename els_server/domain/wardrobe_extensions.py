"""Source-bound wardrobe services; native client renders and applies effects."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/wardrobe_extensions.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='e742119abad57b251bff692f7905db526247f8ae543d91ba24185d1fe071945e':raise ValueError('Wardrobe extension catalog checksum')
    data=json.loads(raw)
    if data['client_sha256']!=CLIENT_SHA:raise ValueError('Wardrobe extension version')
    return data

def color_state(item):
    data=catalog()
    for key,template in (('dye_colors',item['template']),('appearance_colors',item.get('appearance_template',0))):
        colors=item.get(key,[0,0,0])
        if not isinstance(colors,(list,tuple))or len(colors)!=3 or any(type(c)is not int or c<0 or c and c not in data['colors']for c in colors):raise ValueError('Invalid native dye colors')
        if any(colors):
            parts=data['dye_parts'].get(str(template),0)
            if not parts or any(colors[parts:])or item['count']!=1:raise ValueError('Dye part mismatch')
    return item

def ticket_selection(ticket,template,character):
    from els_server.domain.wardrobe import definition,require_owner
    data=catalog();key=str(ticket);row=data['tickets'].get(key)
    if row is None or template not in data['ticket_allowed'][key]:raise ValueError('Appearance outside verified ticket range')
    if definition(template)['equip_position']!=row['part']:raise ValueError('Ticket equipment position')
    require_owner(template,character)
    return row

def unregister_group(template):
    from els_server.domain.wardrobe import definition
    pos=definition(template)['equip_position']
    if pos==2 or 48<=pos<=59:return 1
    if pos in (6,8,9):return 2
    if pos in (10,11):return 3
    if pos==38:return 4
    raise ValueError('Unsupported hanger removal equipment group')
