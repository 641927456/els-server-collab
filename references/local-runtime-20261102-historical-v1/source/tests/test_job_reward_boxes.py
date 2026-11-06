"""Current job convenience boxes: native preview, exact timed contents, consent."""
import asyncio,struct,time
from tests import test_npc_sale as fixture
from tests.test_fixed_cubes import payload
from els_server.domain.cubes import catalog
from els_server.protocol.protocol_codec import Event
from els_server.storage.fixed_cubes import open_cube


BOXES = {300645: (300640,300643,190414), 300646: (300640,300644,183404,183405,183406,183407),
         300647: (300640,300643,190416), 300648: (300640,300644,190416,710132)}
QUANTITIES = {(300648,710132):30}
DAYS = {190414:7, 190416:1, 183404:15, 183405:15, 183406:15, 183407:15}


class JobRewardBoxTests(fixture.SaleTests):
 def session(self):
  from els_server.application import Application
  from els_server.config import ServerConfig
  app=Application(ServerConfig(state_file=self.path,log_dir=self.path.parent/'logs'))
  self.addCleanup(app.executor.shutdown,wait=True)
  app.account=self.account.root
  s=asyncio.run(app.session())
  s.role='game';s.phase='town_ready';s.completed.update((0x28,0x225,0x227))
  return s

 def preview(self,template):
  # 2353800: template, empty vector<int>, two mode bytes.
  return struct.pack('>iI',template,0)+bytes(2)

 def open(self,template,item,operation):
  return open_cube(self.path,1001,template,payload(item['uid']),operation,
      account_id=self.account.account_id,prepare=lambda db:None)

 def test_catalog_exposes_the_four_approved_boxes_without_a_choice(self):
  for template,outputs in BOXES.items():
   row=catalog()[template]
   self.assertIs(row['job_convenience'],True)
   self.assertEqual(row['selection_count'],0)
   self.assertEqual(tuple(e['template'] for e in row['entries']),outputs)
   self.assertEqual([e['quantity'] for e in row['entries']],
       [QUANTITIES.get((template,e['template']),1) for e in row['entries']])

 def test_preview_reports_exact_contents_and_refuses_a_foreign_envelope(self):
  self.grant(300645);s=self.session()
  reply=s.handle(Event(0x202,kind=0x559,payload=self.preview(300645)),1)[0]
  self.assertEqual(reply.kind,0x55a)
  self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,300645))
  self.assertEqual(struct.unpack_from('>i',reply.payload,13)[0],0)
  self.assertEqual(struct.unpack_from('>I',reply.payload,17)[0],3)
  self.assertEqual([struct.unpack_from('>i',reply.payload,21+12*i)[0] for i in range(3)],
      [300640,300643,190414])
  self.assertEqual(s.fixed_cube_preview_template,300645)
  before=self.dump()
  foreign=s.handle(Event(0x202,kind=0x559,uid=7,payload=self.preview(300645)),2)
  self.assertEqual(struct.unpack_from('>i',foreign[0].payload)[0],-1)
  self.assertEqual(self.dump(),before)

 def test_open_consumes_one_box_and_grants_the_exact_timed_contents(self):
  item=self.grant(300645);now=int(time.time())
  events=self.open(300645,item,'job-645')
  self.assertEqual([e.kind for e in events][-1],0x197)
  self.assertEqual(struct.unpack_from('>i',events[-1].payload)[0],0)
  self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
  for template in BOXES[300645]:
   self.assertEqual(sum(i['count'] for i in self.items() if i['template']==template),1)
  badge=next(i for i in self.items() if i['template']==190414)
  self.assertIn(badge['expires_at']-now,(DAYS[190414]*86400,DAYS[190414]*86400+1))
  self.assertNotIn('expires_at',next(i for i in self.items() if i['template']==300640))

 def test_retry_is_idempotent_and_second_turn_boxes_stay_timed(self):
  item=self.grant(300646);now=int(time.time())
  self.open(300646,item,'job-646');before=self.dump()
  retry=self.open(300646,item,'job-646')
  self.assertTrue(all(e.kind!=0xad8 for e in retry));self.assertEqual(self.dump(),before)
  for template in BOXES[300646]:
   self.assertEqual(sum(i['count'] for i in self.items() if i['template']==template),1)
  for template in (183404,183405,183406,183407):
   self.assertIn(next(i for i in self.items() if i['template']==template)['expires_at']-now,(15*86400,15*86400+1))

 def test_third_turn_box_stacks_the_approved_invitation(self):
  item=self.grant(300648)
  self.open(300648,item,'job-648')
  self.assertEqual(sum(i['count'] for i in self.items() if i['template']==710132),30)

 def test_client_selected_output_and_missing_box_preserve_the_save(self):
  item=self.grant(300647);before=self.dump()
  with self.assertRaises(ValueError):open_cube(self.path,1001,300647,payload(item['uid'],(300640,)),'job-choice',
      account_id=self.account.account_id,prepare=lambda db:None)
  self.assertEqual(self.dump(),before)
  with self.assertRaises(ValueError):open_cube(self.path,1001,300647,payload(item['uid']),'job-no-actor')
  self.assertEqual(self.dump(),before)


for _name in list(vars(fixture.SaleTests)):
    if _name.startswith('test_') and _name not in vars(JobRewardBoxTests):setattr(JobRewardBoxTests,_name,None)
