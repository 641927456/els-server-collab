"""Original costume-color recipes on Ariel's existing manufacture transaction."""
from copy import deepcopy
from functools import lru_cache

from els_server.game_data import CLIENT_SHA, client_data
from els_server.manufacture_data import manufacture_data

TICKET = 225200
ARIEL = 40017


def rule(recipe):
    definition=recipe['definition']
    materials=definition['m_MaterialTable'].values()
    if not any(row['m_MaterialID']==TICKET for row in materials):return None
    amounts={row['m_MaterialID']:row['m_MaterialCount'] for row in materials}
    clothing=[t for t in amounts if t!=TICKET]
    if len(amounts)!=2 or len(clothing)!=1 or amounts[clothing[0]]!=1:
        raise ValueError('Costume color recipe material identity')
    targets=recipe['result_registrations']
    if len(targets)!=1 or definition.get('m_bUpgrade'):
        raise ValueError('Costume color recipe output identity')
    source,target=(client_data().item(t) for t in (clothing[0],targets[0]))
    if (source['item_type'] not in (1,2,3) or source['item_type']!=target['item_type']
        or not source['flags4']&1 or not target['flags4']&1
        or source['equip_position']!=target['equip_position']
        or source['record'][210:212]!=target['record'][210:212]):
        raise ValueError('Costume color recipe role/part identity')
    return dict(recipe=definition['m_ManufactureID'],source=clothing[0],target=targets[0],
                tickets=amounts[TICKET],ed=definition['m_Cost'])


@lru_cache(maxsize=1)
def catalog():
    data=manufacture_data()
    return {r['recipe']:r for identity in data.ids() if (r:=rule(data.recipe(identity))) is not None}


@lru_cache(maxsize=1)
def offers():
    # Old recipes repeat an already registered direction. Prefer the native
    # target-ID recipe; preserve every original recipe and its stated price.
    selected={}
    for row in sorted(catalog().values(), key=lambda r:(r['recipe']!=r['target'],r['recipe'])):
        selected.setdefault((row['source'],row['target']),row['recipe'])
    return tuple(sorted(selected.values()))


def require_town(town):
    from els_server.domain.npc_exchange_rules import catalog as npc_catalog
    if town not in npc_catalog()['house_towns'][str(ARIEL)]:
        raise ValueError('Costume color manufacture requires an Ariel town')


def usable(items,recipe,*,now):
    from els_server.domain.item_expiration import expired
    return [i for i in items if i['template']!=recipe['source'] or
            not (i.get('wardrobe_hanger',False) or i.get('expires_at',0)
                 or i.get('activation_seconds',0) or expired(i,now=now))]


def sources(request,recipe,items,allocation):
    by_uid={i['uid']:i for i in items}
    if request.selected_uid!=-1 and by_uid[request.selected_uid]['template']!=recipe['source']:
        raise ValueError('Selected costume color source is not the requested costume')
    selected=[by_uid[a['uid']] for a in allocation if by_uid[a['uid']]['template']==recipe['source']]
    if len(selected)!=request.quantity or any(i['count']!=1 for i in selected):
        raise ValueError('Costume color source count')
    return iter(selected)


def convert(source,template):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item
    out=deepcopy(source)
    out.update(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template])
    if out['group']!=source['group']:
        raise ValueError('Costume color conversion changed inventory container')
    return validate_item(out)
