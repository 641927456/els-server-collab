"""Native 868430 ring-effect exclusions, separately for Lu and Ciel.

The current template's signed int32 at +34 is the exclusion key; zero means
unrestricted. The consumer compares ordinary and avatar rings on the same
side. No ring effects, new item sources or avatar slot unlocks are added here.
"""
import functools,struct
from els_server.game_data import client_data

@functools.lru_cache(maxsize=1)
def sides():
    e=client_data().resource('Enum.lua')['NOW_EQIP_SLOT_ID']
    suffixes=('AC_RING','AC_RING2','AC_AVATAR_RING','AC_AVATAR_RING2')
    return tuple(frozenset(e[p+s] for s in suffixes) for p in ('NESI_','NESI_MINORUNIT_'))

def require_compatible(item,items):
    if item['group']!=9:return
    side=next((s for s in sides() if item['slot'] in s),None)
    if side is None:return
    raw=client_data().item(item['template'])['record']
    key=struct.unpack_from('<i',raw,0x34)[0]
    if not key:return
    for other in items:
        if other['uid']==item['uid'] or other['group']!=9 or other['slot'] not in side:continue
        if struct.unpack_from('<i',client_data().item(other['template'])['record'],0x34)[0]==key:
            raise ValueError('Ring effect group already equipped on this side')
