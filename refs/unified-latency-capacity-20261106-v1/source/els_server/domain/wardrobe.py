"""Current native wardrobe membership; appearance never replaces item stats.

CN guide: /game/000-1635-00303-837181.shtml?ms=771, checked2026-10-20.
CoordiItem.lua/CoordiItem2.lua supply membership, not acquisition permission.
Tickets, unregistration and dyeing need their own source/transaction review.
"""
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA
from els_server.paths import PROJECT_ROOT


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/wardrobe_catalog.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='23249ca0c7bb1a5111bd2104c5cfc6c9df0bf8213af20431454752342e660586':
        raise ValueError('Wardrobe catalog checksum')
    data=json.loads(raw)
    if data['client_sha256']!=CLIENT_SHA or len(data['templates'])!=72885:
        raise ValueError('Wardrobe catalog identity')
    return frozenset(data['templates'])


def definition(template):
    from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
    from els_server.domain.normal_equipment import definitions as normal
    from els_server.domain.ordinary_accessories import definitions as accessories
    from els_server.domain.acquisition_policy import require_acquirable
    if type(template) is not int or template not in catalog():raise ValueError('Outside current wardrobe catalog')
    require_acquirable(template)
    item=client_data().item(template)
    if item['metadata']not in (0,1) or item['item_type'] not in (1,2,3):raise ValueError('Unsupported wardrobe instance type')
    if template not in FASHION_EQUIP_SLOTS and template not in normal() and template not in accessories():
        raise ValueError('Unqualified wardrobe instance')
    from els_server.domain.equipment_instance import restricted_templates
    if template in normal() and template in restricted_templates():raise ValueError('Unsupported normal equipment permission')
    if template in accessories() and accessories()[template]['restricted']:
        raise ValueError('Unsupported special accessory permission')
    return item


def validate_state(item):
    appearance=item.get('appearance_template',0);hanger=item.get('wardrobe_hanger',False)
    if type(appearance) is not int or not 0<=appearance<2**31 or type(hanger) is not bool:
        raise ValueError('Wardrobe instance fields')
    if not appearance and not hanger:return
    original=definition(item['template'])
    if item['count']!=1 or item.get('sealed',False) or 'expires_at' in item:
        raise ValueError('Wardrobe requires permanent unsealed equipment')
    from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
    from els_server.domain.ordinary_accessories import definitions as accessories
    binding=item['template'] in FASHION_EQUIP_SLOTS or item['template'] in accessories()
    if hanger and not binding:raise ValueError('Normal equipment has no hanger binding')
    if appearance:
        chosen=definition(appearance)
        # Native22E2180 allows the paired normal/fashion accessory positions31 apart.
        a,b=original['equip_position'],chosen['equip_position']
        if a!=b and not (17<=min(a,b)<=28 and abs(a-b)==31):raise ValueError('Wardrobe appearance position mismatch')
        if binding and not hanger:raise ValueError('Register hanger before applying appearance')


def require_owner(template,character):
    from els_server.domain.equipment_requirements import class_matches
    raw=definition(template)['record']
    if raw[0xd2] and raw[0xd2]!=character['unit_type'] or not class_matches(character['unit_class'],raw[0xd3]):
        raise ValueError('Wardrobe character requirement')
    if raw[8]&4 and character['unit_type']!=10:raise ValueError('Companion wardrobe requirement')
