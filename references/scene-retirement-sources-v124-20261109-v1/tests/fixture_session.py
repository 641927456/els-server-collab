from types import SimpleNamespace as NS
OWNER=1001

def session(run,*,part_end_notified=True):
    root=NS(character_accounts={})
    account=NS(uid=OWNER,account_id=71,root=root,store=NS(uid=OWNER),
               character=lambda:{'unit_type':15,'level':70})
    s=NS(dungeon_run=run,account=account,role='game',phase='dungeon_active',
         identity={'id':71},released=False,dungeon_substage_synced=True,
         clear_notified=False,part_end_notified=part_end_notified,
         dungeon_participants=frozenset((OWNER,)),reward_run_id=run.run_id,reward_transaction=None,
         reward_test=False,item_test=False,drop_probe=False,summon_keys=set(),
         defeated_npcs=run.defeated,world_drops={},world_drop_sequence=0,
         dungeon_clock=NS(total=0,started=1,pause=lambda:None))
    root.character_accounts[OWNER]=account
    s.application=NS(playing={71:s},accounts={71:root})
    return s
