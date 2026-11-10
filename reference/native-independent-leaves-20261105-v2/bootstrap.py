from pathlib import Path
import os,sys
HERE=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_FULL_SOURCE']).resolve()
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(BASE/'vendor')]
import els_server,els_server.domain,els_server.storage,els_server.protocol
