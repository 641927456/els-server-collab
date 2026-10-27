"""Bank tiers: original membership enum/KIM and the matching CN guide.

The client asks the server for NextExpandED; prices are not embedded in its
request. The CN official table matches this build's 8..48 tier layout.
https://els.ztgame.com/game/000-1446-00000-652988.shtml
"""
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA
from els_server.paths import PROJECT_ROOT

TIERS=(8,16,24,32,40,48)
ED_COSTS={8:(4_000_000,8_000_000,18_000_000,54_000_000,65_000_000),
          16:(8_000_000,16_000_000,32_000_000,64_000_000,128_000_000)}
ED_LIMITS=(7_000_000_000,14_000_000_000,28_000_000_000,42_000_000_000,56_000_000_000,70_000_000_000)


@functools.lru_cache(maxsize=1)
def player_limits():
    raw=(PROJECT_ROOT/'els_server/data/bank_ed_limits.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='221382880e35deea46d5b07a1d790421fd2de669784338efe104409251bd3589':
        raise ValueError('Original ED limits evidence changed')
    data=json.loads(raw)
    if data['client_sha256']!=CLIENT_SHA or set(data['levels'])!={str(n) for n in range(1,101)}:
        raise ValueError('Original ED limits coverage')
    return data['levels']


def player_ed_limit(level):
    if type(level) is not int or not 1<=level<=99:raise ValueError('Invalid bank character level')
    return player_limits()[str(level)]


def expansion_cost(group,capacity):
    if group not in ED_COSTS or capacity not in TIERS[:-1]:
        raise ValueError('Bank is at maximum capacity or has an invalid tier')
    return ED_COSTS[group][TIERS.index(capacity)]


def require_storable(item,group):
    # 222036D..222037A and 238A823..238A838 reject bit 5 before
    # either bank's move sender. Do not confuse untradeable with unbankable.
    if client_data().item(item['template'])['flags4'] & 32:
        raise ValueError('Original item definition forbids bank storage')
    if group==16:
        from els_server.domain.item_locks import require_unlocked
        require_unlocked(item)
        # Quest ownership and character-only entitlement handlers cannot be
        # transferred as ordinary inventory instances.
        if item['group']==21:
            raise ValueError('Character quest items cannot enter shared bank')
