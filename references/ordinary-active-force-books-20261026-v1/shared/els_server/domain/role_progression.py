"""Pinned loadouts and separate Master skill definitions for all native roles."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA


@functools.lru_cache(maxsize=1)
def catalog():
    row=json.loads((PROJECT_ROOT/'els_server/data/role_progression.json').read_text(encoding='utf8'))
    data=client_data();proof=(PROJECT_ROOT/row['proof']).read_bytes()
    if (row['schema_version']!=1 or row['client_sha256']!=CLIENT_SHA
        or row['source_catalog_sha256']!=data.manifest['catalog_sha256']
        or hashlib.sha256(proof).hexdigest()!=row['proof_sha256']
        or hashlib.sha256((PROJECT_ROOT/row['master_source']).read_bytes()).hexdigest()!=row['master_source_sha256']):
        raise ValueError('Role progression evidence identity')
    native=json.loads(proof);witnesses={r['template']:r for r in native['rows']}
    if native['live_process_access'] is not False or native['master_slot']!=21:raise ValueError('Role native evidence scope')
    for key,r in row['costumes'].items():
        template=int(key);item=data.item(template);p=witnesses.get(template,{})
        if (hashlib.sha256(item['record']).hexdigest()!=r['record_sha256'] or p.get('record_sha256')!=r['record_sha256']
            or p.get('ok')!=1 or p.get('consumed')!=304 or p.get('group')!=7 or p.get('fields_match') is not True):
            raise ValueError('Role costume evidence mismatch')
    if set(row['roles'])!={str(n) for n in range(1,16)} or len(row['master_skills'])!=60:raise ValueError('Role progression coverage')
    return row


def master_skills(unit_class):
    return tuple(catalog()['master_skills'].get(str(unit_class),{}).values())


def first_master_skill(character):
    rows=catalog()['master_skills'].get(str(character['unit_class']))
    return rows['0'] if character.get('master') and rows else 0


def known_skills(unit_class):
    from els_server.domain.character_rules import CLASSES
    data=client_data()
    return ({s for s,_ in data.skill_tree(unit_class)}
            |{s for s,_ in data.skill_tree(CLASSES[unit_class]['base_class'])}
            |set(master_skills(unit_class))|{900214,900234,900244})


def slot_accepts(index,skill):
    if not skill:return True
    kind=client_data().skill(skill)['m_eType']
    if kind in (22,23,24,25):return index==21
    if kind==13:return index==20
    return index not in (20,21)
