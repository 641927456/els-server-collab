"""Run only affected integration tests by default, or the full offline set."""
import json
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import bootstrap
from test_social_basics import WhisperRouting,BlacklistLifecycle
from test_friend_mail import MailFolders,FriendLifecycle
from test_guild_returns import ReturnedMail,GuildChat
from test_item_contracts import ItemContracts
from test_material_selection import MaterialSelection
from test_related_actors import RelatedActors
sys.path.insert(0,str(bootstrap.WORK/'source'/'tests'))
from test_mail_scope_current import MailScopeTests
from test_integration_review import ReviewWhisper,ReviewMailStatus,ReviewReturns

loader = unittest.defaultTestLoader
review = [ReviewWhisper('test_whisper_keeps_concurrent_recipient_message'),
          ReviewMailStatus('test_read_reward_with_same_unread_totals_sends_corrected_notice'),
          ReviewReturns('test_predeletion_claim_cannot_be_reclaimed_by_sibling')]
before = '--input-candidate' in sys.argv
if before:
    tests = unittest.TestSuite(review[:2])
elif '--full' in sys.argv:
    cases = (WhisperRouting,BlacklistLifecycle,MailFolders,FriendLifecycle,GuildChat,
             ReturnedMail,ItemContracts,MaterialSelection,RelatedActors,MailScopeTests)
    tests = unittest.TestSuite([loader.loadTestsFromTestCase(cls) for cls in cases]+review)
else:
    tests = unittest.TestSuite([loader.loadTestsFromTestCase(cls) for cls in
             (WhisperRouting,MailFolders,MailScopeTests)]+[
             ReturnedMail('test_historical_return_becomes_visible_without_rewriting_metadata'),*review])
previous = tempfile.tempdir
try:
    tempfile.tempdir = str(bootstrap.WORK)
    result = unittest.TextTestRunner(verbosity=1).run(tests)
finally:
    tempfile.tempdir = previous
report = dict(ok=result.wasSuccessful(),tests=result.testsRun,game_started=False,server_started=False,
              errors=[trace for _,trace in result.errors],failures=[trace for _,trace in result.failures])
name = 'review-input-tests.json' if before else 'review-tests.json'
path = bootstrap.WORK / name
attempt = 1
while path.exists():
    path = bootstrap.WORK / (name[:-5]+'-attempt-'+str(attempt)+'.json')
    attempt += 1
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
raise SystemExit(not report['ok'])
