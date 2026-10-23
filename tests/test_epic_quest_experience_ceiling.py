"""Ordinary quest reward boundaries; controlled prerequisites, no player state."""
from contextlib import closing
from pathlib import Path
import json,sqlite3,tempfile,unittest

from els_server.domain.local_session import LocalAccount
from els_server.domain.seal_quests import quest_catalog,sequence
from els_server.game_data import client_data
from els_server.protocol import quest_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState,ensure


class EpicQuestExperienceCeilingTests(unittest.TestCase):
    def test_original_rewards_commit_at_ceiling_and_retry_without_another_delta(self):
        with tempfile.TemporaryDirectory(prefix='epic-xp-boundary-') as directory:
            path=Path(directory)/'private.sqlite3'
            LocalAccount(LocalState(path)).enable_characters()
            quest=quest_catalog().quest(24630)
            ceiling=min(2**31-1,client_data().thresholds[-1])
            for index,(start,delta) in enumerate(((ceiling-7,7),(ceiling,0),(2**31-1,0))):
                account=50000+index
                uid=Characters(path,account).create('XP'+str(index),1,'xp-owner-'+str(index))['uid']
                location=LocalState(path,uid).load()
                # Level and predecessor are explicit boundary fixtures.
                # Progress below still uses the original accepted clear event.
                with closing(sqlite3.connect(path)) as db,db:
                    ensure(db)
                    db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
                    db.execute('UPDATE reward_balances SET experience=? WHERE uid=?',(start,uid))
                    for parent in sequence(quest['QuestCondition']['m_vecBeforeQuestID']):
                        if parent:db.execute('INSERT INTO completed_quests VALUES (?,?,?,?)',(uid,parent,1,'{"fixture":true}'))
                state=QuestState(path,uid,account_id=account)
                state.action('accept',dict(quest=24630,npc=10025),'accept-'+str(index),lambda r:[])
                state.record('clear-'+str(index),dict(kind='clear',dungeon=35110,level=99),b'controlled-original-clear')
                request=dict(quest=24630,npc=0,choices=(),flags=(0,1,1,1,0))
                def encode(result):
                    event=wire.reward_ack(24630,result['character'],location,result['slots'],result['balances'],result['items'],result['updates'],completed_at=1)
                    encode_event(event)
                    return [event]
                def dump():
                    with closing(sqlite3.connect(path)) as db:return tuple(db.iterdump())
                def fail(result):
                    encode(result)
                    raise ValueError('precommit fixture failure')
                before=dump()
                with self.assertRaisesRegex(ValueError,'precommit fixture failure'):
                    state.action('claim',request,'rollback-'+str(index),fail)
                self.assertEqual(dump(),before)
                result=state.action('claim',request,'claim-'+str(index),encode)
                self.assertEqual(result['balances']['experience'],start+delta)
                self.assertEqual(result['balances']['ed'],quest['Reward']['m_iED'])
                with closing(sqlite3.connect(path)) as db:
                    saved=json.loads(db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=24630',(uid,)).fetchone()[0])
                    self.assertEqual(saved['experience'],delta)
                    self.assertEqual(saved['ep'],quest['Reward']['m_iEP'])
                before=dump()
                self.assertTrue(state.action('claim',request,'claim-'+str(index),encode)['replayed'])
                self.assertEqual(dump(),before)
                self.assertEqual(QuestState(path,uid,account_id=account).snapshot(),state.snapshot())


if __name__=='__main__':unittest.main()
