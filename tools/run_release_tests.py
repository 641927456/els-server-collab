"""Run server regressions separately from historical/manual capture acceptance."""
import contextlib,io,json,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
# These scripts are CLI validators for a caller-supplied capture, not unit tests.
MANUAL={'test_dungeon_actions','test_dungeon_acceptance','test_resource_sweep_acceptance'}
# Portable regressions run on the Windows server without a game installation,
# a captured process image, historical player saves or live client traces.
SERVER_MODULES='''acquisition_policy additional_potions attribute_enchant bag_capacity bag_ui_moves bank_money_memberships bank_state bank_view career_equipment careers challenge_flow challenge_state characters companions complex_dungeon_routes consumables decomposition dungeon_clock dungeon_routes dungeon_session dungeon_spawns ed_shop el_tree_loot_flow equipment_attributes equipment_durability equipment_eligibility equipment_enhancement equipment_moves equipment_repair_transaction equipment_repair equipment_requirements expansion_items expired_equipment fashion_bag_migration fashion_bundles fashion_inventory fashion_moves fixed_cubes friends_character_creation friends_server ground_loot inventory_actions inventory_management inventory_restore_and_drops inventory_rewards item_expiration job_shop_catalog launcher local_session local_state lock_decomposition_extension manufacture_messages manufacture_requirements ice_slot_reuse mount_flow mount_state normal_equipment npc_sale npc_trade owned_extension paid_enhancement persistent_endpoint pet_actions pet_progression pet_support population_cache potion_bag_migration potion_moves probe_commands profession_messages profession_state quick_slots region_quest_flow region_quests registration repair_discounts repair_pass result_messages reward_state role_ice role_progression saved_economy_initialization seal_level_flow seal_quests server_runtime session_clock session_inventory shared_bank shop_entry_protocol shop_purchase_protocol shop_supplements skill_expansion skill_state skill_unlocks summons transcendence_slots ui_layout updated_client_profile'''.split()
def main():
    output=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'release-tests.json'
    portable='--server' in sys.argv
    portable_modules={'test_'+n for n in SERVER_MODULES}|{'test_pet_progression','test_extended_shop'}
    loader=unittest.TestLoader();suite=unittest.TestSuite();modules=[]
    with output.with_suffix('.log').open('w',encoding='utf8') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        for file in sorted((ROOT/'tests').glob('test_*.py')):
            if file.stem in MANUAL:continue
            if portable and file.stem not in portable_modules:continue
            modules.append(file.stem);suite.addTests(loader.discover(str(ROOT/'tests'),pattern=file.name))
        result=unittest.TextTestRunner(stream=log,verbosity=1).run(suite)
    report=dict(ok=result.wasSuccessful(),tests_run=result.testsRun,modules=modules,portable_server_suite=portable,manual_capture_validators=sorted(MANUAL),skipped=[dict(test=t.id(),reason=r) for t,r in result.skipped],failures=[dict(test=t.id(),detail=d) for t,d in result.failures],errors=[dict(test=t.id(),detail=d) for t,d in result.errors])
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(ok=report['ok'],tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))))
    return not result.wasSuccessful()
if __name__=='__main__':raise SystemExit(main())
