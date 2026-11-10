import json
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from els_server.domain.artifact_progression import catalog
from els_server.domain.local_session import LocalAccount
from els_server.storage import artifact_spirit
from els_server.storage.artifact_socket_expansion import perform as expand
from els_server.storage.identification_ui import perform as identify
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.local_state import LocalState


class ArtifactSpiritReplayTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "game.sqlite3"
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.owner = self.account.uid
        self.target = self.grant(168603)
        wedge = self.grant(118207)
        identify(self.path, self.owner, 0x438, struct.pack(">QB Ii", self.target, 0, 0, 0), "identify")
        expand(self.path, self.owner, struct.pack(">QQ", wedge, self.target), "expand")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE reward_balances SET ed=1000000 WHERE uid=?", (self.owner,))

    def grant(self, template):
        definition = next(row for row in catalog()["definitions"] if row["template"] == template)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            return grant_items(db, [dict(template=template, quantity=1, group=definition["group"],
                                         metadata=definition["metadata"])], self.owner)[0]["uid"]

    def request(self, mode, value, operation, draw=lambda n: 0):
        packet = struct.pack(">QIiIiQBiB", self.target, 1, 18, 1, 0, value, 0, mode, 0)
        reply, = artifact_spirit.perform(self.path, self.owner, packet, operation, randbelow=draw, account_id=1)
        return reply.payload

    def test_selected_shard_retries_use_the_correct_preview_and_applied_option(self):
        shard = self.grant(713652)
        preview = self.request(9, shard, "preview")
        option, = struct.unpack(">i", preview[-4:])
        self.assertEqual(struct.unpack(">iiiIi", preview[-20:]), (9, option, 0, 1, option))
        self.assertEqual(self.request(9, shard, "preview", self.fail), preview)
        apply = self.request(10, option, "apply")
        next_shard = self.grant(713652)
        self.request(9, next_shard, "next")
        self.assertEqual(struct.unpack_from(">i", self.request(9, shard, "preview", self.fail))[0], 2005)
        self.assertEqual(self.request(10, option, "apply")[-20:], apply[-20:])
        with closing(sqlite3.connect(self.path)) as db:
            items = {row["uid"]: row for row in load_items(db, self.owner)}
            self.assertNotIn(shard, items)
            self.assertNotIn(next_shard, items)
            self.assertEqual(items[self.target]["option_groups"]["18"], [option])
            self.assertEqual(db.execute("SELECT ed FROM reward_balances WHERE uid=?", (self.owner,)).fetchone(),
                             (600000,))

    def test_saved_preview_from_before_update_can_still_be_applied(self):
        shard = self.grant(713652)
        option, = struct.unpack(">i", self.request(9, shard, "preview")[-4:])
        with closing(sqlite3.connect(self.path)) as db, db:
            metadata, = db.execute("SELECT policy_json FROM artifact_spirit_previews").fetchone()
            policy = json.loads(metadata)
            del policy["operation_id"]
            db.execute("UPDATE artifact_spirit_previews SET policy_json=?", (json.dumps(policy),))
        self.assertEqual(struct.unpack_from(">i", self.request(10, option, "apply"))[0], 0)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT ed FROM reward_balances WHERE uid=?", (self.owner,)).fetchone(),
                             (800000,))
