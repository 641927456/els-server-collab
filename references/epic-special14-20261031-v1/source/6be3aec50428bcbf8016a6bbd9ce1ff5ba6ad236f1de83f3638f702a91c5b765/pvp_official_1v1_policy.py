"""Approved finite friends-server economics; not a match/result producer.

2026-10-24 authorization f7d58482d2936b5becbdba4bc94798c52929b57609981dc6ea74a44067edf701
binds comparison ee678f734a4e12870aff9e8f311d325ba04a7ba89ba48d0f3ac66dc6685711e7.
The current client owns battle/UI/timers. A future qualified flow must bind both
original actors, loaded match generation and real outcome, then apply this plan
inside the same SQL transaction as both receipts and original quest progress.
This module has no storage, event handlers, clocks, random draws or network IO.
Unknown historic PvP profiles must never be converted into this finite schema.
"""
from dataclasses import dataclass, replace
import math

POLICY = 'official-real-player-1v1-20261024-v1'
MIN_LEVEL = 10
MATCH_TYPE = 0
GAME_TYPE = 0
CHANNEL_CLASS = 12
WIN_KILLS = 1
PLAY_SECONDS = 300
PLACEMENT_MATCHES = 10
MAX_RATING_GAP = 400
RP_CAP = 200000
AP_CAP = 100000
RATING_CAP = 3300
# Original CN PvpMatchResultTable.lua exact 1..80; authorized 81..99 use 80.
EXP_BASE = (0,74,157,234,314,404,492,584,678,789,882,1000,1108,1217,
    1341,1469,1601,1733,1865,2013,2163,2313,2472,2638,2815,2990,
    3176,3371,3572,3775,3995,4214,4452,4690,4936,5200,5473,5746,
    6036,6345,6653,6979,7322,7673,8035,8413,8809,9214,9636,10076,
    10534,11018,11510,12021,12557,13112,13693,14291,14916,15559,
    16236,16940,17662,18419,19211,20029,20873,21763,22678,23628,
    24623,25661,26726,27843,29005,30210,31460,32762,34118,35525)
_BOUNDS = {2:(0,250),3:(150,550),4:(450,950),5:(850,1350),
           6:(1250,1850),7:(1750,2350),8:(2250,2950),9:(2850,3301)}
_DOWN_RP = {2:67,3:111,4:156,5:156,6:200,7:200,8:289}

def _integer(value, low, high, field):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('PvP ' + field)
    return value

@dataclass(frozen=True)
class Profile:
    policy: str = POLICY
    rating: int = 1000
    max_rating: int = 1000
    rank: int = 1
    k_factor: float = 500.0
    rp: int = 0
    ap: int = 0
    completed: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    previous_win: bool = False

    def checked(self):
        if self.policy != POLICY or type(self.previous_win) is not bool:
            raise ValueError('PvP finite profile provenance')
        _integer(self.rating,0,RATING_CAP,'rating')
        _integer(self.max_rating,self.rating,RATING_CAP,'max rating')
        _integer(self.rank,1,9,'rank')
        for name in ('rp','ap','completed','wins','losses','draws'):
            _integer(getattr(self,name),0,2**31-1,name)
        if self.wins+self.losses+self.draws != self.completed:
            raise ValueError('PvP counters')
        if self.completed < PLACEMENT_MATCHES:
            if self.rank != 1: raise ValueError('PvP placement rank')
        else:
            _integer(self.rank,2,9,'rank')
        if type(self.k_factor) not in (int,float) or not math.isfinite(self.k_factor) or not 0 <= self.k_factor <= 500:
            raise ValueError('PvP K factor')
        return self

@dataclass(frozen=True)
class EconomicPlan:
    before: Profile
    after: Profile
    raw_exp: int
    play_increment: int
    win_increment: int
    outcome: str

    @property
    def rating_delta(self): return self.after.rating-self.before.rating
    @property
    def rp_delta(self): return self.after.rp-self.before.rp
    @property
    def ap_delta(self): return self.after.ap-self.before.ap

def _add_balance(old, change, cap):
    # Never trim an existing above-cap balance just because a reward is added.
    return max(0,old+min(change,max(0,cap-old))) if change>=0 else max(0,old+change)

