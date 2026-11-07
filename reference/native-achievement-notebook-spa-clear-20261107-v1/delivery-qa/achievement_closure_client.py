"""One shared scenario for private, selected, public and local acceptance."""
from achievement_notebook_client import scenario as notebooks
from achievement_spa_client import scenario as spa
from achievement_clear_client import scenario as clear

async def scenario(values,snapshot,report):
    await notebooks(values,snapshot,report)
    report['ok']=False;await spa(values,snapshot,report)
    report['ok']=False;await clear(values,snapshot,report)
    report.update(connected_source_types=45,connected_definitions=285,remaining_source_types=15,
        unresolved_original_reward_groups=53,new_tables=0,new_indexes=1,
        retained_Noah_rooms_spa_rooms_level_ED_and_owned_history_fixtures=True,
        natural_acquisition=False,native_Game=False,natural_GUI=False,production_clock_patch=False)
