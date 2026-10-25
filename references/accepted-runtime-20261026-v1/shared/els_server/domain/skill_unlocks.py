"""Native seal groups; ownership never follows level or career automatically."""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

@functools.lru_cache(maxsize=1)
def catalog():
    row=json.loads((PROJECT_ROOT/'els_server/data/skill_unlocks.json').read_text(encoding='utf8'))
    data=client_data();proof=(PROJECT_ROOT/row['proof']).read_bytes()
    if row['client_sha256']!=CLIENT_SHA or row['catalog_sha256']!=data.manifest['catalog_sha256'] or hashlib.sha256(proof).hexdigest()!=row['proof_sha256']:raise ValueError('Seal evidence identity')
    witnesses={r['template']:r for r in json.loads(proof)['rows']}
    for r in row['books'].values():
        p=witnesses[r['template']]
        if hashlib.sha256(data.item(r['template'])['record']).hexdigest()!=r['record_sha256'] or p['ok']!=1 or p['consumed']!=304 or p['group']!=4 or not p['fields_match']:raise ValueError('Seal book evidence')
    return row

def groups(character):
    value=(character or {}).get('skill_seal_groups',())
    if not isinstance(value,(tuple,list)) or len(set(value))!=len(value) or any(type(g) is not int or str(g) not in catalog()['groups'] for g in value):raise ValueError('Invalid skill seal ownership')
    return tuple(value)

def skill_group(skill):
    return next((int(g) for g,r in catalog()['groups'].items() if skill in r['skills']),None)

def eligible_skills(character,group):
    from els_server.domain.character_rules import CLASSES
    from els_server.domain.role_progression import master_skills
    cls=character['unit_class'];stage=CLASSES[cls]['stage'];data=client_data()
    rule=catalog()['groups'][str(group)]
    if stage<rule['stage']:return ()
    if group>=9 and not character.get('master'):return ()
    if group in (6,7) and not character.get('transcendence'):return ()
    native_stage=4 if stage==3 else 3 if stage==2 and character.get('transcendence') else stage
    tree={s for s,_ in data.skill_tree(cls)}|set(master_skills(cls))
    return tuple(s for s in rule['skills'] if s in tree and data.skill(s)['m_RequireCharacterLevel']['1']<=character['level'] and data.skill(s)['m_RequireUnitClassType']['1']<=native_stage)

def unsealed_skills(character):
    return tuple(sorted({s for g in groups(character) for s in eligible_skills(character,g)}))

def validate_unlock(character,group):
    owned=groups(character)
    if group in owned:raise ValueError('Skill seal already unlocked')
    if group>=10 and group-1 not in owned:raise ValueError('Previous Master skill grade is sealed')
    if not eligible_skills(character,group):raise ValueError('Skill seal level or career requirement')

def ids_wire(character):
    ids=unsealed_skills(character)
    return struct.pack('>I',len(ids))+b''.join(struct.pack('>i',s) for s in ids)

def unlock_notice(character,previous=()):
    from els_server.domain.skill_rules import learned_skills
    from els_server.domain.skill_state import record
    from els_server.protocol.protocol_codec import Event
    learned=learned_skills(character);ids=tuple(s for s in unsealed_skills(character) if s not in previous)
    ranks={s:learned[s] for s in ids if s in learned}
    wire=struct.pack('>iI',0,len(ranks))+b''.join(record(s,r) for s,r in ranks.items())
    wire+=struct.pack('>I',len(ids))+b''.join(struct.pack('>i',s) for s in ids)
    return Event(0x201,kind=0x131,payload=wire)
