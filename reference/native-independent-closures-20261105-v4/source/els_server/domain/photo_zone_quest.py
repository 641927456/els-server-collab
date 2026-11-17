"""Bind ordinary studio task mutations to the selected character and scene."""
from els_server.domain.friend_flow import selected
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character

def capture(s):
    refs,values=selected(s);refs=refs[:-1]
    scene=(s.phase,s.active_map,s.pending_map,s.dungeon_run)
    if s.phase not in('town_ready','dungeon_active'):raise ValueError('Studio quest current scene')
    def same():
        try:current_refs,current_values=selected(s)
        except(ValueError,AttributeError,KeyError,TypeError):return False
        return(current_values==values and all(a is b for a,b in zip(refs,current_refs[:-1]))
            and(s.phase,s.active_map,s.pending_map,s.dungeon_run)==scene)
    def guard(db):
        if not same():raise ValueError('Studio quest selected actor or scene changed')
        require_owner(db,values[0],values[1]);require_active_character(db,values[0])
    return same,guard
