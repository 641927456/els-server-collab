"""Ordinary owned-item wear checks. Dynamic/privileged contexts stay unavailable."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA
from els_server.domain.normal_equipment import definitions
from els_server.domain.equipment_eligibility import inspect_eligibility
from els_server.domain.equipment_durability import validate


@functools.lru_cache(maxsize=1)
def restricted_templates():
    m=json.loads((PROJECT_ROOT/'els_server/data/equipment_instance.manifest.json').read_text());raw=(PROJECT_ROOT/m['proof']).read_bytes();p=json.loads(raw)
    from els_server.domain.early_weapon_equipment import definitions as appendix
    extra=set(appendix())
    if (hashlib.sha256(raw).hexdigest()!=m['proof_sha256'] or m['client_sha256']!=CLIENT_SHA or p['client_sha256']!=CLIENT_SHA
        or m['default_instance_only'] is not True or m['account_state_semantics_verified'] is not False
        or p['count']!=len(definitions())-len(extra) or len(p['rows'])!=p['count'] or p['cases']!=6*p['count']):raise ValueError('Instance evidence scope')
    seen=set();dynamic=set();special=set()
    for r in p['rows']:
        t=r['template']
        if t in seen or t not in definitions() or r['category77'] not in (0,1) or r['accountState']!=0 or type(r['special']) is not bool:raise ValueError('Instance evidence identity')
        seen.add(t)
        if r['category77']:dynamic.add(t)
        if r['special']:special.add(t)
        expected=[[owner,dur,int(dur>0 and (not r['category77'] or owner!=0) and not r['special'])] for owner in (-1,0,1) for dur in (0,10000)]
        if r['cases']!=expected:raise ValueError('Instance native cases')
    if seen&extra or seen|extra!=set(definitions()):raise ValueError('Instance appendix coverage')
    if dynamic!=set(m['dynamic_templates']) or special!=set(m['privileged_templates']) or special!={28005,28006}:raise ValueError('Instance restriction coverage')
    return frozenset(dynamic|special)


def require_wearable(item,character):
    from els_server.domain.item_expiration import require_current
    require_current(item)
    from els_server.domain.boosting_gear_identification import require_complete
    require_complete(item)
    if item.get('enhancement',0)<0:raise ValueError('Broken equipment requires restoration')
    if item['template'] in restricted_templates():raise ValueError('Unimplemented dynamic equipment permission')
    if validate(item['template'],item.get('durability',0))<=0:raise ValueError('Equipment durability exhausted or missing')
    if not inspect_eligibility(item['template'],character['unit_class'],character['level'])['template_requirements_met']:raise ValueError('Equipment template requirements not met')
    from els_server.domain.tenebros_rules import require_identified
    require_identified(item)


def contributes_attributes(item,character):
    """8A20E0's worn-item filter, for verified default normal instances only.

    A route change retains the item but excludes it from the contribution
    vector. This is distinct from permission to wear a new item: 8A20E0 does
    not recheck the level/model prerequisites used by the right-click path.
    Dynamic account/event items are deliberately outside the supported scope.
    """
    from els_server.game_data import client_data
    from els_server.domain.equipment_requirements import class_matches
    from els_server.domain.item_expiration import expired
    if item['template'] not in definitions():raise ValueError('Outside normal equipment effect scope')
    return (not expired(item) and item.get('enhancement',0)>=0 and item['group']==9 and item['template'] not in restricted_templates()
            and validate(item['template'],item.get('durability',0))>0
            and class_matches(character['unit_class'],client_data().item(item['template'])['record'][0xd3]))
