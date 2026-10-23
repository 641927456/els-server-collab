"""Grantable native definitions, source-based taxonomy and ranked token search."""
from collections import Counter
import functools
import json
from pathlib import Path
import re
import unicodedata

ASSETS=Path(__file__).parent/'static/icons'
BAGS={1:'装备',2:'饰品',3:'材料',4:'特殊',5:'任务',6:'消耗品',7:'时装',21:'生活道具',27:'时装'}
POSITIONS={2:'武器',6:'发型',7:'脸部',8:'上衣',9:'下衣',10:'手套',11:'鞋子',36:'雷文左臂',37:'副武器',38:'连身装',43:'神器头饰',44:'神器护甲',45:'神器项链',46:'神器戒指',47:'神器第二戒指'}
ACCESSORY_POSITIONS={15:'称号',16:'头部',17:'脸部（上）',18:'脸部（中）',19:'脸部（下）',20:'上身',21:'下身',22:'手臂',23:'戒指',24:'项链',25:'武器饰品',26:'迷你伙伴',27:'耳饰',28:'第二戒指',48:'脸部（上）',49:'脸部（中）',50:'脸部（下）',51:'上身',52:'下身',53:'手臂',54:'戒指',55:'项链',56:'武器饰品',57:'迷你伙伴',58:'耳饰',59:'第二戒指'}


def normalize(text):return unicodedata.normalize('NFKC',str(text)).casefold().strip()


def category(group,kind,position,name):
    if kind==3:
        prefix='fashion-accessory' if group in (7,27) else 'accessory'
        label='时装饰品' if group in (7,27) else '饰品'
        return prefix+'-'+str(position),label+' / '+ACCESSORY_POSITIONS.get(position,'其他部位')
    if group in (1,7,27):
        prefix='fashion' if group in (7,27) else 'equipment'
        label='时装' if prefix=='fashion' else '装备'
        slot=POSITIONS.get(position,'其他')
        return prefix+'-'+str(position),label+' / '+slot
    if group==2:return 'accessory','饰品'
    if group==3:return 'material','材料 / 养成材料'
    if group==5:return 'quest','任务道具'
    if group==6:
        if any(w in name for w in ('药水','药剂','灵药')):return 'consumable-potion','消耗品 / 药水药剂'
        return 'consumable-food','消耗品 / 食品及其他'
    if kind==12:return 'pet','宠物 / 生命结晶'
    if kind==13:return 'mount','骑宠 / 召唤石'
    if kind==14:return 'cosmetic','外观 / 动作及技能切入'
    if kind==15:return 'life','生活 / 钓鱼道具'
    if kind==16:return 'housing','家园 / 家具'
    for key,label,words in (
        ('enhancement','强化及装备养成',('强化','复原','保护','魔法石','鉴定','锻造','铸造')),
        ('ticket','活动门票及入场券',('入场','门票','入场券')),
        ('box','箱子及礼包',('宝箱','箱子','箱','礼包','礼盒','冰雕','挫冰')),
        ('coupon','兑换券及功能券',('兑换','交换券','券','扩张','扩充'))):
        if any(w in name for w in words):return 'special-'+key,'特殊 / '+label
    return 'special-other','特殊 / 其他功能道具'


@functools.lru_cache(maxsize=1)
def icon_index():
    return json.loads((ASSETS/'index.json').read_text('utf8')) if (ASSETS/'index.json').exists() else {}


@functools.lru_cache(maxsize=1)
def catalog():
    from els_server.game_data import client_data
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    from els_server.domain.acquisition_policy import require_acquirable
    from els_server.domain.repair_pass import TEMPLATE
    data = client_data()
    icons=icon_index()
    rows = []
    with data.connect() as db:
        for identity, name,kind,position,flags4,record in db.execute('SELECT id,name,item_type,equip_position,flags4,record FROM items ORDER BY id'):
            if identity not in VERIFIED_TEMPLATES or identity == TEMPLATE:
                continue
            try:require_acquirable(identity)
            except ValueError:continue
            group = TEMPLATE_BAG_GROUPS[identity]
            cat,label=category(group,kind,position,name)
            actual=icons.get(str(identity));family=cat.split('-')[0]
            fallback=family if family in ('equipment','fashion','accessory','consumable','material','special') else 'other'
            rows.append(dict(id=identity, name=name, group=group, bag=BAGS.get(group,str(group)),
                stack=TEMPLATE_MAX_STACKS[identity],icon=actual or ('fallback-'+fallback+'.svg'),icon_original=bool(actual),category=cat,category_name=label,
                category_basis='原生类型/背包与部位；特殊道具细分使用名称标签',level=record[0xd1] if group==1 else None,
                quality=(flags4>>20)&15))
    return tuple(rows)


@functools.lru_cache(maxsize=1)
def facets():
    rows=catalog();counts=Counter((r['category'],r['category_name']) for r in rows)
    groups=Counter((str(r['group']),r['bag']) for r in rows)
    return dict(total=len(rows),with_icons=sum(r['icon_original'] for r in rows),
        categories=[dict(id=k,name=n,count=v) for (k,n),v in sorted(counts.items(),key=lambda x:x[0][1])],
        groups=[dict(id=k,name=n,count=v) for (k,n),v in groups.items()])


def search(query='',group='',offset=0,icons_only=False,category='',sort='relevance',ids=''):
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError('分页位置无效')
    if sort not in ('relevance','id','name','level'):raise ValueError('排序方式无效')
    query=normalize(query)[:100];tokens=query.split();wanted=set()
    if ids:
        raw=re.split(r'[,，\s]+',str(ids).strip())
        if len(raw)>500 or any(not v.isdecimal() for v in raw):raise ValueError('收藏列表无效')
        wanted={int(v) for v in raw}
    rows=[r for r in catalog() if (not tokens or all(t in normalize(str(r['id'])+' '+r['name']) for t in tokens))
        and (not group or str(r['group'])==group) and (not category or r['category']==category)
        and (not icons_only or r['icon_original']) and (not ids or r['id'] in wanted)]
    if sort=='relevance' and query:
        rows.sort(key=lambda r:(0 if str(r['id'])==query else 1 if normalize(r['name'])==query else 2 if normalize(r['name']).startswith(query) else 3,r['id']))
    elif sort=='name':rows.sort(key=lambda r:(normalize(r['name']),r['id']))
    elif sort=='level':rows.sort(key=lambda r:(-(r['level'] or 0),r['id']))
    else:rows.sort(key=lambda r:r['id'])
    return dict(total=len(rows), rows=rows[offset:offset+48], offset=offset)
