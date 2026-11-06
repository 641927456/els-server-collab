"""0x460 的应答不能回 result=-1：客户端错误表取空文字，屏幕上就是一个只有「确认」的白框。

原生客户端在副本里每 30 秒发一次这条请求，实测线包 96 字节（载荷 25~32 字节），
比 `boosting_2026_essence.request()` 认的 22 字节宽一截。修之前每次都走
`essence_ack(result=-1)`，于是每 30 秒弹一个空白确认框。
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest

from els_server.domain import boosting_2026_essence as essence_wire
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState


def native_payload(size):
    """0x460 的载荷：实测宽 25~32 字节，内容不影响这条测试。"""
    return bytes(size)


class EssenceRequestShapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'save.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        uid = self.account.characters.create('EssenceOther', 5, 'other')['uid']
        self.account.for_character(uid)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=1000')
        self.session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
            npc_slot_test=True, gate_test=True, population_test=True, clear_test=True,
            reward_test=True, item_test=True, shop_test=True, client_build='dx11_260923')
        self.session.role, self.session.phase = 'game', 'dungeon_active'

    def deliver(self, payload, sequence=7):
        return self.session.handle(Event(0x202, performers=(0,), kind=0x460, payload=payload), sequence)

    def result(self, reply):
        """应答里的 result 就是要喂给客户端错误表的那个整数。"""
        self.assertEqual([e.kind for e in reply], [0x461])
        return struct.unpack_from('>i', reply[0].payload)[0]

    def test_the_stored_twenty_two_byte_shape_is_the_only_one_accepted(self):
        # 22 字节、且 skill>0 才算合法；原生客户端从来不发这个长度。
        good = struct.pack('>BBii3f', 0, 0, 0, 5, 0.0, 0.0, 0.0)
        self.assertEqual(len(good), 22)
        self.assertEqual(essence_wire.request(good), 5)
        for size in (25, 26, 30, 32):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    essence_wire.request(native_payload(size))

    def test_a_wide_native_request_never_answers_with_an_error_code(self):
        # -1 就是那个空白确认框的开关；修完之后必须是 0 且没有库存变更。
        for size in (25, 26, 30, 32):
            with self.subTest(size=size):
                reply = self.deliver(native_payload(size))
                self.assertEqual(self.result(reply), 0)
                self.assertEqual(struct.unpack_from('>I', reply[0].payload, 4)[0], 0)
                self.assertEqual(self.session.essence_rejection[0], size)
                self.assertIn('Essence request size', self.session.essence_rejection[1])

    def test_the_same_request_outside_a_dungeon_is_answered_quietly(self):
        self.session.phase = 'town_ready'
        reply = self.deliver(native_payload(26))
        self.assertEqual(self.result(reply), 0)
        self.assertEqual(self.session.essence_rejection, (26, 'phase town_ready'))


if __name__ == '__main__':
    unittest.main()
