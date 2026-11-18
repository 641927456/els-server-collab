"""Read accepted run facts; the original reward transaction owns title credit."""
from dataclasses import dataclass
from els_server.domain.dungeon_result_stats import current_statistics


@dataclass(frozen=True)
class ClearContext:
    owner: int
    dungeon: int
    run: str
    source_run: str
    players: int
    hits: object
    hits_by_npc: object

    def read(self,db,owner,dungeon,run):
        if (owner,dungeon,run)!=(self.owner,self.dungeon,self.run):
            raise ValueError('Title clear source owner/run changed')
        from els_server.storage.titles import exists
        used=0
        if exists(db,'known_resurrection_spends'):
            used=db.execute('SELECT COUNT(*) FROM known_resurrection_spends WHERE owner=? AND run=?',
                (owner,self.source_run)).fetchone()[0]
        return dict(players=self.players,hits=self.hits,hits_by_npc=self.hits_by_npc,resurrections=used)


def clear_context(session):
    supply=getattr(session,'_raid_supply',None) or getattr(session,'_pve_clear_supply',None)
    original=supply['original_session'] if supply is not None else session
    run=original.dungeon_run
    epoch=run.run_id if run is not None else original.reward_run_id
    stats=current_statistics(original)
    return ClearContext(original.account.uid,original.dungeon_id,original.reward_run_id,epoch,
        len(original.dungeon_participants),None if stats is None else stats['hit_count'],
        None if stats is None else dict(stats['hits_by_npc']))
