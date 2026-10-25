"""Finite original17-output accessory chain, with explicit90day inner rings."""
import hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA
BOXES=frozenset((723615,721785,721786));SHA='c0cfcdd3438dfbee3bc53663cdf0fc86d106b2f2a9d4c2aa24d10fd5816bcc60'
_items={};_boxes={}
RING_TEMPLATES=frozenset((714231,714232,714233,714234,720739))
RING_SIDES={17:0,41:0,32:1,42:1}
RING_CONFLICT_SIDES={17:0,41:0,49:0,54:0,32:1,42:1,61:1,66:1}


def register():
 global _items,_boxes
 p=Path(__file__).resolve().parents[1]/'data/boosting2026-accessories.json';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Selected accessory definition identity')
 d=json.loads(raw);c=client_data();enum=c.resource('Enum.lua');names={v:k for k,v in enum['EQIP_POSITION'].items()};slots=enum['NOW_EQIP_SLOT_ID']
 if (slots['NESI_AC_RING'],slots['NESI_AC_RING2'],slots['NESI_MINORUNIT_AC_RING'],slots['NESI_MINORUNIT_AC_RING2'])!=(17,41,32,42):raise ValueError('Original dual ordinary ring enum')
 if d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']:raise ValueError('Selected accessory client identity')
 # Provenance verified at composition; immutable definition and client are checked here.
 items={r['template']:r for r in d['items']};boxes={r['template']:r for r in d['boxes']};assert len(items)==20 and set(boxes)==BOXES
 if len(d['original_category77_ids'])!=135 or set(items)&set(d['original_category77_ids']):raise ValueError('Unverified PC-bang-only accessory')
 for t,r in items.items():
  item=c.item(t);record=item['record'];name=names[item['equip_position']]
  if t in RING_TEMPLATES and int.from_bytes(record[0x34:0x38],'little')!=(200700 if t==720739 else 183404):raise ValueError('Selected ring original equipment group changed')
  if (hashlib.sha256(record).hexdigest()!=r['record_sha256'] or item['name']!=r['name'] or item['item_type']!=3 or item['metadata']!=0 or record[210:212]!=bytes(2)
      or item['flags4']&0x10 or (item['flags4']>>12)&15!=1 or not item['flags4']&0xf00 or any(item['stats']) or any(item['stat_bonus'])
      or (r['group'],r['max_stack'],r['quantity'],r['slot'],r['minor_slot'])!=(2,1,1,slots['NESI_'+name[3:]],slots['NESI_MINORUNIT_'+name[3:]]) or r['period_days'] not in (0,90)):raise ValueError('Selected accessory native scope')
 for t,r in boxes.items():
  if c.item(t)['name']!=r['name'] or hashlib.sha256(c.item(t)['record']).hexdigest()!=r['record_sha256'] or r['selection_count']!=0 or r['metadata']!=0 or len(r['outputs'])!={723615:17,721785:4,721786:1}[t]:raise ValueError('Selected accessory original box')
 if _items and (_items!=items or _boxes!=boxes):raise ValueError('Cannot replace selected accessory definition')
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
 for t,r in {**items,**boxes}.items():
  expected=(r['metadata'],r['group'],r['max_stack'])
  if t in meta and (meta[t],groups[t],stacks[t])!=expected:raise ValueError('Selected accessory registration conflict')
 for t,r in {**items,**boxes}.items():meta[t]=r['metadata'];groups[t]=r['group'];stacks[t]=r['max_stack']
 _items,_boxes=items,boxes
 from els_server.domain.cubes import catalog
 catalog.cache_clear()
def items():return MappingProxyType(_items)
def boxes():return MappingProxyType(_boxes)
def entries():return tuple(MappingProxyType(dict(template=t,selection_count=0,entries=tuple(dict(r) for r in b['outputs']),selected_accessories=True)) for t,b in sorted(_boxes.items()))

def validate_box_grants(template,plan):
 # This finite context is supplied only by the owned-box transaction, never
 # by generic drops, shops or client data. Do not change compatibility flags.
 rule=_boxes.get(template)
 if rule is None or not isinstance(plan,list) or len(plan)!=len(rule['outputs']):raise ValueError('Selected accessory grant source')
 expected=[r['template'] for r in rule['outputs']]
 if [p.get('template') for p in plan]!=expected:raise ValueError('Selected accessory exact box outputs')
 from els_server.domain.acquisition_policy import excluded_equipment
 from els_server.domain.ordinary_accessories import definitions
 deadlines=set()
 for p in plan:
  t=p['template'];r=_items.get(t)or _boxes.get(t)
  if t in excluded_equipment() or r is None or (p.get('metadata'),p.get('group'),p.get('quantity'))!=(r['metadata'],r['group'],1):raise ValueError('Selected accessory grant identity')
  days=r.get('period_days',0)
  if set(p)!={'template','metadata','group','quantity'}|({'expires_at'}if days else set()):raise ValueError('Selected accessory grant instance fields')
  if days:
   from els_server.domain.item_expiration import validate
   validate(p['expires_at']);deadlines.add(p['expires_at'])
  if t in _items and (t not in definitions() or definitions()[t]['restricted']):raise ValueError('Selected accessory generic consumer scope')
 if len(deadlines)>1:raise ValueError('Selected accessory common inner opening deadline')
 return True
