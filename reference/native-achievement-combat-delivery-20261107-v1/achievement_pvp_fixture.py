"""Explicit owned PvP snapshots, calculated with the approved current policy."""
from contextlib import closing
from dataclasses import asdict
import json,sqlite3,struct
from els_server.domain.pvp_official_1v1_policy import Profile,plan,MAX_RATING_GAP
from els_server.storage import pvp_official_profiles as profiles
from els_server.protocol import pvp_match_messages as wire


def registration():return struct.pack('>IBB?iI',1,0,1,False,0,0)


def balanced_profiles():
    a=b=Profile()
    for turn in range(198):
        win=turn%2==0
        next_a=plan(a,b,outcome='win'if win else'loss',level=75,kills=int(win),
            maximum_damage_kills=int(win),deaths=int(not win)).after
        next_b=plan(b,a,outcome='loss'if win else'win',level=75,kills=int(not win),
            maximum_damage_kills=int(not win),deaths=int(win)).after
        a,b=next_a,next_b
    assert a.wins==a.losses==b.wins==b.losses==99
    assert abs(a.rating-b.rating)<=MAX_RATING_GAP
    return a,b


def register_fixture(path,actor,profile):
    uid,account=actor['uid'],actor['account_id'];profile.checked()
    def guard():
        with closing(sqlite3.connect(path))as db:
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
    operation='owned-pvp-profile-fixture:'+str(uid)
    profiles.register(path,uid,account,registration(),operation,guard=guard,
        encode=lambda *_:(wire.registration_ack(0,False,''),wire.wait_notification(0,((0,1,False),))))
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE');guard()
        assert db.execute('UPDATE official_pvp_profiles SET profile_json=?,revision=?WHERE uid=?AND account_id=?',
            (json.dumps(asdict(profile),sort_keys=True,separators=(',',':')),profile.completed,uid,account)).rowcount==1
        assert profiles.snapshot(db,uid,account)==(profile,profile.completed)
