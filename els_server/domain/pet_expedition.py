"""Current expedition formula/eligibility and explicitly approved box pools."""
import copy
import functools
import hashlib
import json
from els_server.paths import PROJECT_ROOT

# The transactional lifecycle is in storage.pet_expedition.
WRITER_ENABLED = True
TABLE_SHA256 = 'f41cd61ed98c9ea8a3fb1c7ba2518330a5b4f126484de745604e1aa0ff451a1f'
RAW_SHA256 = 'f7304bfb85e362033059e18fc1f1c09750f9f6cc4cd47b83d8c9e24f2cc5e54d'
IMAGE_SHA256 = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'


@functools.lru_cache(maxsize=1)
def _catalog():
    root=PROJECT_ROOT/'analysis/pet-support-20261015'
    raw=(root/'LifeContentData.lua.tables.json').read_bytes()
    from els_server.game_data import CLIENT_SHA
    if hashlib.sha256(raw).hexdigest()!=TABLE_SHA256 or CLIENT_SHA!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709':
        raise ValueError('Current LifeContentData identity')
    # Raw18466B source + resource-proof are frozen external lineage evidence;
    # the runtime already carries this exact parsed table, not that audit file.
    data=json.loads(raw);groups={}
    for call in data['__symbolic_calls__']:
        name=call['function'].split('.')[-1]
        groups.setdefault(name,[]).append(call['arguments'][1:])
    regions={r[0]['m_iRegionId']:r[0] for r in groups['AddExpeditionRegion']}
    missions={r[0]['m_iMissionId']:r[0] for r in groups['AddExpeditionMission']}
    risks={r[0]['m_iRiskFactorId']:r[0] for r in groups['AddExpeditionRiskFactor']}
    if (len(regions)!=9 or len(missions)!=36 or len(risks)!=36
            or set(regions)!=set(range(1,10)) or data['CalculateExpeditionSuccessRate']!={'closure':0}
            or groups['SetUseLifeSpirit']!=[[20]] or groups['SetUseEndurance']!=[[40]]):
        raise ValueError('Finite life-content scope changed')
    for row in missions.values():
        if (row['m_iRegionId'] not in regions or row['m_iRiskFactorId'] not in risks
                or any(type(row[k]) is not int or row[k]<=0 for k in
                    ('m_iConsumedLifeSpirit','m_iConsumedED','m_iExplorationTime','m_iDifficultyPoint'))):
            raise ValueError('Original expedition mission fields')
    return dict(regions=regions,missions=missions,risks=risks,
                fishing_life_cost=20,fishing_condition_cost=40,
                success_formula_closure=0,
                caveat='Reward IDs are candidate identities only; no quantity/weights, start writer or invented life maximum.')


def catalog():
    return copy.deepcopy(_catalog())


def mission(identity):
    if type(identity) is not int or identity not in _catalog()['missions']:
        raise ValueError('Outside exact expedition mission scope')
    return copy.deepcopy(_catalog()['missions'][identity])


def eligible_pet(pet, *, region, active_pet):
    """Original permanent, unsummoned final stage and raw affinity gate."""
    from els_server.domain.pet_progression import template, status, threshold
    if (type(pet) is not dict or pet.get('kind')!='pet' or
            type(pet.get('uid')) is not int or pet['uid']<=0 or
            pet['uid']==active_pet or pet.get('expires_at',0)!=0):
        raise ValueError('Expedition owned permanent unsummoned pet')
    spec=template(pet['unit'])
    if (type(pet.get('step')) is not int or status(pet)!=3 or
            pet['step']!=spec['EVOLUTION_ALL_STEP'] or
            type(pet.get('growth')) is not int or
            not _catalog()['regions'][region]['m_iIntimacyRestriction']<=pet['growth']<=threshold(pet)):
        raise ValueError('Expedition original final-stage affinity')
    allocated=pet.get('personality',{})
    if type(allocated) is not dict:raise ValueError('Expedition original allocated growth map')
    # 2377EA0 sums only raw map keys0..3; unused nutrition is not invested.
    total=0
    for key,value in allocated.items():
        try:index=int(key)
        except(TypeError,ValueError):raise ValueError('Expedition growth key') from None
        if str(index)!=str(key) or type(value) is not int or not 0<=value<=32767:
            raise ValueError('Expedition growth entry')
        if 0<=index<=3:total+=value
    return dict(uid=pet['uid'],allocated=total,attribute=spec['ATTRIBUTE'])


