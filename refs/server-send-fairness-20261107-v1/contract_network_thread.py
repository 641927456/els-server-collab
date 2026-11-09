import ast
SETUP="""kernel.GetCurrentThread.restype=ctypes.c_void_p
kernel.SetThreadPriority.argtypes=[ctypes.c_void_p,ctypes.c_int]
kernel.SetThreadPriority.restype=ctypes.c_int
kernel.GetThreadPriority.argtypes=[ctypes.c_void_p]
kernel.GetThreadPriority.restype=ctypes.c_int
thread=kernel.GetCurrentThread()
if not kernel.SetThreadPriority(thread,1):raise ctypes.WinError(ctypes.get_last_error())
if kernel.GetThreadPriority(thread)!=1:raise OSError('Unable to select network thread scheduling')"""
def normalize_network_thread(tree):
 function=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_normal_scheduling')
 nodes=ast.parse(SETUP).body
 start=next(i for i,n in enumerate(function.body)if isinstance(n,ast.Assign)and ast.unparse(n.targets[0])=='kernel.GetCurrentThread.restype')
 assert [ast.dump(n)for n in function.body[start:start+len(nodes)]]==[ast.dump(n)for n in nodes]
 del function.body[start:start+len(nodes)]
 found=[]
 for n in ast.walk(function):
  if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='dict':
   fields=[k for k in n.keywords if k.arg=='network_thread_priority'];assert len(fields)==1
   found.append(ast.unparse(fields[0].value));n.keywords.remove(fields[0])
 assert found==['kernel.GetThreadPriority(thread)','1']
 return tree
