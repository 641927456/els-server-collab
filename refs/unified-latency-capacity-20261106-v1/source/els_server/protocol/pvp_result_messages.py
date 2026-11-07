"""Current native C2 byte codec; all outcomes/economics come from the writer."""
import struct

def player(uid,rank,kills,maximum_damage_kills,deaths,rating_delta,ap_delta,experience,win):
    from els_server.protocol.mail_messages import empty_item
    ints=(rank,kills,maximum_damage_kills,deaths,rating_delta,ap_delta,0,experience)
    if type(uid)is not int or not 0<uid<2**63 or type(win)is not bool:
        raise ValueError('PvP result player identity')
    if any(type(n)is not int or not -2**31<=n<2**31 for n in ints):raise ValueError('PvP result scalar')
    # 2C19C70 constructor zeros fields for disabled bonus systems. Unknown
    # appended economic fields receive no fabricated balances or bonuses.
    body=struct.pack('>Q8iB',uid,*ints,win)+bytes(16+60+4+1+4+2+8)
    body+=bytes(4+4)+empty_item()  # empty +88 map, +98 scalar, +9C item
    assert len(body)==448
    return body

def result(winner_team,seconds,players,*,spirit,draw=False,abnormal=False):
    if winner_team not in (0,1)or type(seconds)is not int or not 0<=seconds<=300:
        raise ValueError('Finite PvP first-kill result')
    if type(spirit)is not int or not 0<=spirit<2**31 or len(players)!=2:
        raise ValueError('PvP explicit saved spirit and two original players')
    if type(draw)is not bool or type(abnormal)is not bool:raise ValueError('PvP result flags')
    body=struct.pack('>bBBiiiII',winner_team,draw,abnormal,seconds,0,spirit,12,2)+b''.join(players)
    # Ordinary no item/bonus acquisition; native constructor defaults.
    return body+bytes(2+4+4+3+4)
