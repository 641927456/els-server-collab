"""Finite native vouchers; 999/one coupon/zero ED are USER LOCAL rules."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data
DATA_SHA='747b8c5e838308d4b5a105d90ff650a3604d69889532a1a26f5889b801a0f0e3'
@functools.lru_cache(maxsize=1)
def policy():
    raw=(Path(__file__).resolve().parents[1]/'data/exascale_color_local_policy.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Color local policy identity')
    c=json.loads(raw)
    if c['max_stack']!=999 or c['quantity_per_use']!=1 or c['ed_per_use']!=0 or len(c['vouchers'])!=16:raise ValueError('Color local policy scope')
    for row in c['vouchers'].values():
        d=client_data().item(row['template'])
        if d['metadata']!=row['metadata'] or d['item_type']!=7 or row['group']!=4 or row['max_stack']!=999 or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']:raise ValueError('Color voucher original record identity')
    return c
def definitions():return policy()['vouchers'].values()
