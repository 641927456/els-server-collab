"""One commit for every participant's reward receipt and phase progress."""
import sqlite3
from pathlib import Path
from contextlib import closing


def settle(members,event):
    from els_server.domain.local_session import LocalSession
    from els_server.domain.challenge_flow import notification
    paths={Path(m.account.store.path).resolve() for m in members}
    if len(paths)!=1:raise ValueError('Shared challenge requires one database')
    names=('reward_receipt','clear_items_synced','clear_notified','challenge_clear_effect')
    before={m:{name:getattr(m,name,None) for name in names} for m in members}
    deliveries=[]
    try:
        with closing(sqlite3.connect(next(iter(paths)),timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            for m in members:m.reward_transaction=db
            for m in members:
                # The outer handle() observes quest/pet events through their
                # own connections. Run those observers after this commit.
                messages=LocalSession._handle(m,event)
                if not m.clear_notified or m.reward_receipt is None:raise ValueError('Shared settlement did not produce a clear receipt')
                deliveries.append((m,[e for e in messages if e.kind not in (0xbc,0xae6)]))
    except BaseException:
        for m,values in before.items():
            for name,value in values.items():setattr(m,name,value)
        raise
    finally:
        for m in members:m.__dict__.pop('reward_transaction',None)
    # Read the committed phase only after all member effects have succeeded.
    result=[]
    from els_server.domain.quest_flow import observe
    from els_server.domain.pet_progression_flow import observe as observe_pet
    from els_server.domain.artifact_flow import observe as observe_artifact
    for m,messages in deliveries:
        result.append((m,[*messages,notification(m),*observe(m,messages),*observe_pet(m,messages),*observe_artifact(m,messages)]))
    return result
