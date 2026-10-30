"""Native life-content catalog: expedition, resonance potions, fishing, pet gear.

Decoded from the client's life-content registrations:

  * 9 expedition regions, 36 missions (4 per region), 36 risk factors (12 per pet
    attribute) with their ED / life-spirit / time costs and reward items
  * 52 El-resonance experience potions, 4 life-spirit restore potions
  * 16 fishing premium items and the 19-item pet accessory whitelist
  * the two global action costs the client registers (life spirit 20, endurance 40)

Read-only. Nothing here starts an expedition or consumes a potion; the costs and
rewards are copied exactly as registered so a later integration has no reason to
re-derive them. Two things are deliberately left out of the claim:

  * the two trailing arguments of `AddElResonanceExpPotion` are kept verbatim
    under `extra` because the native call does not name them
  * expedition display textures are dropped — they are render resources, not
    gameplay data
"""
import functools
import hashlib
import json

from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

DATA = PROJECT_ROOT / 'els_server/data/life_content.json'


@functools.lru_cache(maxsize=1)
def _payload():
    data = json.loads(DATA.read_text(encoding='utf8'))
    if data.get('client_sha256') != CLIENT_SHA:
        raise ValueError('Life content client mismatch')
    for source in data.get('sources', []):
        path = PROJECT_ROOT / source['path']
        # The analysis artifacts ship in the runtime asset archive, not in git.
        # Verify them whenever they are present so drift cannot pass silently.
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Life content source changed: %s' % source['path'])
    data['expedition'] = {
        name: {int(k): v for k, v in body.items()}
        for name, body in data['expedition'].items()
    }
    data['resonance_exp_potions'] = {int(k): v for k, v in data['resonance_exp_potions'].items()}
    data['life_spirit_restore_potions'] = {int(k): v for k, v in data['life_spirit_restore_potions'].items()}
    data['fishing_premium_items'] = {int(k): v for k, v in data['fishing_premium_items'].items()}
    return data


def regions():
    """`{region_id: {name_str_id, intimacy_item}}`."""
    return dict(_payload()['expedition']['regions'])


def region(region_id):
    return regions().get(int(region_id))


def risk_factors():
    """`{risk_factor_id: {pet_attribute, name_str_id, description_str_id}}`."""
    return dict(_payload()['expedition']['risk_factors'])


def risk_factor(risk_factor_id):
    return risk_factors().get(int(risk_factor_id))


def missions():
    """`{mission_id: {region_id, risk_factor_id, costs, rewards, ...}}`."""
    return dict(_payload()['expedition']['missions'])


def mission(mission_id):
    return missions().get(int(mission_id))


def missions_for_region(region_id):
    """Sorted `(mission_id, mission)` pairs for one region."""
    wanted = int(region_id)
    return tuple(sorted((mid, body) for mid, body in missions().items()
                        if body['region_id'] == wanted))


def resonance_potion(item_id):
    """`{exp, extra}` for an El-resonance experience potion, or None."""
    return _payload()['resonance_exp_potions'].get(int(item_id))


def restore_potion(item_id):
    """`{minutes}` for a life-spirit restore potion, or None."""
    return _payload()['life_spirit_restore_potions'].get(int(item_id))


def fishing_premium(item_id):
    """`{value}` for a fishing premium item, or None."""
    return _payload()['fishing_premium_items'].get(int(item_id))


def pet_accessories():
    """The native pet accessory whitelist, in registration order."""
    return tuple(_payload()['pet_accessory_items'])


def is_pet_accessory(item_id):
    return int(item_id) in _payload()['pet_accessory_items']


def policy_values():
    """`{life_spirit_per_action, endurance_per_action}`."""
    return dict(_payload()['policy_values'])


def summary():
    return dict(_payload()['summary'])
