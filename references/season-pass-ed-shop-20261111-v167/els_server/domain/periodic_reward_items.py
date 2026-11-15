"""Configured outputs of the current pass and admitted ordinary weekly tasks."""
from collections import Counter
import json
from els_server.domain import periodic_activities as rules
from els_server.domain.periodic_item_readers import DATA_SHA
POLICY='current-season-pass-normal-reward-20261109-v1'
PREMIUM_POLICY='current-magmelia-express-premium-20261110-v1'
WEEKLY_POLICY='current-ordinary-weekly-reward-20261109-v1'

def plan(category,claims):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,LOCAL_MAX_STACK
    from els_server.domain.equipment_chip_rules import PASS_CHIP
    config=rules.catalog()['passes'][str(category)]
    rows={(r['1'],r['2']):r for r in config['Reward'].values()}
    chip=chip_reward(category)
    selected=[]
    for pair in claims:
        row=rows.get(tuple(pair))
        if row is None:raise ValueError('Current pass reward identity')
        template=PASS_CHIP if chip and tuple(pair)==(chip['PassType'],chip['Step']) else row['4']
        selected.append((template,row['5']))
    if len(selected)>36:
        # Betty's native claim-all can request 30 normal and 30 premium
        # steps together. Combine identical outputs within the grant bound.
        quantities=Counter()
        for template,quantity in selected:
            quantities[template]+=quantity
        selected=[(template,min(LOCAL_MAX_STACK,quantity-offset))
                  for template,quantity in quantities.items()
                  for offset in range(0,quantity,LOCAL_MAX_STACK)]
    return [dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)
            for t,n in selected]

def chip_reward(category):
    config=rules.catalog()['passes'][str(category)]
    return config.get('RewardChipOption',{}).get('1')

def weekly_plan(qid):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,LOCAL_MAX_STACK
    if not rules.ordinary_weekly(qid):raise ValueError('Ordinary weekly reward source')
    result=[]
    for row in rules.definition(qid)['Reward']['m_vecItem'].values():
        template=row['m_iItemID'];left=row['m_iQuantity']
        if row['m_iPeriod']or row['m_sSocketOption']:raise ValueError('Ordinary weekly fixed reward shape')
        while left:
            n=min(left,LOCAL_MAX_STACK);left-=n
            result.append(dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=n))
    return result

def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    policy=identity.get('policy')
    if policy not in(POLICY,PREMIUM_POLICY,WEEKLY_POLICY):return False
    if source.kind!='ordinary'or identity.get('owner')!=source.owner or identity.get('readers_sha256')!=DATA_SHA:
        raise ValueError('Periodic exact reward source')
    if policy in (POLICY,PREMIUM_POLICY):
        if identity.get('season')!=12 or str(identity.get('category')) not in rules.catalog()['passes']:
            raise ValueError('Pass exact reward source')
        if (policy==PREMIUM_POLICY)!=any(track==2 for track,_ in identity['claims']):
            raise ValueError('Pass reward source track')
        expected=plan(identity['category'],identity['claims'])
    else:expected=weekly_plan(identity['quest'])
    source.validate_plan(expected)
    if template not in {p['template']for p in expected}:raise ValueError('Periodic output outside exact reward plan')
    return True