def original_success_rate(*, difficulty, pet_count, allocated, risk_matched, accessory_bonus):
    """Authority equivalent of current closure0, not a UI replacement.

    22B1710→234C230 supplies these five parameters. The original closure
    multiplies invested points by1.2/0.8, subtracts and divides difficulty,
    adds the accessory rate, clamps0..1 or0..2, floors3 decimals, and returns
    string.format('%.2f'). No independent local success probability exists.
    """
    import math, struct
    if (type(difficulty) is not int or difficulty<=0 or type(pet_count) is not int or
            not 1<=pet_count<=3 or type(allocated) is not int or not 0<=allocated<=393204 or
            type(risk_matched) is not bool or type(accessory_bonus) not in (int,float) or
            not math.isfinite(accessory_bonus)):
        raise ValueError('Original expedition formula input')
    # Native wrapper promotes an original float bonus to double for Lua.
    bonus=struct.unpack('<f',struct.pack('<f',accessory_bonus))[0]
    value=((allocated*(1.2 if risk_matched else 0.8)-difficulty)/difficulty)+bonus
    value=max(0.0,min(1.0 if pet_count==1 else 2.0,value))
    # 234C230 tail7D4090 parses the formatted string and narrows to float.
    return struct.unpack('<f',struct.pack('<f',float(format(math.floor(value*1000)/1000,'.2f'))))[0]


def native_display_percent(rate):
    # 22B1ECC mulss100.0f/addss0.5f/cvttss2si; do not reuse a double product.
    import math, struct
    def f32(v):return struct.unpack('<f',struct.pack('<f',v))[0]
    if type(rate) is not float or not math.isfinite(rate)or not 0<=rate<=2:
        raise ValueError('Native expedition float rate')
    return int(f32(f32(f32(rate)*100.0)+0.5))


def source_terms(mission_id, pets, *, active_pet=0):
    """Deterministic current mission/pet facts; no draws or economic writes."""
    row=mission(mission_id);region=row['m_iRegionId'];pets=tuple(pets)
    if not 1<=len(pets)<=3:raise ValueError('Original selected pet count')
    facts=[eligible_pet(p,region=region,active_pet=active_pet)for p in pets]
    if len({f['uid']for f in facts})!=len(facts):raise ValueError('Repeated expedition pet')
    risk=_catalog()['risks'][row['m_iRiskFactorId']]['m_iPetAttribute']
    from els_server.domain.pet_accessory_rules import effects
    # Current full socket definitions name these three original rates.
    ordered_effects=[effects({slot:entry})for p in pets
        for slot,entry in sorted(p.get('equipment',{}).items(),key=lambda pair:int(pair[0]))]
    import struct
    def sum32(field):
        value=0.0
        for e in ordered_effects:
            rate=struct.unpack('<f',struct.pack('<f',e.get(field,0)))[0]
            value=struct.unpack('<f',struct.pack('<f',value+rate))[0]
        return value
    rate=original_success_rate(difficulty=row['m_iDifficultyPoint'],pet_count=len(pets),
        allocated=sum(f['allocated']for f in facts),risk_matched=any(f['attribute']==risk for f in facts),
        accessory_bonus=sum32('m_fExpeditionAdditionalSuccessRate'))
    return dict(mission=row,pet_facts=facts,success_rate=rate,native_display_percent=native_display_percent(rate),
        original_ed=row['m_iConsumedED'],original_life=row['m_iConsumedLifeSpirit'],
        original_minutes=row['m_iExplorationTime'],
        ed_reduce_rate=sum32('m_fExpeditionEDReduceRate'),
        time_reduce_rate=sum32('m_fExpeditionTimeReduceRate'),
        writer_enabled=WRITER_ENABLED)


def boxes():
    """User-approved2026-10-31 local pools; never labelled native odds."""
    from els_server.game_data import client_data
    result={}
    for template,weight in ((135984,8000),(135985,5000)):
        entries=[dict(template=t,quantity=1,name=client_data().item(t)['name'],weight=w)
                 for t,w in ((135977,weight),(135974,10000-weight))]
        result[template]=dict(template=template,name=client_data().item(template)['name'],
            group=21,selection_count=0,random=True,pet_expedition=True,entries=entries)
    return result
