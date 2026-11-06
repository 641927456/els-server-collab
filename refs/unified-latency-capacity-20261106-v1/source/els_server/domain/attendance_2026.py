"""Verified rules for the selected 2026 CN Hedgehog attendance campaign.

This module does not choose a reset anchor or authorize an award. The session
must supply the verified campaign schedule and account's authoritative counters.
Original RewardIDs remain unresolved and must not be replaced by name matches.
"""
from dataclasses import dataclass


def _nonnegative_int(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(name + ' must be a nonnegative integer')
    return value


@dataclass(frozen=True)
class AttendanceDefinition:
    code: int
    quest_id: int
    minimum_level: int
    days: int
    max_purchases: int
    ed_cost: int
    daily_reward_ids: tuple
    excluded_dungeons: frozenset

    @classmethod
    def from_original(cls, document):
        script = document['script_call']['arguments'][-1]
        quest = document['quest']['quest']
        rewards = script['Reward']
        rows = sorted(rewards['Day'].values(), key=lambda row: row['Index'])
        subquests = {row['definition']['m_iID']: row['definition']
                     for row in document['quest']['subquests']}
        # Reject another season or a silently extended reward family.
        if (script['UIFileName'] != 'STX_UI_AttendanceEvent202605'
                or document['icon']['CODE_EVENT_ID'] != 518
                or set(rewards) != {'Day'}
                or [row['Index'] for row in rows] != list(range(42))
                or script['MaxAttendance'] != 42 or script['MaxPurchase'] != 21
                or script['EDCost'] != 70000000
                or quest['m_iID'] != 166210 or quest['m_bIsAccount'] != 1
                or quest['m_iClearSubQuestCount'] != 1
                or quest['QuestCondition']['m_iLevel'] != 10
                or subquests[1000005]['m_ClearCondition']['m_iDungeonClearCount'] != 5
                or subquests[165620]['m_ClearCondition']['m_iClearCount'] != 60):
            raise ValueError('Not the selected original 2026 attendance definition')
        exclusions = subquests[1000005]['m_ClearCondition']['m_eExceptionDungeonID']
        return cls(518, 166210, 10, 42, 21, 70000000,
                   tuple(row['RewardID'] for row in rows),
                   frozenset(v for k, v in exclusions.items() if str(k) != '0' and v is not None))

    def counts_as_dungeon_clear(self, dungeon_id, *, appropriate_level):
        """The existing dungeon-level rule must supply appropriate_level."""
        _nonnegative_int(dungeon_id, 'dungeon_id')
        if type(appropriate_level) is not bool:
            raise ValueError('appropriate_level must be resolved by the dungeon rule')
        return appropriate_level and dungeon_id not in self.excluded_dungeons

    def daily_conditions_met(self, *, level, qualifying_dungeon_clears, online_seconds):
        """Task166210: level10 and (five qualifying clears OR sixty minutes).

        A true result is only the task's counter condition, not permission to
        grant, stamp again, bypass an expired campaign or skip account scoping.
        """
        for n, v in [('level', level), ('clears', qualifying_dungeon_clears), ('online_seconds', online_seconds)]:
            _nonnegative_int(v, n)
        return level >= self.minimum_level and (qualifying_dungeon_clears >= 5 or online_seconds >= 3600)

    @property
    def has_weekly_rewards(self):
        return False


def elapsed_display_periods(anchor_epoch_seconds, now_epoch_seconds, *,
                            period_parameter=None, active=True, maximum_attendance=42):
    """EE5650 for CN's fixed UTC+8 local calendar (no DST).

    Both inputs are integer epoch seconds. The selected state's anchor is
    supplied, never inferred from a login or the announcement's start date.
    Native default is 86400 seconds; only a positive first event parameter
    overrides it. The return value is not capped by maximum_attendance.
    This elapsed value is UI input, not a daily reset or reward permission.
    """
    _nonnegative_int(anchor_epoch_seconds, 'anchor')
    _nonnegative_int(now_epoch_seconds, 'now')
    if type(active) is not bool or type(maximum_attendance) is not int:
        raise ValueError('Invalid activity configuration')
    if period_parameter is not None and type(period_parameter) is not int:
        raise ValueError('Period must be an integer')
    if not active or maximum_attendance <= 0 or now_epoch_seconds < anchor_epoch_seconds:
        return 0
    period = period_parameter if period_parameter is not None and period_parameter > 0 else 86400
    return (now_epoch_seconds - anchor_epoch_seconds) // period
