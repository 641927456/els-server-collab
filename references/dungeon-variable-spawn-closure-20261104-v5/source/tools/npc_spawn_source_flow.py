"""Finite provenance for current KL sources; branches join, native AI is never run."""
import collections,json,math,re,heapq
def freeze(v):
 if type(v)is bool:return('lua_bool',v)
 if isinstance(v,dict):return('dict',tuple((freeze(k),freeze(x))for k,x in v.items()))
 if isinstance(v,list):return('list',tuple(map(freeze,v)))
 return v
class Flow:
 def __init__(self,dump,enums):
  self.dump=dump;self.enums=enums;self.nodes=[];self.ids={};self.functions=[];self.captures=collections.defaultdict(list);self.globals=collections.defaultdict(list);self.table_writes=collections.defaultdict(list);self.stores=[];self.spawns=[]
  for pi in range(len(dump['prototypes'])):self.functions.append(self.function(pi))
  self.names={}
  for name,values in self.globals.items():
   closures={self.nodes[n][1]for value in values for n in value if self.nodes[n][0]=='closure'}
   if len(closures)==1:self.names[name]=next(iter(closures))
  self.incoming=collections.defaultdict(list)
  for pi,f in enumerate(self.functions):
   for call in f['calls'].values():
    for callee in self.function_refs(call['fn']):self.incoming[callee].append((pi,call))
  self.parameter_roles=collections.defaultdict(set)
  for pi,f in enumerate(self.functions):
   for call in f['calls'].values():
    for n in call['fn']:
     raw=self.nodes[n]
     if raw[0]!='lookup':continue
     names={self.nodes[k][1]for k in raw[2]if self.nodes[k][0]=='constant'}
     role='world'if names&{'GetNPCUnitNum','GetNPCUnitListSize','GetNPCUnit','GetLineMap'}else'npc'if names&{'GetPos','GetUnitID','GetIsRight','GetHardLevel','GetHP','GetMaxHP','StateChange_LUA'}else None
     if role:
      for obj in raw[1]:
       value=self.nodes[obj]
       if value[0]=='parameter':self.parameter_roles[tuple(value[1:])].add(role)
  self.memo={};self.active=set()
 def node(self,kind,*args):
  value=(kind,*args)
  if value not in self.ids:self.ids[value]=len(self.nodes);self.nodes.append(value)
  return self.ids[value]
 def function_refs(self,values,seen=None):
  seen=set()if seen is None else seen;out=set()
  for n in values:
   if n in seen:continue
   seen.add(n);kind,*v=self.nodes[n]
   if kind=='closure':out.add(v[0])
   elif kind=='global':
    for value in self.globals[v[0]]:out.update(self.function_refs(value,seen))
   elif kind=='upvalue':
    for value in self.captures[tuple(v)]:out.update(self.function_refs(value,seen))
  return out
 def val(self,v):return frozenset({self.node('constant',freeze(v))})
 def exp(self,kind,*args):return frozenset({self.node(kind,*args)})
 def function(self,pi):
  p=self.dump['prototypes'][pi];code=p['instructions'];states={0:{i:self.exp('parameter',pi,i)for i in range(p['parameters'])}};queue=[0];calls={};returns=[];captured=collections.defaultdict(set)
  def merge(target,state):
   if not 0<=target<len(code):return
   if target not in states:states[target]=dict(state);heapq.heappush(queue,target);return
   old=states[target];changed=False
   for k in old.keys()|state.keys():
    value=old.get(k,self.exp('unknown','unassigned',pi,target,k))|state.get(k,self.exp('unknown','unassigned',pi,target,k))
    if len(value)>80:value=self.exp('unknown','register_join',pi,target,k)
    if old.get(k)!=value:old[k]=value;changed=True
   if changed:heapq.heappush(queue,target)
  # Forward CFG. Numeric loop bodies use one quantified range, including all
  # original iterations; no runtime loop counter or AI callback is executed.
  processed=set()
  while queue:
   pc=heapq.heappop(queue)
   if pc in processed:continue
   processed.add(pc);r=dict(states[pc]);op,a,c,b=code[pc];d=c|b<<8;get=lambda n:r.get(n,self.exp('unknown','register',pi,pc,n));nexts=[pc+1]
   if op==12:r[a]=get(d)
   elif op==24:r[a]=self.val(d if d<32768 else d-65536)
   elif op==25:r[a]=self.val(p['knum'][d])
   elif op==26:r[a]=self.val([None,False,True][d])
   elif op==22:r[a]=self.val(p['kgc'][d])
   elif op==62:r[a]=self.exp('global',p['kgc'][d])
   elif op==63:self.globals[p['kgc'][d]].append(get(a))
   elif op==53:r[a]=self.exp('upvalue',pi,d)
   elif op in(54,55,56,57):pass
   elif op==59:
    child=p['kgc'][d]['child'];uv=bytes.fromhex(self.dump['prototypes'][child]['upvalues'])
    for index in range(len(uv)//2):
     raw=int.from_bytes(uv[index*2:index*2+2],'little');value=get(raw&0xff)if raw&0x8000 else self.exp('upvalue',pi,raw)
     self.captures[child,index].append(value)
     if raw&0x8000:captured[raw&0xff].add((child,index))
    r[a]=self.exp('closure',child)
   elif op in(60,61):
    ref=self.node('table',pi,pc);r[a]=frozenset({ref})
    if op==61:
     for k,v in p['kgc'][d].items():self.table_writes[ref].append((self.val(k),self.val(v)))
   elif op in(64,65,66):r[a]=self.exp('lookup',get(b),self.val(p['kgc'][c])if op==65 else self.val(c)if op==66 else get(c))
   elif op in(68,69,70):
    key=self.val(p['kgc'][c])if op==69 else self.val(c)if op==70 else get(c)
    for ref in get(b):self.table_writes[ref].append((key,get(a)))
   elif op==71:
    # TSETM appends open multiple returns; preserve the producing value.
    for ref in get(a-1):self.table_writes[ref].append((self.exp('unknown','append_index'),get(a)))
   elif 28<=op<=42:
    left,right=get(b),self.val(p['knum'][c])if op<=37 else get(c)
    if 33<=op<=37:left,right=right,left
    r[a]=self.exp('arithmetic',op,left,right)
   elif op==14:r[a]=self.exp('negative',get(d))
   elif op==15:r[a]=self.exp('length',get(d))
   elif op==44:r[a]=self.exp('concat',tuple(get(i)for i in range(b,c+1)))
   elif op==27:
    for n in range(a,d+1):r[n]=self.val(None)
   elif op in(45,46):
    fn=get(a);args=tuple(get(i)for i in range(a+2,a+c+1));calls[pc]=dict(pc=pc+1,fn=fn,args=args)
    rvalue=self.exp('call',pi,pc,fn,args)
    if b==0:
     for n in range(a,p['frame_size']):r[n]=self.exp('return_item',rvalue,n-a)
    elif b>=2:
     for n in range(a,a+b-1):r[n]=rvalue if n==a else self.exp('return_item',rvalue,n-a)
   elif op in(49,50):
    source=get(a-3);r[a]=self.exp('iterator_key',source);r[a+1]=self.exp('iterator_value',source)
   elif op in(75,76):
    if op==76:returns.append(get(a))
    nexts=[]
   elif op in(77,78):
    r[a+3]=self.exp('range',get(a),get(a+1),get(a+2));nexts=[pc+1,pc+1+d-32768]
   elif op in(79,80,81):nexts=[pc+1]
   elif op in(58,88):
    nexts=[pc+1+d-32768]
    if op==58:
     for key in list(captured):
      if key>=a:del captured[key]
    target=nexts[0]
    if target>pc and target+1<len(code)and code[target][0]in(49,50)and code[target+1][0]in(82,83,84):
     base=code[target][1];source=get(base-3);r[base]=self.exp('iterator_key',source);r[base+1]=self.exp('iterator_value',source)
     branch=code[target+1];body=target+2+(branch[2]|branch[3]<<8)-32768
     nexts=[body,target+2]
   elif 0<=op<=11 or op in(18,19):
    if op<=11:
     left=get(a);right=get(d)if op<=5 else self.val(p['kgc'][d])if op<=7 else self.val(p['knum'][d])if op<=9 else self.val([None,False,True][d])
     for target,condition in((pc+1,True),(pc+2,False)):
      state=dict(r);state[a]=self.exp('filter',op,left,right,condition);merge(target,state)
     nexts=[]
    else:nexts=[pc+1,pc+2]
   elif op in(82,83,84,85,86,87):pass
   else:r[a]=self.exp('unknown','opcode',op,pi,pc)
   for register,refs in captured.items():
    if register in r and states[pc].get(register)!=r[register]:
     for ref in refs:self.captures[ref].append(r[register])
   for target in nexts:
    if target>pc:merge(target,r)
  return dict(calls=calls,returns=returns)
 def error(self,text):return frozenset({('unknown',text)})
 def number(self,value):return value[1]if isinstance(value,tuple)and value[0]=='npc_id'else value
 def identity(self,value):return isinstance(value,tuple)and value[0]=='npc_id'
 def resolve(self,values):
  out=set()
  for n in values:out.update(self.resolve_node(n))
  return frozenset(out)
 def resolve_node(self,n):
  if n in self.memo:return self.memo[n]
  if n in self.active:return self.error('recursive_value')
  self.active.add(n)
  try:result=self.evaluate(self.nodes[n])
  finally:self.active.remove(n)
  self.memo[n]=result;return result
 def evaluate(self,node):
  kind,*v=node
  if kind=='constant':return frozenset({v[0]})
  if kind=='unknown':return self.error(str(v[:3]))
  if kind=='table':return frozenset({('table',self.ids[node])})
  if kind=='closure':return frozenset({('closure',v[0])})
  if kind=='global':
   name=v[0]
   if name in self.enums:return frozenset({('enum',name)})
   if name in('TRUE','FALSE'):return frozenset({name=='TRUE'})
   if name in self.globals:return self.resolve(frozenset().union(*self.globals[name]))
   return frozenset({('global',name)})
  if kind=='parameter':
   pi,index=v;args=[c['args'][index]for caller,c in self.incoming[pi]if index<len(c['args'])]
   return self.resolve(frozenset().union(*args))if args else self.error('external_parameter:'+str((pi,index)))
  if kind=='upvalue':
   values=self.captures[tuple(v)];return self.resolve(frozenset().union(*values))if values else self.error('unbound_upvalue:'+str(v))
  if kind=='lookup':
   objects=self.resolve(v[0]);keys=self.resolve(v[1]);out=set()
   for obj in objects:
    if isinstance(obj,tuple)and obj[0]=='enum':
     for key in keys:
      if key in self.enums[obj[1]]:
       value=self.enums[obj[1]][key];out.add(('npc_id',value,key)if obj[1]=='NPC_UNIT_ID'else value)
      elif isinstance(key,tuple)and key[0]=='string_pattern':
       out.update(('npc_id',value,name)if obj[1]=='NPC_UNIT_ID'else value for name,value in self.enums[obj[1]].items()if re.fullmatch(key[1],name))
    elif isinstance(obj,tuple)and obj[0]in('table','object'):
     for reference,items in list(self.table_writes.items()):
      if reference!=obj[1]and obj not in self.resolve_node(reference):continue
      for key,value in items:
       written=self.resolve(key)
       if written&keys or any(isinstance(k,tuple)and k[0]=='unknown'for k in written|keys):out.update(self.resolve(value))
    elif isinstance(obj,tuple)and obj[0]=='dict':
     out.update(value for key,value in obj[1]if key in keys)
    elif isinstance(obj,tuple)and obj[0]=='global':
     out.update(('method',obj,key)for key in keys if isinstance(key,str))
    else:out.update(('method',obj,key)for key in keys if isinstance(key,str))
   return frozenset(out)or self.error('empty_lookup')
  if kind=='range':
   start,end,steps=[self.resolve(x)for x in v];out=set()
   for a in start:
    for b in end:
     for step in steps:
      if type(a)is int and type(b)is int and type(step)is int and step and abs(b-a)<500:out.update(range(a,b+(1 if step>0 else-1),step))
      else:out.add(('unknown','loop_range'))
   return frozenset(out)
  if kind=='negative':return frozenset(-x if type(x)in(int,float)else('unknown','negative')for x in self.resolve(v[0]))
  if kind=='concat':
   result={('',False)}
   for value in v[0]:
    parts=self.resolve(value);new=set()
    for prefix,pattern in result:
     for part in parts:
      if type(part)in(str,int,float):text=str(part)if type(part)in(str,int)else format(part,'.14g');new.add((prefix+(re.escape(text)if pattern else text),pattern))
      elif isinstance(part,tuple)and part[0]=='string_pattern':new.add(((prefix if pattern else re.escape(prefix))+part[1],True))
      else:new.add(((prefix if pattern else re.escape(prefix))+r'[+-]?\d+',True))
    result=new
    if len(result)>500:return self.error('concat_bound')
   return frozenset(('string_pattern',text)if pattern else text for text,pattern in result)
  if kind=='filter':
   op,left,right,condition=v;out=set()
   for a in self.resolve(left):
    for b in self.resolve(right):
     try:
      av,bv=self.number(a),self.number(b)
      if isinstance(av,tuple)or isinstance(bv,tuple):out.add(a);continue
      predicate=(av<bv if op==0 else av>=bv if op==1 else av<=bv if op==2 else av>bv if op==3 else av==bv if op%2==0 else av!=bv)
      if predicate==condition:out.add(a)
     except TypeError:out.add(a)
   return frozenset(out)
  if kind=='length':
   out=set()
   for obj in self.resolve(v[0]):
    if isinstance(obj,tuple)and obj[0]=='table':
     keys=set()
     for ref,items in self.table_writes.items():
      if ref==obj[1]or('table',obj[1])in self.resolve_node(ref):keys.update(*(self.resolve(k)for k,val in items))
     ints={k for k in keys if type(k)is int and k>0};out.add(max(ints,default=0))
    elif isinstance(obj,tuple)and obj[0]=='dict':out.add(max((k for k,v in obj[1]if type(k)is int and k>0),default=0))
    else:out.add(('unknown','length'))
   return frozenset(out)
  if kind=='arithmetic':
   op,left,right=v;left=self.resolve(left);right=self.resolve(right);out=set();operator=(op-28)%5 if op<38 else op-38
   for a in left:
    for b in right:
     av,bv=self.number(a),self.number(b)
     if type(av)in(int,float)and type(bv)in(int,float):
      try:
       value=(av+bv,av-bv,av*bv,av/bv if bv else None,av%bv if bv else None)[operator]
       out.add(('npc_id',int(value),'source_enum_arithmetic')if(self.identity(a)or self.identity(b))and type(value)in(int,float)and int(value)==value else value)
      except(OverflowError,ValueError):out.add(('unknown','arithmetic_bound'))
     elif operator==4 and type(b)is int and 0<b<=100:out.update(range(b))
     else:out.add(('unknown','arithmetic'))
   return frozenset(out)
  if kind=='return_item':
   values=self.resolve(v[0]);out=set()
   for value in values:
    if isinstance(value,tuple)and value[0]=='iterator':out.update(self.resolve(value[1])if v[1]==1 else{0}if v[1]==2 else{value})
    elif v[1]==0:out.add(value)
    else:out.add(('unknown','multi_return'))
   return frozenset(out)
  if kind in('iterator_key','iterator_value'):
   out=set()
   for value in self.resolve(v[0]):
    if not isinstance(value,tuple)or value[0]!='iterator':continue
    for obj in self.resolve(value[1]):
     if isinstance(obj,tuple)and obj[0]=='table':
      for key,data in self.table_writes[obj[1]]:out.update(self.resolve(key if kind=='iterator_key'else data))
   return frozenset(out)or self.error('iterator_source')
  if kind=='call':return self.call(*v)
  return self.error(kind)
 def call(self,pi,pc,fn,args):
  out=set()
  for n in fn:
   if self.nodes[n]==('global','TableCopy')and args:
    out.update(self.resolve(args[0]));continue
   if self.nodes[n]==('global','D3DXVECTOR3')and len(args)==3:
    obj=self.node('call',pi,pc,fn,args)
    for key,value in zip(('x','y','z'),args):
     pair=(self.val(key),value)
     if pair not in self.table_writes[obj]:self.table_writes[obj].append(pair)
    out.add(('object',obj));continue
   if self.nodes[n]in(('global','pairs'),('global','ipairs'))and args:
    out.add(('iterator',args[0]));continue
   if self.nodes[n]in(('global','ShuffleTable'),('global','ShuffleTable_RandSeed'))and args:
    out.update(self.resolve(args[0]));continue
   callees=self.function_refs(frozenset({n}))
   if callees:
    for callee in callees:
     returns=self.functions[callee]['returns'];out.update(self.resolve(frozenset().union(*returns))if returns else self.error('no_return'))
    continue
   for f in self.resolve_node(n):
    if isinstance(f,tuple)and f[0]=='method':
     method=f[-1]
     if method in('GetInt_LUA','GetNumber_LUA'):
      keys=self.resolve(args[1])if len(args)>1 else self.error('slot_key');out.update(self.memory(method,keys,f[1]))
     elif method=='GetVector_LUA':
      keys=self.resolve(args[1])if len(args)>1 else self.error('slot_key');out.update(self.memory(method,keys,f[1]))
     elif method in('random','GetRandVal'):
      bounds=[self.resolve(x)for x in args[(1 if method=='GetRandVal'else 0):]]
      if len(bounds)==2 and all(len(b)==1 for b in bounds):
       a,b=[next(iter(x))for x in bounds]
       if type(a)is int and type(b)is int and 0<=b-a<500:out.update(range(a,b+1));continue
      out.add(('unknown','random'))
     elif method in('floor','ceil')and args:
      out.update((math.floor(x)if method=='floor'else math.ceil(x))if type(x)in(int,float)else('unknown','round')for x in self.resolve(args[0]))
     elif method in('GetPos','GetStartPosition','GetLandPosition_LUA'):out.add(('object',self.node('call',pi,pc,fn,args)))
     elif method in('ShuffleTable_RandSeed','ShuffleTable')and len(args)>2 and f[1]==('global','NPC'):out.update(self.resolve(args[2]))
     else:out.add(('unknown','native_call:'+str(method)))
    elif isinstance(f,tuple)and f[0]=='global'and f[1]=='TableCopy'and args:out.update(self.resolve(args[0]))
    elif isinstance(f,tuple)and f[0]=='global'and f[1]=='tostring'and args:
     out.update(str(x)if type(x)in(str,int)else format(x,'.14g')if type(x)is float else('unknown','tostring')for x in self.resolve(args[0]))
    else:out.add(('unknown','function'))
  return frozenset(out)or self.error('call')
 def receiver_role(self,value):
  if isinstance(value,tuple)and value[0]=='unknown':
   match=re.fullmatch(r'external_parameter:\((\d+), (\d+)\)',value[1])
   if match:
    key=tuple(map(int,match.groups()));roles=self.parameter_roles[key]
    if len(roles)==1:return next(iter(roles))
    if self.dump['prototypes'][key[0]]['parameters']==3 and not self.incoming[key[0]]:
     return 'world'if key[1]==1 else'npc'if key[1]==2 else None
    if self.dump['prototypes'][key[0]]['parameters']==2 and not self.incoming[key[0]]and key[1]==1:return'npc'
  return None
 def memory(self,method,keys,receiver):
  setter={'GetInt_LUA':'SetInt_LUA','GetNumber_LUA':'SetNumber_LUA','GetVector_LUA':'SetVector_LUA'}[method];out=set();unknown_keys=any(isinstance(k,tuple)and k[0]=='unknown'for k in keys);role=self.receiver_role(receiver)
  for pi,f in enumerate(self.functions):
   for call in f['calls'].values():
    for n in call['fn']:
     raw=self.nodes[n]
     if raw[0]!='lookup':continue
     names=self.resolve(raw[2])
     if setter not in names or len(call['args'])<3:continue
     if role:
      receivers=self.resolve(call['args'][0]);roles={self.receiver_role(obj)for obj in receivers}
      if roles and None not in roles and role not in roles:continue
     written=self.resolve(call['args'][1])
     if unknown_keys or keys&written:
      for value in call['args'][2]:
       alias=self.nodes[value]
       # Writing a getter value back to its same typed slot is an identity
       # edge in this source lattice; it introduces no new constructor.
       if alias[0]=='call'and alias[4]and len(alias[4])>1:
        same=False
        for function in alias[3]:
         getter=self.nodes[function]
         if getter[0]=='lookup'and method in self.resolve(getter[2])and self.resolve(alias[4][1])==written:same=True
        if same:continue
       out.update(self.resolve_node(value))
  return frozenset(out)or self.error('unbound_slot')
 def spawn_results(self):
  out=[]
  for pi,f in enumerate(self.functions):
   for pc,call in f['calls'].items():
    names=set()
    for n in call['fn']:
     raw=self.nodes[n]
     if raw[0]=='lookup':names.update(self.resolve(raw[2]))
    if names&{'CreateNPCReq_LUA','CreateNPCHostReq_LUA'}:
     result=self.resolve(call['args'][1]);literal={self.nodes[n][1]for n in call['args'][1]if self.nodes[n][0]=='constant'and type(self.nodes[n][1])is int and self.nodes[n][1]>0 and self.nodes[n][1]in self.enums['NPC_UNIT_ID'].values()};targets=sorted(literal|{x[1]for x in result if self.identity(x)and x[1]>0 and x[1]in self.enums['NPC_UNIT_ID'].values()});unknown=[str(x)for x in result if not self.identity(x)and x not in literal];identities=[list(x)for x in result if self.identity(x)]+[['native_literal',x,'direct_native_spawn_argument']for x in sorted(literal)]
     out.append(dict(prototype=pi,call_pc=pc+1,targets=targets,unknown=unknown,identity_witnesses=identities))
  return out
