"""Source-bound Silver Mirror Valley policy; no player writes or client effects.

The weekly ordering is an explicitly authorized local choice. Client encounter
IDs and CN Wednesday 10:00 boundaries are independent source facts.
"""
import datetime as dt
import hashlib

UTC8 = dt.timezone(dt.timedelta(hours=8))
NORMAL = (35720, 35730, 35740, 35750)
THIRD = (35780, 35790)
SPECIAL = (35760, 35770)
STORY = {35720: 35800, 35730: 35810, 35740: 35820, 35750: 35830,
         35760: 35840, 35770: 35850, 35780: 35820, 35790: 35830}
FAMILY = {**{n: n for n in NORMAL + SPECIAL}, 35780: 35740, 35790: 35750}
ALL = frozenset(STORY) | frozenset(STORY.values())
WEEKLY_REWARDS = 5
MEMORY_THRESHOLD = 4
GUARANTEED_STONE = 136228

def blackout(now):
    start=week_start(now)
    return now<start+600 or now>=start+7*86400-600


def week_start(now):
    if type(now) not in (int, float) or not 0 <= now < 253402200000:
        raise ValueError('Silver Mirror clock range')
    local = dt.datetime.fromtimestamp(now, UTC8)
    day = local.date() - dt.timedelta(days=(local.weekday() - 2) % 7)
    reset = dt.datetime.combine(day, dt.time(10), UTC8)
    if local < reset:
        reset -= dt.timedelta(days=7)
    return int(reset.timestamp())


def layout(week):
    if type(week) is not int or week_start(week) != week:
        raise ValueError('Silver Mirror week identity')
    # There is no published server seed or exact deployment probability.
    # Freeze one shared local order per week, independent of login, UID or RNG
    # retries; all characters observe the same order in both server channels.
    digest = hashlib.sha256(b'els-silver-mirror-week-v1:' + str(week).encode()).digest()
    third = THIRD[digest[0] % len(THIRD)]
    pool = [n for n in NORMAL if n != FAMILY[third]]
    pool.sort(key=lambda n: hashlib.sha256(digest + str(n).encode()).digest())
    special = SPECIAL[(week // (7 * 86400)) % len(SPECIAL)]
    return (pool[0], pool[1], third), special


def deployed(week, memory):
    if type(memory) is not int or not 0 <= memory <= MEMORY_THRESHOLD:
        raise ValueError('Silver Mirror memory range')
    normal, special = layout(week)
    return (*normal[:2], special if memory == MEMORY_THRESHOLD else normal[2])


def slot(week, memory, dungeon):
    if type(dungeon) is not int or dungeon not in ALL:
        raise ValueError('Silver Mirror encounter identity')
    # Native DC_STORY shows six independent buttons and hides normal stage
    # progression and buffs. Never turn their IDs into normal reward aliases.
    if dungeon in STORY.values():return -1
    normal = deployed(week, memory)
    matches = [i for i, n in enumerate(normal) if dungeon == n]
    if len(matches) != 1:
        raise ValueError('Encounter is not deployed in this Silver Mirror week')
    return matches[0]


def validate_progress(progress):
    if type(progress) is not int or not 0 <= progress <= 2:
        raise ValueError('Silver Mirror progress range')
    return progress


def eligible(week, memory, progress, dungeon):
    validate_progress(progress)
    index = slot(week, memory, dungeon)
    # Repeating already cleared stages is needed to replace their buffs.
    if index > progress:
        raise ValueError('Clear the preceding Silver Mirror stage first')
    return index


def cleared(week, memory, progress, remaining, dungeon):
    if type(remaining) is not int or not 0 <= remaining <= WEEKLY_REWARDS:
        raise ValueError('Silver Mirror reward count range')
    index = eligible(week, memory, progress, dungeon)
    if index==-1:return dict(progress=progress,memory=memory,remaining=remaining,weekly=False,slot=-1,clear_buffs=False)
    weekly = index == 2 and remaining > 0
    special = dungeon in SPECIAL or dungeon in (STORY[n] for n in SPECIAL)
    return dict(progress=0 if index == 2 else max(progress, index + 1),
                memory=(0 if special else memory + 1) if weekly else memory,
                remaining=remaining - int(weekly), weekly=weekly, slot=index,
                clear_buffs=index == 2)
