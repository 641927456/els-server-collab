"""Current guild definitions and the explicitly approved warehouse exceptions."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json

DATA_SHA256 = 'cc9487cafd32effdcc6e3c3fdcd8f7e5cda8a0c9de14a2617e500953eb94f19d'


@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/guild_system.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA256:
        raise ValueError('Guild definitions changed')
    return json.loads(raw)


def calls(name):
    return catalog()['calls'][name]


def authorities():
    result={row[0]:tuple(row[1:])for row in calls('SetGuildMemberAuthority')}
    result[1]=(*result[1][:4],catalog()['local_overrides']['bank_master_daily_withdrawals'],*result[1][5:])
    result[6]=(False,False,False,False,0,0,0)
    return result


def week(now):
    # CN official guild reset: Wednesday10:00, UTC+8.
    return (now-525600)//604800


def next_week(now):
    # Unix epoch was Thursday. Wednesday10 local is Unix epoch +6days+2hours.
    offset=6*86400+2*3600
    return ((now-offset)//604800+1)*604800+offset


def day(now):
    return (now+8*3600)//86400


def initial():
    return dict(version=2,capacity=20,experience=0,announcement='',rules='',advertisement=None,
        grade_names={},announcement_author=0,authorities={str(k):list(v)for k,v in authorities().items()},
        pages={'1':dict(skills={},cash_points=0,cash_expires=0,alias='')},
        emblems=[row[0]['EMBLEM_ID']for row in calls('AddGuildEmblem')if row[0]['ACQUISITION_CONDITION']==1],
        equipped_emblems={str(row[0]['EMBLEM_TYPE']):row[0]['EMBLEM_ID']for row in calls('AddGuildEmblem')if row[0]['ACQUISITION_CONDITION']==1},
        emblem_enhancement={},emblem_expiry={},skins={},skin=0,services={},farm_slots=1,
        fertilizer=0,plots={},watering={},expedition=None,fountain={},fountain_week=None,
        member_details={},applications={},posts=[])


def level(experience):
    return max(row[0]for row in calls('AddGuildEXP')if row[0]<=30 and row[2]<=experience)


def permission(saved, state, index):
    return bool(state['authorities'][str(saved['grade'])][index])


def plants():
    return {row[0]['GUILD_PLANT_ID']:row[0]for row in calls('AddGuildPlant')}


def expedition_rules():
    return calls('SetGuildExpedition')[0][0]
