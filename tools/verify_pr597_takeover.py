"""Run PR597 counterexamples without changing accepted runtime sources."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.materialize_formal_runtime import load_manifest, materialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-runtime', action='store_true')
    parser.add_argument('--assets-root', type=Path,
                        default=Path(os.environ.get('ELS_PR597_ASSETS_ROOT', ROOT)))
    args = parser.parse_args()
    environment = dict(os.environ, ELS_PR597_TEST_TEMP_ROOT=str(ROOT.parent))
    if not args.with_runtime:
        subprocess.run([
            sys.executable, '-B', '-m', 'unittest',
            'tests.test_pr597_door_regression',
            'tests.test_pr597_source_contract',
            'tests.test_pr597_skill_book_regression.PR597FrozenSkillBookNegativeControl',
        ], cwd=ROOT, env=environment, check=True)
        print(json.dumps(dict(ok=True, portable_cases=11, runtime_tests=False)))
        return

    profile = load_manifest(ROOT / 'channels/current-engine.json', ROOT)
    with tempfile.TemporaryDirectory(prefix='pr597-book-views-', dir=ROOT.parent) as owned:
        owned = Path(owned).resolve()
        results = {}
        for channel in ('online', 'local'):
            view = owned / channel
            receipt = materialize(ROOT, profile, channel, view,
                                  assets_root=args.assets_root, link_assets=False)
            selected_environment = dict(environment, ELS_PR597_RUNTIME_ROOT=str(view),
                                        ELS_PR597_TEST_TEMP_ROOT=str(owned))
            subprocess.run([
                sys.executable, '-B', '-m', 'unittest',
                'tests.test_pr597_skill_book_regression.PR597SkillBookRegression',
            ], cwd=ROOT, env=selected_environment, check=True)
            results[channel] = dict(cases=3, source_files=receipt['source_files'],
                                    assets=receipt['asset_files'], asset_links=False)
        print(json.dumps(dict(ok=True, channels=results, runtime_cases=6,
                              private_temporary_SQL_only=True, production_actions=0)))


if __name__ == '__main__':
    main()
