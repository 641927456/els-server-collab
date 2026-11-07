"""Actual authenticated frontend plus same-account game connection, own stores only."""
import runtime_fixture as h
import asyncio,json,time
from unittest.mock import patch
from els_server.periodic_work import next_poll_deadline
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False,tests=0)
 try:
  bridge=c.bridge(c.alice)
  frontend=await h.f.Peer.open(bridge);c.peers.append(frontend)
  await frontend.send(0x274,event_id=0x402);await frontend.until(0x275)
  game=await c.peer(c.alice);await game.roster()
  s=next(slot.session for slot in c.server.periodics.slots.values()if slot.session.identity['id']==c.alice['id']and slot.session.role=='frontend')
  await c.server.periodics.close()
  assert s.phase=='authenticated';await c.app.call(s.periodic_notifications)
  now=time.monotonic();due=next_poll_deadline(c.app,s,now)
  assert .8<due-now<=1.1,(due-now);out['tests']+=1
  with patch.object(s,'_periodic_pending',True):assert next_poll_deadline(c.app,s,now)==now
  out['tests']+=1
  s.mailbox.append(h.Event(0x201,kind=0x48f))
  assert next_poll_deadline(c.app,s,now)==now;s.mailbox.drain();out['tests']+=1
  with patch.object(s,'next_periodic',now-.1):assert next_poll_deadline(c.app,s,now)==now
  out['tests']+=1
  out.update(passed=True,actual_same_account_frontend_and_game=True,idle_delay_seconds=due-now,pending_slice_immediate=True,mailbox_immediate=True,overdue_immediate=True,source=h.bootstrap.SOURCE_BINDINGS)
 finally:
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  (h.H/'frontend-poll-deadline-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out));assert out['passed']and not out['errors']
asyncio.run(main())
