import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from els_server.periodic_scheduler import PeriodicScheduler
from els_server.dungeon_workers import DungeonWorkers
from els_server.periodic_work import periodic_chunks

class Queue:
    async def run(self, work, *, timing):
        return work()

class Workers:
    run_upkeep = DungeonWorkers.run_upkeep
    release_upkeep = DungeonWorkers.release_upkeep
    def __init__(self):
        self.upkeep_admission = asyncio.Semaphore(1)
        self.upkeep_queue = self.town_upkeep_queue = Queue()
        self.upkeep_available = None
    def key(self, session):
        return ('party', 1)
    def candidate(self, function, args):
        return True
    def town_periodic(self, function, args):
        return False
    def town_mailbox(self, function, args):
        session = function.__self__
        session.checks += 1
        return session.name == 'A' and session.checks <= 2
    def upkeep_admission_for(self, session):
        return self.upkeep_admission
    def publish(self, *args, **kwargs):
        pass

class Session:
    def __init__(self, name):
        self.name = name
        self.checks = 0
    def periodic_notifications(self):
        return [self.name]

async def verify():
    workers = Workers()
    calls = []
    delivered = []
    def run(work, args, options, submitted, *, queue_timing):
        calls.extend(work())
        return calls[-1:]
    application = SimpleNamespace(dungeon_workers=workers, performance=SimpleNamespace(due=lambda:None), _worker_call=run)
    application.periodic_chunks = lambda *args, **kw: periodic_chunks(application, *args, **kw)
    scheduler = PeriodicScheduler(application, .01, lambda *a, **kw:None)
    ready = asyncio.Event()
    async def send(messages):
        delivered.extend(messages)
        if len(delivered) == 2:
            ready.set()
    sessions = [Session('A'),Session('B')]
    listeners = [asyncio.create_task(scheduler.serve(s,asyncio.Lock(),send)) for s in sessions]
    await asyncio.sleep(0)
    try:
        await asyncio.wait_for(ready.wait(),.5)
    except TimeoutError:
        assert not calls and all(s.claim is not None and s.finished is not None for s in scheduler.slots.values())
        assert workers.upkeep_admission.locked() and len(scheduler.polls) == 1
        print('REPRODUCED: mailbox -> upkeep waits for the same party poll second member')
        for slot in scheduler.slots.values():
            if slot.claim.upkeep_reserved:
                slot.claim.upkeep_reserved=False
                workers.release_upkeep(workers.upkeep_admission)
    else:
        assert calls == delivered == ['B','A'], (calls,delivered)
        print('FIXED: both original replies delivered once, reserved member runs first')
    finally:
        for task in listeners:
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*listeners,return_exceptions=True),1)
        await asyncio.wait_for(scheduler.close(),1)
    assert not scheduler.polls and not scheduler.deliveries and not workers.upkeep_admission.locked()
    print('Both connection retirements and scheduler shutdown finished; upkeep permit returned')

asyncio.run(verify())
