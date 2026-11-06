"""魔纳特拉 (Devildom5) 35080/35090/35100/35110 副本流程.

四张图各自被一种“客户端在自己的场景里结束对象”的写法卡住:

* 35080 黄金城美朵拜茵的 hub (stage0 part0) 用 ``kind == 3`` 点名五个
  class-0 传送门标记 8827/8828/8829/8830/8832; 客户端只上报原生 flag-255
  退场, 通用战斗路径丢弃它, 条件永不满足。``NATIVE_EXPIRY_ROOMS`` 只钉死
  这个 hub; stage3 part2 的 8829 仍按标记处理, 不能提前结算。
* 35080 stage3 part0/part1 是文物馆的两个跳跃平台房间: 官方设定里屏障
  不可破坏, 五个/四个 8821 ``...TRAP1`` 从不被打死, 玩家踩对发光平台后
  8826 ``STAGE3_MANAGER`` 退场。所以这一间只等客户端自己的 0xb8 作为出口
  证明(portal_exit 行), 不要求任何击杀; part2 的 8829 仍按标记处理,
  真 BOSS 8811 必须死。
  stage1 part2/part4 的 8827、stage2 part1/part2 的 8828/8941、stage4 的
  8835/8836/8831/8839/8940 由 ``DUMMY_HOSTILE_SOURCES`` 从清场和 0xb8 豁免。
* 35090 钢铁城堡的 8853/8857/8868/8859/8861 与 35100 托尔塔斗技场的
  8877/8880/8882/8883 是 class-103 场景/演出标记。35100 的 stage1/stage2
  还有 ``[8874,8881]``/``[8873,8881]`` 的 fail 分支 (``kind 4``), 由
  ``exits`` 拒绝; 真 BOSS 8874/8873 由 ``combat`` 保留。
* 35110 猎人的藏身处 stage0/stage2 的 BOSS 由同点多个 actor 合成, 只有
  “心脏” 8901/8905 会上报死亡, 8902/8903 与 8906/8907 由
  ``BOSS_CORE_SOURCES`` 豁免; 8931/8933 是场景标记。

每一条都是钉死行: (identity, stage, part)、graph_sha、整行 source、脚本名
与清单 sha、class_id/is_npc。任何字段与当前图谱不一致就不放行。关闭对应
开关即回到上游的卡住行为。
"""
import json
import struct
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

from els_server.domain import dungeon_flow, dungeon_routes, local_dungeon_flow
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event

GOLDCASTLE, UNDERGROUND, ARENA, IRONWALL = 35080, 35090, 35100, 35110
DEVILLDOM5 = (GOLDCASTLE, UNDERGROUND, ARENA, IRONWALL)

# Every real combat actor the four routes still owe a death report for.
GOLDCASTLE_MOBS = {8810, 8811, 8812, 8813, 8814, 8815, 8816, 8817, 8818,
                   8819, 8820, 8821, 8822, 8823, 8824}
GOLDCASTLE_WAIVED = {8826, 8827, 8828, 8829, 8830, 8831, 8835, 8836, 8839,
                     8940, 8941}
UNDERGROUND_MOBS = {8841, 8843, 8844, 8845, 8846, 8847}
UNDERGROUND_MARKERS = (8853, 8857, 8868, 8859, 8861)
ARENA_MOBS = {8871, 8872, 8873, 8874, 8875, 8876}
IRONWALL_MOBS = {8901, 8904, 8905}


class FakeClock:
    def __init__(self):
        self.value = 100.0
        self.started = 0.0
        self.total = 0.0

    def __call__(self):
        return self.value

    def pause(self):
        self.started = None

    def resume(self):
        self.started = self.value

    def seconds(self):
        return 5


def portal_request(part):
    return Event(0x202, kind=0xb8, payload=struct.pack('>b', part))


def client_part_end(part):
    """The client's own 0xbb part-end request for the current part."""
    return Event(0x202, performers=(0,), kind=0xbb, payload=struct.pack('>b', part))


