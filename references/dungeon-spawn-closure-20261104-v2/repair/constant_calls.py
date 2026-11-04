"""Reuse the qualified KL register/constant call trace, restricted to native 2CE APIs."""
def trace(dump,enums):
 calls=[];unresolved=[]
 for pi,pr in enumerate(dump['prototypes']):
  if not any(isinstance(x,str)and x.lower()in('createnpcreq_lua','createnpchostreq_lua')for x in pr['kgc']):continue
  reg={};proven={}
  for pc,(op,a,c,b)in enumerate(pr['instructions'],1):
   value=c|b<<8
   if op==12:reg[a]=reg.get(value);proven[a]=proven.get(value)
   elif op==24:reg[a]=value if value<32768 else value-65536;proven[a]=pc
   elif op==25:reg[a]=pr['knum'][value];proven[a]=pc
   elif op==26:reg[a]=[None,False,True][value];proven[a]=pc
   elif op==22:reg[a]=pr['kgc'][value];proven[a]=pc
   elif op==62:reg[a]=enums.get(pr['kgc'][value]);proven[a]=pc
   elif op==65:
    obj=reg.get(b);key=pr['kgc'][c];reg[a]=obj.get(key)if isinstance(obj,dict)else('method',key);proven[a]=pc
   elif op==64:
    obj,key=reg.get(b),reg.get(c);reg[a]=obj.get(key)if isinstance(obj,dict)and isinstance(key,(str,int))else None;proven[a]=pc
   elif op==46:
    fn=reg.get(a);args=[reg.get(i)for i in range(a+2,a+c+1)]if c else[]
    if isinstance(fn,tuple)and fn[0]=='method'and fn[1].lower()in('createnpcreq_lua','createnpchostreq_lua'):
     target=args[1]if len(args)>1 else None
     item=dict(prototype=pi,call_pc=pc,method=fn[1],target=target if type(target)is int and target>0 else None,target_definition_pc=proven.get(a+3))
     (calls if item['target']else unresolved).append(item)
    if b==0:
     for r in range(a,pr['frame_size']):reg[r]=None
    elif b>=2:
     for r in range(a,a+b-1):reg[r]=None
   elif op in(61,60,59,45):reg[a]=None
   elif op<20 or op in(63,69,70,68,88,75,76):pass
   else:reg[a]=None
 return calls,unresolved
