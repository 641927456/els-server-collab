"""Pinned resonance thresholds and the original client's experience display.

Wire 0x610 field04 / character+0x2865 is cumulative experience. The native
Lua loader inserts NEED_ER_EXP at node+28 and TOTAL_ER_EXP at node+30.
This module does not decide how a growth award treats an existing partial bar,
alter point allocations, or persist an account. Those transitions need their
own verified transaction rules.
"""
from dataclasses import dataclass
import hashlib
import json
import struct

CURVE_SHA256='24b70a500fa01f7cc6204ed0d0fe3af740b3c88e3a49bb0f49d7430f9ddc2708'


def checked_integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid resonance ' + name)
    return value


def f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


@dataclass(frozen=True)
class ResonanceCurve:
    needed: tuple
    total: tuple

    @classmethod
    def from_client_data(cls, client_data):
        rows=client_data.resonance_curve()
        raw=json.dumps(rows,sort_keys=True,separators=(',',':')).encode()
        if hashlib.sha256(raw).hexdigest()!=CURVE_SHA256:
            raise ValueError('Unverified resonance curve')
        if [r['ER_LEVEL'] for r in rows]!=list(range(1,1001)):
            raise ValueError('Incomplete resonance curve')
        needed=tuple(int(r['NEED_ER_EXP']) for r in rows)
        total=tuple(int(r['TOTAL_ER_EXP']) for r in rows)
        if any(n!=r['NEED_ER_EXP'] or t!=r['TOTAL_ER_EXP'] for r,n,t in zip(rows,needed,total)):
            raise ValueError('Non-integral resonance experience')
        if needed[0]!=0 or total[0]!=0 or any(total[i]-total[i-1]!=needed[i] or needed[i]<=0 for i in range(1,1000)):
            raise ValueError('Inconsistent resonance thresholds')
        return cls(needed,total)

    def threshold(self, level):
        """Exact original minimum cumulative experience; not an award command."""
        checked_integer(level,'curve level',1,1000)
        return self.total[level-1]

    def next_level_cost(self, level):
        checked_integer(level,'display level',1,999)
        return self.needed[level]

    def display_fraction(self, level, cumulative_experience):
        """378F9B6..378FAA8 float32 arithmetic; 999 displays a full bar.

        Inconsistent level/experience inputs are clamped for display just as
        the client does. They are not validated or repaired as account state.
        """
        checked_integer(level,'display level',1,999)
        checked_integer(cumulative_experience,'cumulative experience',0,2**63-1)
        if level==999:
            return 1.0
        numerator=f32(f32(cumulative_experience)-f32(self.threshold(level)))
        result=f32(numerator/f32(self.next_level_cost(level)))
        return min(1.0,max(0.0,result))
