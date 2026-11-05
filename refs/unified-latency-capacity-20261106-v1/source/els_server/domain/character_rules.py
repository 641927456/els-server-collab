"""Pinned current-client class identities and level-one skills."""
import json
from pathlib import Path

DATA=json.loads((Path(__file__).parents[1]/'data/characters.json').read_text(encoding='utf8'))
CLASSES={int(k):v for k,v in DATA['classes'].items()}
INITIAL={int(k):tuple(v) for k,v in DATA['initial_skills'].items()}

def initial_skills(character=None):
    cls=1 if character is None else character['unit_class']
    if cls not in CLASSES:raise ValueError('Unknown native class')
    return INITIAL[CLASSES[cls]['base_class']]

def default_slots(character=None):
    from els_server.domain.skill_rules import upgraded_slots
    ids=initial_skills(character)
    slots=list(upgraded_slots(ids+(0,)*(22-len(ids)),character))
    if character:
        from els_server.domain.role_progression import first_master_skill
        slots[21]=first_master_skill(character)
    return tuple(slots)

def transcendental_stage(character):
    return 2 if character.get('master') else 1 if character.get('transcendence') else 0

def artifact_wire(character):
    import struct
    artifact=character.get('artifact')
    if artifact is None:
        if character.get('master'):raise ValueError('Master character is missing its Artifact')
        return bytes(24)
    fields={'template','evolution','level','experience','potentials'}
    if not isinstance(artifact,dict) or set(artifact)!=fields:raise ValueError('Artifact fields')
    if not character.get('master') or type(artifact['template']) is not int or artifact['template']!=character['unit_type']:
        raise ValueError('Artifact does not match master character')
    choices=artifact['potentials']
    if not isinstance(choices,(list,tuple)) or len(choices)!=4 or any(type(v) is not int or not 0<=v<2**31 for v in choices):raise ValueError('Artifact potentials')
    if (any(type(artifact[k]) is not int for k in ('evolution','level','experience'))
        or not 1<=artifact['evolution']<=5 or not 1<=artifact['level']<=99 or not 0<=artifact['experience']<2**63):
        raise ValueError('Artifact progression')
    from els_server.game_data import client_data
    if artifact['level'] not in {r['ARTIFACT_LEVEL'] for r in client_data().artifact_curve(artifact['evolution'])}:
        raise ValueError('Artifact level is absent from client curve')
    return struct.pack('>iiiQI4i',artifact['template'],artifact['evolution'],artifact['level'],artifact['experience'],4,*choices)


def validate_career_state(character):
    from els_server.game_data import client_data
    cls=character['unit_class']
    if type(cls) is not int or cls not in CLASSES:raise ValueError('Unknown native class')
    if type(character['unit_type']) is not int or client_data().unit(cls)['unitType']!=character['unit_type']:raise ValueError('Career role identity')
    if type(character['level']) is not int or not 1<=character['level']<=99:raise ValueError('Career level')
    if any(type(character[k]) is not bool for k in ('transcendence','master')):raise ValueError('Career stage flags')
    stage=CLASSES[cls]['stage']
    if character['transcendence'] and stage<2 or stage==3 and not character['transcendence']:raise ValueError('Invalid transcendence stage')
    if character['master'] and (stage!=3 or not character['transcendence']):raise ValueError('Invalid Master stage')
    artifact_wire(character)
    return character
