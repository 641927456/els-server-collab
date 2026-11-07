"""CN July 2026 campaign580, with the human-authorized permanent calendar."""
import functools, hashlib, json
from pathlib import Path

CODE=580
BOX=721729
POINT_ITEM=721728
DEFINITION_SHA='fa2810e382521917e13750c5b41e8a9fc32f36da02de0f86969ffb7d93b1df17'

@functools.lru_cache(maxsize=1)
def definition():
    raw=(Path(__file__).resolve().parents[1]/'data/abyss_weapon_2026.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA:raise ValueError('Abyss summer definition changed')
    data=json.loads(raw)
    from els_server.game_data import client_data
    for row in data['templates']:
        actual=client_data().item(row['template'])
        if actual['name']!=row['name'] or hashlib.sha256(actual['record']).hexdigest()!=row['record_sha256']:
            raise ValueError('Abyss campaign item identity changed')
    return data

def templates():return {r['template']:r for r in definition()['templates']}
def weapon_templates():return frozenset(r['ItemID']for r in definition()['client_config']['WeaponItemID'].values())
def quests():return {r['definition']['m_iID']:r for r in definition()['quests']}
def points():
    c=definition()['client_config']
    return {r['QuestID']:r['Point']for key in ('SpecialQuestIDList','WeeklyQuestIDList')for r in c[key].values()}
def limit(quest):
    row=quests()[quest]['objective'];condition=row['m_ClearCondition']
    return condition.get('m_iDungeonClearCount',1)
def rewards():return {int(k):v for k,v in definition()['reward_items'].items()}
def reward_plan(reward):return plan(rewards()[reward],1)
def plan(template,quantity):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    return [dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)]
def output_for(unit_class):
    from els_server.domain.equipment_requirements import catalog
    family=catalog()[0][unit_class]['family']
    from els_server.game_data import client_data
    return next(t for t in weapon_templates()if client_data().item(t)['record'][0xd2]==family)
def register():
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    from els_server.domain.activity_2026_stack_policy import effective_stack
    for t,row in templates().items():
        if t in VERIFIED_TEMPLATES:
            if (VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t])!=(row['metadata'],row['group']):raise ValueError('Abyss inventory type conflict')
        else:
            VERIFIED_TEMPLATES[t]=row['metadata'];TEMPLATE_BAG_GROUPS[t]=row['group'];TEMPLATE_MAX_STACKS[t]=effective_stack(row['max_stack'])
    from els_server.domain.cubes import catalog
    catalog.cache_clear()
def boxes():return {BOX,*map(int,definition()['bundles'])}
def entries():
    return tuple(dict(template=t,selection_count=0,entries=(),abyss_campaign_box=True)for t in sorted(boxes()))
def preview(template,unit_class):
    return (dict(template=output_for(unit_class),quantity=1),)if template==BOX else tuple(definition()['bundles'][str(template)])

