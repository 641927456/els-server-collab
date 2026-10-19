"""Pinned repair dependencies and default-instance equipment discounts.

Owned title repair effects use the independently pinned native effect table.
Explicitly timed inventory passes are supported; dual forms remain pending.
"""
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA,DATA_DIR
from els_server.domain.character_stats import f32


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(DATA_DIR/'repair.json').read_bytes()
    m=json.loads((DATA_DIR/'repair.manifest.json').read_text())
    d=json.loads(raw)
    if (m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or m['sha256']!=hashlib.sha256(raw).hexdigest()
        or m['source_catalog_sha256']!=client_data().manifest['catalog_sha256']
        or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=m['source_catalog_sha256']
        or d['effect_count']!=70522 or d['item_count']!=181836 or d['set_count']!=11422
        or d['all_set_repair_effects_zero'] is not True):raise ValueError('Repair catalog identity')
    return d


def multiplier(character,items):
    d=catalog()
    if character['unit_type']==10:raise ValueError('Dual-form repair pricing pending')
    if character.get('repair_buffs'):raise ValueError('Buff repair pricing pending')
    total=0.;sources=[];passes=[]
    if character.get('title',0):
        from els_server.domain.titles import eligible
        if not eligible(character,character['title']):raise ValueError('Ineligible repair title')
        for effect in d['title_effects'].get(str(character['title']),[]):
            value=d['effects'][str(effect)];total=f32(total+value)
            sources.append(dict(title=character['title'],effect=effect,value=value))
    for item in sorted(items,key=lambda i:i.get('slot',0)):
        from els_server.domain.item_expiration import expired
        if expired(item):continue
        client_data().item(item['template'])
        if item['template'] in d['free_repair_templates']:
            from els_server.domain.repair_pass import TEMPLATE
            if item['template']!=TEMPLATE or 'expires_at' not in item:raise ValueError('Unsupported repair pass instance')
            # Current registered pass is valid only in its owned bag group 4.
            # Native 865910 excludes warehouse/pet groups 8,13,14,16.
            if item['group']==4 and item.get('count',0)>0:passes.append(item['uid'])
        if item['group']==9:
            for effect in d['template_effects'].get(str(item['template']),[]):
                value=d['effects'][str(effect)];total=f32(total+value)
                sources.append(dict(uid=item.get('uid'),template=item['template'],effect=effect,value=value))
    # 865910 adds template effects even when the instance is broken. Set effects
    # in this build all have zero repair discounts. Title discounts were added
    # separately above; persistent buffs remain unsupported.
    capped=min(total,f32(.7))
    if passes:return dict(multiplier=0.,uncapped_discount=total,discount=1.,sources=sources,free_pass_uids=passes)
    return dict(multiplier=f32(1.-capped),uncapped_discount=total,discount=capped,sources=sources)


def require_baseline(character,items):
    value=multiplier(character,items)['multiplier']
    if value!=1.:raise ValueError('Repair context is not baseline')
    return value


def character_quote(selected,character,inventory):
    from els_server.domain.equipment_repair import normal_quote
    import math
    q=normal_quote(selected);context=multiplier(character,inventory)
    cost=math.trunc(f32(f32(q['subtotal_ed'])*context['multiplier']))
    if not 0<=cost<2**31:raise ValueError('Repair cost bound')
    return dict(q,pricing_context=context,total_ed=cost,pending=[])
