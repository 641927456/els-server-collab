from pathlib import Path
import os,sys
HERE=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_FULL_SOURCE']).resolve()
assert(BASE/'els_server').is_dir()
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor')]
