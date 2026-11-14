"""CN July boost event containers: shared-bank ban and local event deadline.

Opened equipment/pets/titles keep their own 90-day lifetime. Only the exact
containers and activation coupons listed by the event announcement expire here.
"""
from functools import cache
from pathlib import Path
import json

EVENT_ITEMS=frozenset((723680,723612,721780,723613,723614,721783,723615,
    723673,721788,723618,723616,721785,721786,721789,721790,721791,721792,
    720746,723617,723635,723688,723687,723621,723619,723620,723634))

@cache
def deadline():
    configuration=json.loads((Path(__file__).resolve().parents[1]/'data/selected2026/local-growth.json').read_bytes())['configuration']
    # The native expiry reader uses now > deadline; the event ends exclusively.
    return configuration['ends']-1

def item_deadline(item):
    value=item.get('expires_at')
    if item.get('template') in EVENT_ITEMS:
        return deadline() if value is None else min(value,deadline())
    return value
