"""Original Camilla sparring equipment and ranked accessory AP stock."""
from dataclasses import dataclass
from functools import lru_cache
import json
import struct

from els_server.domain.camilla_force import CAMILLA_NPC, CAMILLA_TOWNS

POLICY = 'native-camilla-ap-shop-v1'
CAMILLA_HOUSE = 40016
ACCESSORY_RANK_BY_AP = {7700:2,6500:9}


@dataclass(frozen=True)
class Offer:
    ed: int
    ap: int
    rank: int
    unit: int


@lru_cache(maxsize=1)
def catalog():
    from els_server.domain.npc_trade import stock
    from els_server.domain.pvp_specialization import catalog as specialization
    from els_server.game_data import client_data

    native = client_data()
    equipment = specialization()['targets']
    templates = set().union(*(stock().get((town,CAMILLA_NPC),()) for town in CAMILLA_TOWNS))
    offers = {}
    for template in templates:
        item = native.item(template)
        raw = item['record']
        ed,ap = struct.unpack_from('<ii',raw,0x1c)
        rank,unit = raw[0xd0],raw[0xd2]
        sparring = equipment.get(str(template))
        if sparring is not None:
            if not ed or ap != {1:200,2:50}[sparring['item_type']] or rank or unit!=sparring['unit_type']:
                raise ValueError('Camilla native sparring price or eligibility')
        elif not (item['item_type']==3 and ed==100000 and ap in ACCESSORY_RANK_BY_AP
                  and rank==ACCESSORY_RANK_BY_AP[ap] and raw[0xd5] in (17,20,21,27)):
            continue
        if raw[0xe1] or not 1<=unit<=15:
            raise ValueError('Camilla native role or alternate rank')
        offers[template] = Offer(ed,ap,rank,unit)
    return offers


def authorize_output(template,source):
    if getattr(source,'kind',None)!='npc_trade' or template not in catalog():
        return False
    from els_server.domain.raid_reward_items import validate_source
    from els_server.domain.npc_trade import stock

    source = validate_source(source)
    data = json.loads(source._source)
    if source.kind!='npc_trade' or data.get('policy')!=POLICY:
        return False
    town = data.get('town')
    if (data.get('owner')!=source.owner or data.get('operation')!=source.operation
            or data.get('merchant')!=CAMILLA_NPC or town not in CAMILLA_TOWNS
            or template not in stock().get((town,CAMILLA_NPC),())):
        raise ValueError('Camilla AP item requires its original shop')
    source.validate_template(template)
    return True
