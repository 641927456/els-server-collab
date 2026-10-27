"""Portable source/privacy/protocol checks; runtime validation is explicit."""

from pathlib import Path

import argparse,json,os,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]

sys.path.insert(0,str(ROOT))



def run(command):subprocess.run(command,cwd=ROOT,check=True)

def main(argv=None):

    parser=argparse.ArgumentParser();parser.add_argument('--with-runtime',action='store_true');args=parser.parse_args(argv)

    run([sys.executable,'-B',str(ROOT/'tools/repository_guard.py')])
    if (ROOT/'channels/reviewed-pr563-573-576-current-20261027-v1.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_reviewed_three_pr_binding_20261027.py')])
    if (ROOT/'channels/formal-clock-20261027-v1.json').is_file():
        for channel in ('online', 'local'):
            run([sys.executable,'-B',str(ROOT/'tools/materialize_formal_runtime.py'),
                 '--channel',channel,'--verify-only'])
        run([sys.executable,'-B','-m','unittest','tests.test_formal_materializer'])
    if (ROOT/'channels/server-latency-guards-20261027-v1.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_server_latency_guards.py')])
    if (ROOT/'channels/server-risk-remediation-20261027-v1.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_current_runtime_regressions.py')])
    if (ROOT/'channels/server-risk-current-20261027-v2.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_current_runtime_regressions.py'),
             '--manifest',str(ROOT/'channels/server-risk-current-20261027-v2.json'),
             '--delta',str(ROOT/'references/server-risk-current-20261027-v2/delta.json')])
    if (ROOT/'channels/server-risk-current-local-roles-20261027-v3.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_current_runtime_regressions.py'),
             '--manifest',str(ROOT/'channels/server-risk-current-local-roles-20261027-v3.json'),
             '--delta',str(ROOT/'references/local-auxiliary-role-binding-20261027-v1/delta.json')])


    if (ROOT/'references/background-native-gear-20261026-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_background_native_gear_archive.py')])
    if (ROOT/'references/accepted-runtime-20261026-v1/manifest.json').is_file():

        run([sys.executable,'-B',str(ROOT/'tools/verify_accepted_runtime_sources_20261026.py')])

    if (ROOT/'references/pr494-reviewed-runtime-delta-20261026-v1/manifest.json').is_file():

        run([sys.executable,'-B',str(ROOT/'tools/verify_pr494_runtime_delta.py')])

    if (ROOT/'references/memory2-lithia-native-completion-20261026-v1/manifest.json').is_file():

        run([sys.executable,'-B',str(ROOT/'tools/verify_memory2_lithia_runtime_delta.py')])

    if (ROOT/'references/black-market-native-completion-20261026-v1/manifest.json').is_file():

        run([sys.executable,'-B',str(ROOT/'tools/verify_black_market_sources_20261026.py')])

    if (ROOT/'references/f-chip-circuit-transfer-20261026-v1/manifest.json').is_file():

        run([sys.executable,'-B',str(ROOT/'tools/verify_F_chip_circuit_sources.py')])

    if any((ROOT/'references').glob('f-service-*-20261026-v1/manifest.json')):

        run([sys.executable,'-B',str(ROOT/'tools/verify_f_service_component_sources.py')])

    if any((ROOT/'references').glob('f-remaining-*-20261026-v1/manifest.json')):
        run([sys.executable,'-B',str(ROOT/'tools/verify_f_remaining_sources.py')])
    if (ROOT/'references/f-trade-board-native-20261026-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/check_trade_board_sources.py')])
        run([sys.executable,'-B','-m','unittest','tests.test_trade_board_reference'])
    if (ROOT/'references/early-role-eight-weapons-20261026-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_early_role_weapons_20261026.py')])
    if (ROOT/'references/ordinary-active-force-books-20261026-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_ordinary_active_force_books_20261026.py')])
    if (ROOT/'references/qualified-force-next8-20261026-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_qualified_force_next8_20261026.py')])
        run([sys.executable,'-B',str(ROOT/'tools/verify_qualified_force_next8_20261026.py'),'--channel','local'])
    run([sys.executable,'-B','-m','unittest','tests.test_native_hero_inputs',
         'tests.test_retained_native_hp.FinitePolicyFilesTests.test_all_four_payloads_match_their_manifests_and_client'])
    if (ROOT/'references/qualified-force-clock-20261026-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_qualified_force_clock_20261026.py')])
        run([sys.executable,'-B',str(ROOT/'tools/verify_qualified_force_clock_20261026.py'),'--channel','local'])
    if (ROOT/'references/native-two-permanent-tickets-20261027-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_native_permanent_tickets_20261027.py')])
        run([sys.executable,'-B',str(ROOT/'tools/verify_native_permanent_tickets_20261027.py'),'--channel','local'])
    if (ROOT/'references/native-rosso-reset-20261027-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_rosso_reset_20261027.py')])
        run([sys.executable,'-B',str(ROOT/'tools/verify_rosso_reset_20261027.py'),'--channel','local'])
    if (ROOT/'references/native-aurora-book-sources-20261027-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_aurora_book_sources_20261027.py')])
        run([sys.executable,'-B',str(ROOT/'tools/verify_aurora_book_sources_20261027.py'),'--channel','local'])
        run([sys.executable,'-B','-m','unittest','tests.test_295762_group_draw_guard'])
    if (ROOT/'references/native-change-force-materials-20261027-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_change_force_materials_20261027.py')])
        run([sys.executable,'-B',str(ROOT/'tools/verify_change_force_materials_20261027.py'),'--channel','local'])
    if (ROOT/'references/current-refresh-combat-inputs-20261027-v1/manifest.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_current_refresh_archive_20261027.py')])
    if (ROOT/'references/native-power-cache-sync-20261027-v1/candidate.json').is_file():
        run([sys.executable,'-B',str(ROOT/'tools/verify_native_power_cache_archive_20261027.py')])
        run([sys.executable,'-B','-m','unittest','tests.test_native_power_cache_contract'])
    names=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf8').split('\0')

    count=0

    for name in filter(None,names):

        if Path(name).suffix in ('.py','.pyw'):

            compile((ROOT/name).read_text(encoding='utf-8-sig'),name,'exec');count+=1

    from els_server.protocol.protocol_codec import Keys,Event,encode_event,decode_event,encode_frame,decode_frame

    keys=Keys(os.urandom(8),os.urandom(8))

    event=Event(0x202,kind=0x6eb,payload=bytes(range(33)))

    plaintext=encode_event(event)

    wire=encode_frame(plaintext,keys,spi=7,sequence=1)

    frame=decode_frame(wire,keys,expected_sequence=1)

    assert decode_event(frame.plaintext)==event

    if args.with_runtime:
        if (ROOT/'channels/server-latency-guards-20261027-v1.json').is_file():
            run([sys.executable,'-B',str(ROOT/'tools/verify_server_latency_guards.py'),'--with-runtime'])

        run([sys.executable,'-B','-m','els_server','--config','config/server.toml','--check'])

        run([sys.executable,'-B','-m','unittest','tests.test_retained_native_hp',
             'tests.test_current_native_title_inputs'])
        assert not (ROOT/'state/development.sqlite3').exists(),'CI must not create a player database'

    print(json.dumps(dict(ok=True,python_sources_compiled=count,protocol_roundtrip=True,runtime_check=args.with_runtime,no_owner_data=True)))



if __name__=='__main__':main()
