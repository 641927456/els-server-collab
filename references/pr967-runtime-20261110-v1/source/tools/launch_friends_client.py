"""Compatibility name: all startup logic lives in launch_client."""
from launch_client import ClientLaunchError,verify_client,prepare_native_sources,compatibility_preflight,bridge_failure_message,_wait_owned_game_probe
import sys
def main(argv=None):
    from launch_client import main as shared_main
    return shared_main(['--mode','friends',*(sys.argv[1:]if argv is None else argv)])
if __name__=='__main__':
    try:raise SystemExit(main())
    except ClientLaunchError as error:print('ELS_LAUNCH_ERROR: '+str(error),flush=True);raise SystemExit(2)
