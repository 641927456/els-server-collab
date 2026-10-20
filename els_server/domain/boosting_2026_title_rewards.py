"""Exact CN20260729 title support outputs; original title lifecycle reused."""
import hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA
BOX=723673
COUPONS=frozenset((721789,721790,721791,721792))
SHA='bb9457a0181c663588d9e9c88db4bcea31222c6d66dda91bc3011419866a938f'
_definition=None

def register():
 global _definition
 p=Path(__file__).resolve().parents[1]/'data/boosting2026-title-support.json';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Selected title support identity')
 d=json.loads(raw);c=client_data()
 if d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']:raise ValueError('Selected title support client identity')
 # Original provenance files are verified at composition/freeze time.
 # Runtime validates this immutable definition plus current client/title consumers.
 from els_server.domain.titles import catalog,definition
 title_items=catalog()['items']
 if d['box']['template']!=BOX or {r['template'] for r in d['coupons']}!=COUPONS or [r['template'] for r in d['outputs']]!=[721789,721790,721791,721792,723610]:raise ValueError('Selected title support finite outputs')
 for r in [d['box'],*d['coupons'],*d['outputs']]:
  item=c.item(r['template'])
  if item['name']!=r['name'] or hashlib.sha256(item['record']).hexdigest()!=r['record_sha256']:raise ValueError('Selected title support native item')
 for r in d['coupons']:
  rule=r['title_item_rule'];td=definition(rule['title'])
  if title_items[str(r['template'])]!=rule or rule['period_days']!=90 or td['m_bAccountTitle']!=0 or td['m_iOpenLevel']!=99:raise ValueError('Selected title original lifecycle')
 for r in d['outputs']:
  if (r['metadata'],r['group'],r['max_stack'],r['quantity'])!=((2,4,999,500) if r['template']==723610 else (0,4,999,1)):raise ValueError('Selected title support grant')
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
 rows=[dict(template=BOX,metadata=0,group=4,max_stack=999),*d['outputs']]
 for r in rows:
  t=r['template'];expected=(r['metadata'],r['group'],r['max_stack'])
  if t in meta and (meta[t],groups[t],stacks[t])!=expected:raise ValueError('Selected title support registration conflict')
 for r in rows:
  t=r['template'];meta[t]=r['metadata'];groups[t]=r['group'];stacks[t]=r['max_stack']
 if _definition is not None and _definition!=d:raise ValueError('Cannot replace selected title support definition')
 _definition=d
 from els_server.domain.cubes import catalog as cubes
 cubes.cache_clear()

def enabled():return _definition is not None
def outputs():return tuple(MappingProxyType(r) for r in _definition['outputs']) if enabled() else ()
def is_coupon(template):return enabled() and template in COUPONS
def is_title(title):return enabled() and title in (13250,13260,13270,13280)
def entry():return MappingProxyType(dict(template=BOX,selection_count=0,entries=outputs(),selected_title_support=True)) if enabled() else None
