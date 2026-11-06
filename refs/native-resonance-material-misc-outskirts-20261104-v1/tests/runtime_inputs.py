import importlib.abc,importlib.util,json,sys
from pathlib import Path
W=Path(__file__).resolve().parent;R=Path('G:/els');BASE=R/json.loads((W/'parent.json').read_bytes())['path'];sys.path.insert(0,str(BASE))
if '--baseline'not in sys.argv:
 class Finder(importlib.abc.MetaPathFinder):
  def find_spec(self,fullname,path=None,target=None):
   source=W/'candidate'/Path(*fullname.split('.')).with_suffix('.py')
   if source.exists():return importlib.util.spec_from_file_location(fullname,source)
 sys.meta_path.insert(0,Finder())