class Devildom5Dungeons(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.run = None
        self.session = None

    def enter(self, identity, stage, part):
        self.clock.value = 100.0
        self.run = dungeon_routes.DungeonRun(identity, str(uuid.uuid4()), clock=self.clock)
        self.run._load_stage(stage)
        self.run.part = part
        self.run.started_at = 0.0
        self.session = NS(dungeon_run=self.run,
                          account=NS(uid=1004, character=lambda: {'unit_type': 15}),
                          role='game', phase='dungeon_active', dungeon_substage_synced=True,
                          clear_notified=False, dungeon_failed=False, part_end_notified=False,
                          dungeon_clock=self.clock, dungeon_participants=frozenset((1004,)),
                          reward_run_id=self.run.run_id, reward_transaction=None,
                          challenge_deadline=None, drop_probe=False, world_drops={},
                          world_drop_sequence=0, gate_stage_loading=False, gate_stage=0,
                          previous_dungeon_part=None, summon_keys=set(), summon_deaths={},
                          summon_requests={}, summon_next_key=16,
                          defeated_npcs=self.run.defeated, application=None,
                          active_challenge=None, clear_items_synced=False)
        return self.run

    def live(self):
        return [n for n in self.run.current['npcs']
                if n['active'] and n.get('team', 1) != 0 and n['key'] not in self.run.defeated]

    def billable(self):
        """Live actors the room really owes a death report for."""
        return [n for n in self.live()
                if not local_dungeon_flow.dummy_hostile(self.run, n)
                and not local_dungeon_flow.part_marker_npc(self.run, n)
                and not local_dungeon_flow.boss_core(self.run, n)]

    def kill(self, npc):
        self.run.defeated[npc['key']] = b'\0'

    def ready(self):
        """Arm the source condition (fixes ``ready_at``), then let its delay elapse."""
        self.run.poll_ready()
        self.clock.value += 200
        return self.run.poll_ready()

    def actor(self, template):
        return next(n for n in self.run.current['npcs'] if n['template'] == template)

    def expiry(self, npc, **kw):
        from test_lithia_memory8_offfield_expiry import native255
        kw.setdefault('owner', 1004)
        return Event(0x202, performers=(0,), kind=0xad,
                     payload=native255(npc['key'], npc['hp'], **kw))

    def back8(self):
        """The client's own 0xb8 part request; returns the i32 result payload."""
        reply = dungeon_flow.handle(self.session, portal_request(self.run.part))
        self.assertEqual(reply[0].kind, 0xb9)
        return struct.unpack('>i', reply[0].payload)[0]

    def declared(self, stage, part):
        return [n for group in self.run.graph['stages'][str(stage)]['parts'][str(part)]['groups']
                for n in group['npcs']]

    def assert_no_declared_row_drifts(self, declared, source_row):
        hits = [n for n in declared if n.get('template') == source_row['template']
                and n.get('source_index') == source_row['source_index']]
        self.assertTrue(hits)
        for hit in hits:
            self.assertTrue(all(hit.get(k) == v for k, v in source_row.items()))

    # -- 1: every pinned row must describe its graph exactly ----------------
    def test_pinned_rows_match_declared_sources(self):
        catalog = dungeon_routes.route_catalog()

        markers = [(key, row) for key, row in local_dungeon_flow.PART_MARKERS.items()
                   if key[0] in DEVILLDOM5]
        self.assertEqual(len(markers), 15)
        for (identity, stage, part), row in markers:
            with self.subTest(kind='part_marker', dungeon=identity, stage=stage, part=part):
                self.enter(identity, stage, part)
                self.assertEqual(self.run.graph['source_sha256'], row['graph_sha'])
                declared = self.declared(stage, part)
                exits = tuple(row.get('exits') or row['required'])
                self.assertTrue(set(row['required']) <= set(exits))
                if identity == ARENA and (stage, part) in ((1, 0), (2, 0)):
                    # 两行都只放行成功分支, fail 分支的 8881 不在 exits 里.
                    self.assertEqual(exits, tuple(row['required']))
                    self.assertEqual(row['combat'], (8874 if stage == 1 else 8873,))
                for marker in row['markers']:
                    source = marker['source']
                    native = client_data().npc(source['template'])
                    self.assertEqual(native['class_id'], marker.get('class_id', 103))
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(native['script'], marker['script'])
                    self.assertEqual(catalog.manifest['source_sha256'][marker['script']],
                                     marker['script_sha'])
                    if identity == GOLDCASTLE and stage == 3:
                        # 35080 stage3 三行必须显式声明 class-0 标记.
                        self.assertEqual(marker['class_id'], 0)
                    self.assert_no_declared_row_drifts(declared, source)

        dummies = [(key, row) for key, row in local_dungeon_flow.DUMMY_HOSTILES.items()
                   if key[0] in DEVILLDOM5]
        self.assertEqual(len(dummies), 5)
        for (identity, stage, part), row in dummies:
            with self.subTest(kind='dummy_hostile', dungeon=identity, stage=stage, part=part):
                self.enter(identity, stage, part)
                self.assertEqual(self.run.graph['source_sha256'], row['graph_sha'])
                declared = self.declared(stage, part)
                for pinned in row['sources']:
                    source = pinned['source']
                    native = client_data().npc(source['template'])
                    self.assertEqual(native['class_id'], pinned['class_id'])
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(native['script'], pinned['script'])
                    self.assertEqual(catalog.manifest['source_sha256'][pinned['script']],
                                     pinned['script_sha'])
                    self.assert_no_declared_row_drifts(declared, source)

        cores = [row for row in local_dungeon_flow.BOSS_CORE_SOURCES
                 if row['identity'] in DEVILLDOM5]
        self.assertEqual(len(cores), 2)
        for row in cores:
            identity, stage, part = row['identity'], row['stage'], row['part']
            with self.subTest(kind='boss_core', dungeon=identity, stage=stage, part=part):
                self.enter(identity, stage, part)
                self.assertEqual(self.run.graph['source_sha256'], row['graph_sha'])
                declared = self.declared(stage, part)
                heart = row['heart']
                source = heart['source']
                native = client_data().npc(source['template'])
                self.assertEqual(native['class_id'], heart['class_id'])
                self.assertIs(native['is_npc'], True)
                self.assertEqual(native['script'], heart['script'])
                self.assertEqual(catalog.manifest['source_sha256'][heart['script']],
                                 heart['script_sha'])
                self.assert_no_declared_row_drifts(declared, source)
                self.assertEqual(row['body'], (8902, 8903) if stage == 0 else (8906, 8907))

        expiry = [(key, row) for key, row in local_dungeon_flow.NATIVE_EXPIRY_ROOMS.items()
                  if key[0] in DEVILLDOM5]
        self.assertEqual(len(expiry), 1)
        for (identity, stage, part), row in expiry:
            with self.subTest(kind='native_expiry', dungeon=identity, stage=stage, part=part):
                self.enter(identity, stage, part)
                self.assertEqual(self.run.graph['source_sha256'], row['graph_sha'])
                self.assertEqual(len(row['scripts']), 5)
                declared = self.declared(stage, part)
                for template, (script, script_sha) in row['scripts'].items():
                    native = client_data().npc(template)
                    self.assertEqual(native['script'], script)
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(catalog.manifest['source_sha256'][script], script_sha)
                    hits = [n for n in declared if n['template'] == template]
                    self.assertTrue(hits)
                    for hit in hits:
                        self.assertTrue(hit['active'])
                        self.assertFalse(hit['boss'])

    # -- 2: the goldcastle hub retires its doors through flag 255 ----------
    def test_goldcastle_hub_retirement(self):
        for index, template, wing in ((0, 8827, 1), (1, 8828, 2), (2, 8829, 3),
                                      (3, 8832, 4)):
            with self.subTest(portal=template):
                self.enter(GOLDCASTLE, 0, 0)
                npc = self.actor(template)
                event = self.expiry(npc)
                replies = dungeon_flow.handle(self.session, event)
                self.assertEqual([r.kind for r in replies][:1], [0xae])
                self.assertEqual(self.run.defeated[npc['key']], event.payload)
                self.assertFalse(npc['active'])
                condition = self.run.current['conditions'][index]
                if template != 8832:
                    self.assertTrue(self.run.condition_ready(condition))
                    self.assertTrue(self.ready())
                    self.assertEqual((self.run.next['stage'], self.run.next['part']),
                                     (wing, 0))
                    continue
                # 三翼未集齐: 8832 的死已记录, 但 gold_castle 门控拒绝 BOSS 目标.
                self.assertFalse(self.run.condition_ready(condition))
                self.assertFalse(self.ready())
                self.assertIsNone(self.run.next)
                self.run.completed_stages = {1, 2, 3}
                self.assertTrue(self.run.condition_ready(condition))
                self.assertTrue(self.ready())
                self.assertEqual(self.run.next['stage'], 4)

    # -- 3: hub <-> wings <-> boss, without touching a waived row ----------
    def test_goldcastle_walk(self):
        self.enter(GOLDCASTLE, 0, 0)
        visited = []
        killed = []
        verdict = None
        for _ in range(40):
            self.run.loaded()
            visited.append((self.run.stage, self.run.part))
            if self.run.stage == 0:
                # hub: 四个门都由原生退场报告关闭, 不杀任何 actor.
                for template in (8827, 8828, 8829, 8832):
                    npc = next((n for n in self.run.current['npcs']
                                if n['template'] == template), None)
                    if npc is None or not npc['active']:
                        continue
                    replies = dungeon_flow.handle(self.session, self.expiry(npc))
                    self.assertEqual([r.kind for r in replies][:1], [0xae])
                    self.assertIn(npc['key'], self.run.defeated)
            else:
                for npc in self.billable():
                    self.kill(npc)
                    killed.append(npc['template'])
                if (self.run.stage, self.run.part) in ((3, 0), (3, 1)):
                    # 文物馆: 全体演员都是标记, 进门不能自动结算; 本 build 这里
                    # 从不发 0xb8, 客户端自己的换段请求才是可用的出口证明.
                    self.assertFalse(self.run.poll_ready())
                    # 新段开始时服务器还没有宣告本段结束.
                    self.session.part_end_notified = False
                    self.assertEqual(dungeon_flow.handle(self.session,
                                                         client_part_end(self.run.part)),
                                     [])
                    self.assertTrue(self.run.poll_ready())
                if (self.run.stage, self.run.part) == (4, 0):
                    exempt = [n for n in self.run.current['npcs']
                              if n['template'] in (8835, 8836, 8831, 8839, 8940)]
                    self.assertEqual(len(exempt), 5)
                    self.assertTrue(all(n['active'] and n['key'] not in self.run.defeated
                                        for n in exempt))
                    # 豁免行都还活着, 0xb8 仍必须通过.
                    self.assertEqual(self.back8(), 0)
            self.assertTrue(self.ready(), 'part %r never satisfies its condition'
                            % (visited[-1],))
            if self.run.next['kind'] == 4:
                verdict = self.run.advance()
                break
            self.run.advance()
        else:
            self.fail('run never settled')
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited,
                         [(0, 0), (1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (0, 0),
                          (2, 0), (2, 1), (2, 2), (0, 0), (3, 0), (3, 1), (3, 2),
                          (0, 0), (4, 0)])
        # 8821 是文物馆不可破坏的陷阱, 只存在于 stage3 part0/part1.
        self.assertEqual(set(killed), GOLDCASTLE_MOBS - {8821})
        self.assertEqual(set(killed) & GOLDCASTLE_WAIVED, set())

    # -- 3b: 文物馆两条出口证明各自可用, 且都不跨段残留 --------------------
    def test_goldcastle_puzzle_room_exit_proofs(self):
        for part in (0, 1):
            with self.subTest(proof='client_0xb8', part=part):
                # 证明一: 客户端在出口发来的 0xb8. 整间演员都是标记, 所以这条
                # 走的是 part_marker_npc 豁免, 但门仍然只能靠玩家走到出口.
                self.enter(GOLDCASTLE, 3, part)
                self.run.loaded()
                self.assertFalse(self.run.poll_ready(), 'entering the room must not settle it')
                self.assertEqual(self.back8(), 0)
                self.assertTrue(self.run.portal_requested)
                self.assertTrue(self.run.poll_ready())

            with self.subTest(proof='client_0xbb', part=part):
                # 证明二: 本 build 这里从不发 0xb8, 客户端自己的换段请求也可作证.
                self.enter(GOLDCASTLE, 3, part)
                self.run.loaded()
                self.session.part_end_notified = False
                self.assertFalse(self.run.poll_ready())
                self.assertEqual(dungeon_flow.handle(self.session,
                                                     client_part_end(part)), [])
                self.assertTrue(local_dungeon_flow.portal_exit_settled(self.run))
                self.assertTrue(self.run.poll_ready())

        # 官方解谜路径: 踩对发光平台后 8826 STAGE3_MANAGER 原生退场, 这一段
        # 直接满足, 服务端这才宣告本段结束 (0xba), 客户端才有 0xbb 可发.
        for part in (0, 1):
            with self.subTest(proof='manager_retirement', part=part):
                self.enter(GOLDCASTLE, 3, part)
                self.run.loaded()
                npc = self.actor(8826)
                replies = dungeon_flow.handle(self.session, self.expiry(npc))
                self.assertEqual([r.kind for r in replies][:1], [0xae])
                self.assertIn(npc['key'], self.run.defeated)
                self.assertTrue(self.run.poll_ready())
                self.session.part_end_notified = False
                notices = dungeon_flow.periodic(self.session)
                self.assertEqual([r.kind for r in notices], [0xba])
                self.assertTrue(self.session.part_end_notified)

        # 证明按段键控: part0 留下来的 0xbb 不能替 part1 结算.
        self.enter(GOLDCASTLE, 3, 0)
        self.run.loaded()
        self.session.part_end_notified = False
        self.assertEqual(dungeon_flow.handle(self.session, client_part_end(0)), [])
        self.assertTrue(local_dungeon_flow.portal_exit_settled(self.run))
        self.run.advance()
        self.run.loaded()
        self.assertEqual((self.run.stage, self.run.part), (3, 1))
        self.assertFalse(local_dungeon_flow.portal_exit_settled(self.run))
        self.assertFalse(self.run.poll_ready())

    # -- 4: 35090, the five scene markers stay alive the whole run ---------
    def test_underground_walk(self):
        self.enter(UNDERGROUND, 0, 0)
        visited = []
        killed = []
        verdict = None
        for _ in range(40):
            self.run.loaded()
            visited.append((self.run.stage, self.run.part))
            billable = self.billable()
            if (self.run.stage, self.run.part) == (0, 0):
                # 同房的 8845/8846/8847 真怪全杀.
                self.assertTrue({8845, 8846, 8847} <= {n['template'] for n in billable})
            if (self.run.stage, self.run.part) == (1, 0):
                self.assertIn(8844, {n['template'] for n in billable})
            for npc in billable:
                self.kill(npc)
                killed.append(npc['template'])
            for npc in self.run.current['npcs']:
                if npc['template'] in UNDERGROUND_MARKERS and npc['active']:
                    self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, npc))
                    self.assertNotIn(npc['key'], self.run.defeated)
            self.assertTrue(self.ready(), 'part %r never satisfies its condition'
                            % (visited[-1],))
            if self.run.next['kind'] == 4:
                verdict = self.run.advance()
                break
            self.run.advance()
        else:
            self.fail('run never settled')
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited,
                         [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (1, 3),
                          (2, 0), (2, 1), (2, 2), (3, 0)])
        self.assertEqual(set(killed), UNDERGROUND_MOBS)

    # -- 5: 35100, the fail branches may never open -------------------------
    def test_arena_walk(self):
        self.enter(ARENA, 0, 0)
        visited = []
        killed = []
        verdict = None
        for _ in range(40):
            self.run.loaded()
            visited.append((self.run.stage, self.run.part))
            conditions = self.run.current['conditions']
            if visited[-1] == (0, 1):
                # 触发标记房: 唯一 actor 8877 被豁免, 进入即满足.
                self.assertEqual(self.billable(), [])
                self.assertTrue(self.run.condition_ready(conditions[0]))
            if visited[-1] in ((1, 0), (2, 0)):
                boss, fail = (8874, 8881) if visited[-1] == (1, 0) else (8873, 8881)
                self.assertEqual(conditions[0]['kind'], 3)
                self.assertEqual(set(conditions[0]['required']), {boss, fail})
                self.assertEqual([t['kind'] for t in conditions[0]['next']], [4])
                self.assertEqual(conditions[1]['kind'], 3)
                self.assertEqual(set(conditions[1]['required']), {boss, 8880})
                self.assertFalse(self.run.condition_ready(conditions[0]))
                self.assertFalse(self.run.condition_ready(conditions[1]))
            for npc in self.billable():
                self.kill(npc)
                killed.append(npc['template'])
            if visited[-1] in ((1, 0), (2, 0)):
                # fail 分支即使 BOSS 死了也永不满足; 成功分支此时放行.
                self.assertFalse(self.run.condition_ready(conditions[0]))
                self.assertTrue(self.run.condition_ready(conditions[1]))
            self.assertTrue(self.ready(), 'part %r never satisfies its condition'
                            % (visited[-1],))
            if self.run.next['kind'] == 4:
                verdict = self.run.advance()
                break
            self.run.advance()
        else:
            self.fail('run never settled')
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (0, 1), (1, 0), (2, 0), (3, 0), (4, 0)])
        self.assertEqual(set(killed), ARENA_MOBS)

    # -- 6: 35110, only the heart of a composed boss has to die -------------
    def test_ironwall_walk(self):
        self.enter(IRONWALL, 0, 0)
        visited = []
        killed = []
        verdict = None
        for _ in range(40):
            self.run.loaded()
            visited.append((self.run.stage, self.run.part))
            point = visited[-1]
            billable = self.billable()
            self.assertEqual([n['template'] for n in billable],
                             {(0, 0): [8901], (1, 0): [8904], (2, 0): [8905]}[point])
            if point == (0, 0):
                # 8902 LEG / 8903 CANNON 从头到尾都不上报, 只豁免不杀.
                self.assertTrue(all(n['active'] and n['key'] not in self.run.defeated
                                    for n in self.run.current['npcs']
                                    if n['template'] in (8902, 8903)))
            if point == (2, 0):
                self.assertTrue(all(n['active'] and n['key'] not in self.run.defeated
                                    for n in self.run.current['npcs']
                                    if n['template'] in (8906, 8907)))
            for npc in billable:
                self.kill(npc)
                killed.append(npc['template'])
            if point in ((0, 0), (2, 0)):
                # 手脚还活着, 0xb8 仍必须通过.
                self.assertEqual(self.back8(), 0)
            self.assertTrue(self.ready(), 'part %r never satisfies its condition' % (point,))
            if self.run.next['kind'] == 4:
                verdict = self.run.advance()
                break
            self.run.advance()
        else:
            self.fail('run never settled')
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (1, 0), (2, 0)])
        self.assertEqual(set(killed), IRONWALL_MOBS)

    # -- 7: switching any one waiver off restores the upstream stall --------
    def test_switch_off_still_stuck(self):
        # 35090 stage0 part0: 8853 是 kind==3 的唯一 required.
        self.enter(UNDERGROUND, 0, 0)
        for npc in self.billable():
            self.kill(npc)
        with patch.object(local_dungeon_flow, 'part_marker_relaxation', lambda: False):
            self.assertFalse(any(self.run.condition_ready(c)
                                 for c in self.run.current['conditions']))
            self.assertFalse(self.ready())
        self.assertTrue(self.ready())

        # 35080 stage1 part2: class-0 8827 是 kind==0 清场里的场景替身.
        self.enter(GOLDCASTLE, 1, 2)
        for npc in self.billable():
            self.kill(npc)
        with patch.object(local_dungeon_flow, 'dummy_hostile_relaxation', lambda: False):
            self.assertFalse(self.ready())
        self.assertTrue(self.ready())

        # 35110 stage2 part0: 只杀心脏 8905, 手脚由 BOSS_CORE 豁免.
        self.enter(IRONWALL, 2, 0)
        self.kill(self.actor(8905))
        with patch.object(local_dungeon_flow, 'boss_core_relaxation', lambda: False):
            self.assertFalse(any(self.run.condition_ready(c)
                                 for c in self.run.current['conditions']))
            self.assertFalse(self.ready())
        self.assertTrue(self.ready())

        # 35080 stage3 part0 (文物馆): 只认客户端 0xb8, 开关关掉后必须仍然卡住,
        # 不能退回"进门即结算".
        self.enter(GOLDCASTLE, 3, 0)
        with patch.object(local_dungeon_flow, 'portal_exit_relaxation', lambda: False):
            self.assertEqual(self.back8(), 0)
            self.assertFalse(any(self.run.condition_ready(c)
                                 for c in self.run.current['conditions']))
            self.assertFalse(self.run.poll_ready())
        self.assertTrue(self.ready())

        # 35080 hub: 原生 flag-255 退场必须由开关放行.
        self.enter(GOLDCASTLE, 0, 0)
        npc = self.actor(8827)
        event = self.expiry(npc)
        with patch.object(local_dungeon_flow, 'native_expiry_relaxation', lambda: False):
            self.assertEqual(dungeon_flow.handle(self.session, event), [])
            self.assertEqual(self.run.defeated, {})
            self.assertTrue(npc['active'])
            self.assertFalse(self.ready())
        self.assertEqual([r.kind for r in dungeon_flow.handle(self.session, event)][:1],
                         [0xae])
        self.assertEqual(self.run.defeated[npc['key']], event.payload)
        self.assertTrue(self.ready())

    # -- 8: the read-only audit mirrors the declared part exactly ----------
    def test_part_audit_matches_declared_points(self):
        self.enter(GOLDCASTLE, 1, 0)
        self.assertEqual(sorted(self.run.part_audit), sorted(self.run.parts))
        for part, part_row in self.run.parts.items():
            rows = dungeon_flow.part_audit_rows(self.run, part)
            self.assertEqual([(r['key'], r['template'], r['point'], r['active'])
                              for r in rows],
                             [(n['key'], n['template'], n['start_point'], bool(n['active']))
                              for n in part_row['npcs']])
        path = Path(tempfile.mkdtemp()) / 'audit.jsonl'
        with patch.object(dungeon_flow, 'PART_AUDIT_PATH', path), \
                patch.object(dungeon_flow, 'part_audit_lines', None):
            # 0xb3 首次同步就是其中一个下发点, 必须落一行当前 part.
            self.session.dungeon_substage_synced = False
            reply = dungeon_flow.handle(self.session, Event(
                0x202, kind=0xb3, payload=bytes(5) + struct.pack('>f', 0.0)))
            self.assertEqual([r.kind for r in reply][:4], [0xb4, 0xb5, 0xb6, 0xb7])
            self.assertTrue(self.session.dungeon_substage_synced)
            record = json.loads(path.read_text(encoding='utf8').splitlines()[-1])
        self.assertEqual((record['dungeon'], record['stage'], record['part'], record['run_id']),
                         (GOLDCASTLE, self.run.stage, self.run.part, self.run.run_id))
        npcs = self.run.parts[self.run.part]['npcs']
        self.assertEqual([(r['key'], r['template'], r['point'], r['active'])
                          for r in record['rows']],
                         [(n['key'], n['template'], n['start_point'], bool(n['active']))
                          for n in npcs])

    # -- 9: the switch only controls the file, never a packet --------------
    def test_part_audit_switch_off_is_silent(self):
        self.assertEqual((dungeon_flow.PART_AUDIT_LIMIT, dungeon_flow.PART_AUDIT_BYTES),
                         (512, 16384))
        self.enter(GOLDCASTLE, 1, 0)
        path = Path(tempfile.mkdtemp()) / 'audit.jsonl'
        with patch.object(dungeon_flow, 'PART_AUDIT_PATH', path), \
                patch.object(dungeon_flow, 'part_audit_lines', None):
            dungeon_flow.write_part_audit(self.session, 0)
            before = path.read_text(encoding='utf8')
            self.assertEqual(len(before.splitlines()), 1)
        off = dict(local_dungeon_flow.rules())
        off['part_audit'] = False
        with patch.object(local_dungeon_flow, 'rules', lambda: off), \
                patch.object(dungeon_flow, 'PART_AUDIT_PATH', path), \
                patch.object(dungeon_flow, 'part_audit_lines', None):
            dungeon_flow.write_part_audit(self.session, 1)
            self.assertEqual(path.read_text(encoding='utf8'), before)
        with patch.object(dungeon_flow, 'PART_AUDIT_PATH', path), \
                patch.object(dungeon_flow, 'part_audit_lines', 512):
            dungeon_flow.write_part_audit(self.session, 2)
            self.assertEqual(path.read_text(encoding='utf8'), before)


if __name__ == '__main__':
    unittest.main()