def _rank(old, rating):
    result=old
    while True:
        lo,hi=_BOUNDS[result]
        if rating<lo: result-=1
        elif rating>=hi: result+=1
        else: return result

def _next_k(p, win):
    if p.completed<10:
        return p.k_factor*.8 if p.completed>0 and p.previous_win!=win else p.k_factor
    if p.completed>29 and p.rating<1851: return 32.0
    if p.rating>2350: return 12.0
    if p.rating>1850: return 24.0
    if p.rating>1350: return 36.0
    if p.rating>950: return 48.0
    return 60.0

def plan(p, opponent, *, outcome, level, kills=0, maximum_damage_kills=0, deaths=0):
    """Economics for an already-authorized outcome; never validates a battle.

    outcome win/loss/draw means a completed real match; leave is the leaver's
    penalty; aborted is the other actor when an opponent leaves before 30 s.
    The caller must prove elapsed time/outcome; this pure module cannot do so.
    raw_exp is an award request before the existing ordinary-XP cap. It must
    not be rerouted into ERP or injected into a native calculation here.
    """
    if type(p) is not Profile or type(opponent) is not Profile:
        raise ValueError('PvP profile type')
    p.checked();opponent.checked()
    _integer(level,MIN_LEVEL,99,'level')
    for name,value in (('kill',kills),('maximum damage kill',maximum_damage_kills),('death',deaths)):
        _integer(value,0,1,name)
    if outcome not in ('win','loss','draw','leave','aborted'):
        raise ValueError('PvP outcome')
    if outcome=='aborted': return EconomicPlan(p,p,0,0,0,outcome)
    if outcome=='leave':
        win_ap=math.floor(2*(math.floor(p.rating*.01)+10)+.5)
        after=replace(p,rp=_add_balance(p.rp,-60,RP_CAP),ap=_add_balance(p.ap,-5*win_ap,AP_CAP))
        return EconomicPlan(p,after.checked(),0,0,0,outcome)
    completed=p.completed+1
    _integer(completed,0,2**31-1,'completed')
    if outcome=='draw':
        # Explicit authorized draw: no economic delta, but a real play counts.
        rank=_rank(2,p.rating) if completed==10 else p.rank
        after=replace(p,completed=completed,draws=p.draws+1,rank=rank)
        return EconomicPlan(p,after.checked(),0,1,0,outcome)
    win=outcome=='win'
    expected=1/(1+10**((opponent.rating-p.rating)/400))
    own_placement=p.completed<10; enemy_placement=opponent.completed<10
    k=p.k_factor; rating=p.rating
    if win or own_placement or not enemy_placement:
        k=_next_k(p,win)
        rating_change=k*(int(win)-expected)
        # Exact legacy call-site condition is equality, not merely both True.
        if not win and own_placement==enemy_placement: rating_change*=.5
        rating=max(0,min(RATING_CAP,p.rating+math.trunc(rating_change)))
    if completed<10: rank=1
    else: rank=_rank(2 if p.rank==1 else p.rank,rating)
    rp_change=math.trunc(max(12*(int(win)-expected),-6)+max(-4,min(12,kills+maximum_damage_kills-deaths)))
    if rank>p.rank and rank!=1: rp=0
    elif rank<p.rank: rp=_DOWN_RP[rank]
    else: rp=_add_balance(p.rp,rp_change,RP_CAP)
    ap_change=math.floor((2 if win else .5)*(math.floor(p.rating*.01)+10)+.5)
    # Decimal fifths, integer division: exact 1/.2 + .2*kill base, avoids
    # accidental binary-float truncation of an integer expected reward.
    raw_exp=EXP_BASE[min(level,80)-1]*((5 if win else 1)+min(kills+maximum_damage_kills,3))//5
    after=replace(p,rating=rating,max_rating=max(p.max_rating,rating),rank=rank,k_factor=k,
        rp=rp,ap=_add_balance(p.ap,ap_change,AP_CAP),completed=completed,
        wins=p.wins+int(win),losses=p.losses+int(not win),previous_win=win)
    return EconomicPlan(p,after.checked(),raw_exp,1,int(win),outcome)
