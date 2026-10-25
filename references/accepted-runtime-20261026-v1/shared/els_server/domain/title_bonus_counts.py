"""Owned equipped title's extra-count chance, from pinned current option data.

This applies only to admitted obtain kill/clear objectives. Discovery, weekly,
collection and unrelated events are not inferred. Native battle effects remain
client-owned. Caller owns the reward/death receipt and the same SQL transaction.
"""
import functools
from secrets import randbelow as _randbelow
from decimal import Decimal
from els_server.domain.title_option_data import SOURCES,catalog

EFFECTS=frozenset((74041,82143))

@functools.lru_cache(maxsize=1)
def effects():
    found={}
    for key in EFFECTS:
        row=catalog()[key]
        if set(row)!={'ID','m_fBonusTitleMissionCountingRate','TYPE','STAT','OVER_LAP'} or row['TYPE']!=7 or row['STAT'] or row['OVER_LAP']!=0:raise ValueError('Unreviewed title bonus condition')
        basis=Decimal(str(row['m_fBonusTitleMissionCountingRate']))*10000
        if basis!=int(basis) or not 0<int(basis)<=10000:raise ValueError('Title bonus probability bound')
        found[key]=int(basis)
    if set(found)!=EFFECTS or found!={74041:1500,82143:2000}:raise ValueError('Title bonus scope changed')
    return found

def rate(db,character,now):
    from els_server.storage import titles
    from els_server.domain.titles import definition
    current=titles.snapshot(db,character['uid'],now)
    if not current['title']:return 0
    options=set(v for v in definition(current['title'])['SOCKET_OPTION'].values() if v)&EFFECTS
    if not options:return 0
    # Current titles have exactly one such non-overlap option. Do not infer
    # cross-source synergy, medals or multiple-title stacking.
    if len(options)!=1:raise ValueError('Unreviewed multiple title count bonuses')
    return effects()[next(iter(options))]

def increment(remaining,basis,*,randbelow=None):
    if type(remaining) is not int or not 1<=remaining<=32767 or type(basis) is not int or not 0<=basis<=10000:raise ValueError('Title bonus increment bound')
    if not basis or remaining==1:return 1
    draw=(randbelow or _randbelow)(10000)
    if type(draw) is not int or not 0<=draw<10000:raise ValueError('Title bonus draw bound')
    return 2 if draw<basis else 1
