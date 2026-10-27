"""Original ordinary enhancement through +13, including broken instances."""
import math,struct
from els_server.game_data import client_data
from els_server.domain.normal_equipment import definitions

# Official changed probabilities; no El's Hammer, profession or event modifier.
# https://els.ztgame.com/html/news/134635d/000-1621-01419-911225.shtml
# Existing level -> success/no change/down/reset[/break] basis points.
# Full original official table: nexon Probability/View?n4ArticleSN=228.
RATES=((10000,0,0,0),(10000,0,0,0),(9000,1000,0,0),(8000,2000,0,0),
       (7000,3000,0,0),(6000,4000,0,0),(2000,8000,0,0),(500,1500,3000,5000),
       (200,1000,2800,4000,2000),(100,700,2700,4000,2500),
       (70,700,2700,3000,3530),(100,700,2700,4000,2500),(100,300,2700,4000,2900))
STONES=(163284,163135) # Original 2245990 material priority: Cobo, then ordinary.


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]


def fee(template,level):
    # Actual 23E8E74..23E8F0E float32 arithmetic. Read price and grade from
    # the immutable template, not from any client-supplied price/level fields.
    if type(level) is not int or not 0<=level<=13:raise ValueError('Invalid enhancement level')
    d=client_data().item(template);raw=d['record'];price=struct.unpack_from('<i',raw,0x1c)[0]
    grade=(d['flags4']>>20)&15
    scale=.05 if level<9 else .1 if level<11 else .15
    factor={1:2,2:1.5,6:2.5}.get(grade,1)
    value=f32(f32(f32(price)*f32(scale))*f32(factor))
    if not math.isfinite(value) or not 0<=value<2**31:raise ValueError('Invalid native enhancement fee')
    return math.trunc(value)


def quote(item,mode=0):
    from els_server.domain.boosting_2026_participation_gear import cannot_enhance
    if cannot_enhance(item['template']):raise ValueError('Participation armor cannot be enhanced')
    d=client_data().item(item['template']);level=item.get('enhancement',0)
    if item['template'] not in definitions() or item['count']!=1 or item['group'] not in (1,9) or d['flags4']&0xa1:
        raise ValueError('Unsupported ordinary enhancement equipment')
    if type(level) is not int or not 0<=level<len(RATES):raise ValueError('Broken equipment or original +13 cap reached')
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    require_current(item);require_unlocked(item)
    from els_server.domain.enhancement_progress import full
    if mode not in (0,1,2,4) or mode==1 and not 7<=level<=10 or mode==2 and level not in (11,12):raise ValueError('Enhancement mode level mismatch')
    if mode==4 and not full(item) or mode!=4 and full(item):raise ValueError('Guaranteed enhancement gauge state mismatch')
    return dict(level=level,mode=mode,ed=fee(item['template'],level),rates=RATES[level])


def outcome(level,roll,mode=0,hammer=False):
    if type(roll) is not int or not 0<=roll<10000:raise ValueError('Invalid enhancement random source')
    from els_server.domain.gm_rates import enhancement_rates
    rates=enhancement_rates(level,RATES[level])
    if hammer:
        extra=min(rates[0],10000-rates[0])
        from els_server.domain.gm_rates import snapshot
        if snapshot()['enhancement'][level] is None:
            rates[0]+=extra;rates[1]-=extra
            if rates[1]<0:raise ValueError('Incomplete original hammer probability table')
        else:
            # Custom rate: proportionally retain failure outcomes after hammer.
            old=10000-rates[0];remain=old-extra
            failures=[n*remain//old if old else 0 for n in rates[1:]]
            failures[0]+=remain-sum(failures)
            rates=[rates[0]+extra,*failures]
    cutoff=0
    for n,weight in enumerate(rates):
        cutoff+=weight
        if roll<cutoff:
            result,updated=((1,level+1),(3,level),(4,level-1),(5,0),(2,-level))[n]
            # Fluorite Ore prevents drop/reset; Crystal prevents reset.
            # Their original failure probabilities become no-change outcomes.
            if mode==1 and result in (4,5) or mode==2 and result==5:return 3,level
            return result,updated
    raise ValueError('Incomplete enhancement probability table')
