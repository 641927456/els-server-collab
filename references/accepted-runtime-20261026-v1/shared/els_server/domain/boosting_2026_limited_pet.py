"""Exactly the original selected2026 Dana90 item; other timed SKUs stay closed."""
import functools,hashlib,json
from pathlib import Path
TEMPLATE=721783;UNIT=223;DAYS=90
SHA='f84aaf90f32b8d414043589b4b277bc6f28ec2d5fe8736609c830127a1c6e5b1'
_enabled=False
@functools.lru_cache(maxsize=1)
def definition():
 from els_server.game_data import CLIENT_SHA,client_data
 from els_server.domain.companions import catalog
 from els_server.domain.pet_progression import template
 p=Path(__file__).resolve().parents[1]/'data/boosting2026-limited-pet.json';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Limited Dana definition identity')
 d=json.loads(raw);c=client_data();spec=catalog()['pet'].get(TEMPLATE)
 if (d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256'] or d['template']!=TEMPLATE or d['unit']!=UNIT or d['period_days']!=DAYS
     or d['record_sha256']!=hashlib.sha256(c.item(TEMPLATE)['record']).hexdigest() or d['activation']!=spec or spec!=dict(outcomes=[[UNIT,1]],duration=DAYS,native_extra=DAYS)
     or d['pet_template']!=template(UNIT) or d['step']!=0 or template(UNIT)['PET_STATUS']['1']!=3 or template(UNIT)['EVOLUTION_ALL_STEP']!=0 or not d['free_pickup'] or template(UNIT)['FREE_AUTO_LOOTING']!=1):raise ValueError('Limited Dana original mapping/stage')
 # Original sources verified at composition; runtime pins definition/client.
 return d
def enable():
 global _enabled
 definition();_enabled=True
def enabled():return _enabled
