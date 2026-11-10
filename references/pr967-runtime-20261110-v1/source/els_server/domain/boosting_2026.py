"""Selected CN July 2026 combat boost: original task and resonance rules.

Inputs to the query methods must come from authoritative account/quest state.
This module does not bind an account, consume a client completion claim, grant
items, or activate an event. JoinReward 8173 remains unresolved. SpecialRewardID
is preserved as metadata and is NOT automatically added to the item award.
"""
from dataclasses import dataclass
import hashlib
import json
from functools import lru_cache


SOURCE_SHA256 = 'de3534de61546f5a40d9b5c36df5d30c039b91bd39c5bf237e828c296b8c1b4d'


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name + ' must be an integer >= ' + str(minimum))
    return value


def lua_values(table):
    return tuple(v for k, v in sorted(table.items(), key=lambda pair: int(pair[0]))
                 if str(k) != '0' and v is not None)


@dataclass(frozen=True)
class ItemAward:
    item_id: int
    quantity: int
    period: int
    socket_option: int


@dataclass(frozen=True)
class BoostingTask:
    quest_id: int
    title: str
    minimum_level: int
    prerequisites: tuple
    subquest_id: int
    condition_kind: int
    required_count: int
    dungeon_ids: tuple
    items: tuple
    resonance_target: int | None
    special_reward_id: int | None
    opens_pporu: bool
    raid: bool
    display_progress: int


@dataclass(frozen=True)
class BoostingDefinition:
    code: int
    minimum_level: int
    join_reward_id: int
    join_resonance_target: int
    icon: str
    tasks: tuple

    @classmethod
    def from_original(cls, raw):
        # Cache only immutable verified definitions, never account/page state.
        # Mutable and unusual inputs retain the original uncached validation.
        if type(raw) is bytes:
            return _original_definition(cls, raw)
        return cls._parse_original(raw)

    @classmethod
    def _parse_original(cls, raw):
        """Load only the audited fixed-client source, not a similarly named season."""
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
            raise ValueError('Unverified combat boost source')
        source = json.loads(raw)
        script = source['original_script_call']['arguments'][-1]
        ui = {r['QuestID']: r for r in script['EventQuestID'].values()}
        tasks = []
        for row in source['quests']:
            q = row['definition']
            sub, = row['subquests']
            sub = sub['definition']
            condition = sub['m_ClearCondition']
            data = ui[q['m_iID']]
            kind = sub['m_eClearType']
            if kind not in (8, 116):
                raise ValueError('Unsupported original condition')
            awards = tuple(ItemAward(x['m_iItemID'], x['m_iQuantity'], x['m_iPeriod'], x['m_sSocketOption'])
                           for x in lua_values(q['Reward']['m_vecItem']))
            tasks.append(BoostingTask(
                q['m_iID'], row['translation']['m_wstrTitle'],
                q['QuestCondition']['m_iLevel'],
                lua_values(q['QuestCondition']['m_vecBeforeQuestID']),
                sub['m_iID'], kind,
                condition['m_iDungeonClearCount' if kind == 8 else 'm_iClearCount'],
                lua_values(condition.get('m_eDungeonID', {})), awards,
                data['Value'] if data.get('IsErLevelUp') == 1 else None,
                data.get('SpecialRewardID'), data.get('OpenPporu') == 1,
                data.get('IsRaid') == 1, data['LogProgress']))
        tasks.sort(key=lambda task: task.quest_id)
        if (source['code_id'] != 678 or script['JoinReward'] != 8173
                or script['DirectErLevelUp'] != 200
                or [t.quest_id for t in tasks] != list(range(169500, 169520))
                or any(t.minimum_level != 99 for t in tasks)):
            raise ValueError('Wrong selected campaign')
        for i, task in enumerate(tasks):
            if task.prerequisites != (() if i == 0 else (tasks[i - 1].quest_id,)):
                raise ValueError('Unexpected original task chain')
        return cls(678, 99, 8173, 200, source['original_icon']['ICON_FILE_NAME'], tuple(tasks))

    def task(self, quest_id):
        integer(quest_id, 'quest_id')
        for task in self.tasks:
            if task.quest_id == quest_id:
                return task
        raise ValueError('Not a selected combat boost quest')

    def completed_prefix(self, completed):
        """Selected successful quest receipts only; active/ready quests are excluded."""
        values = tuple(completed)
        for value in values:
            integer(value, 'completed quest')
        if len(set(values)) != len(values):
            raise ValueError('Duplicate completed quest')
        ordered = tuple(sorted(values))
        expected = tuple(t.quest_id for t in self.tasks[:len(values)])
        if ordered != expected:
            raise ValueError('Non-contiguous or foreign completed quest state')
        return len(values)

    def next_task(self, *, level, character_uid, bound_character_uid, completed):
        """No binding is inferred from level or from this query."""
        integer(level, 'level')
        integer(character_uid, 'character_uid', 1)
        integer(bound_character_uid, 'bound_character_uid')
        count = self.completed_prefix(completed)
        if level < self.minimum_level or character_uid != bound_character_uid or count == len(self.tasks):
            return None
        return self.tasks[count]

    def dungeon_progress(self, quest_id, dungeon_counts):
        """Counts must be post-acceptance, committed clears for this task's role.

        Task169501/type116 cannot be completed by a dungeon clear or by this
        module; its original accessory Apply handler is still required.
        """
        task = self.task(quest_id)
        if task.condition_kind != 8:
            raise ValueError('Original type116 accessory Apply handler still required')
        total = 0
        for dungeon_id, count in dungeon_counts.items():
            integer(dungeon_id, 'dungeon_id', 1)
            integer(count, 'dungeon count')
            if dungeon_id in task.dungeon_ids:
                total += count
        return min(total, task.required_count)

    def resonance_after_join(self, current_level):
        """Target only: applying it requires the eventual atomic join operation."""
        integer(current_level, 'resonance')
        return max(current_level, self.join_resonance_target)

    def resonance_after_claim(self, quest_id, current_level):
        """Target only: call after qualifying the original task, within its award TX."""
        integer(current_level, 'resonance')
        target = self.task(quest_id).resonance_target
        return current_level if target is None else max(current_level, target)

    def pporu_available(self, *, event_active, is_bound_character, completed):
        if type(event_active) is not bool or type(is_bound_character) is not bool:
            raise ValueError('Explicit activity and bound-role state required')
        count = self.completed_prefix(completed)
        return (not event_active or not is_bound_character
                or any(t.opens_pporu for t in self.tasks[:count]))


@lru_cache(maxsize=2)
def _original_definition(cls, raw):
    return cls._parse_original(raw)
