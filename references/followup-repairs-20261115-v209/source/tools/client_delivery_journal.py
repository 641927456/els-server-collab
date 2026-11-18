"""Bounded client observations. No native memory access or inferred success."""
from collections import deque
from copy import deepcopy
import re
import json
import math

PHASES=frozenset(('ready','disabled','observer_error','event_decoded','event_decode_failed','frame_without_event','dispatch_enter','dispatch_return','dispatch_unmatched','state_observed','effect_observed','lifecycle_observed'))

def effect_data(value,depth=0):
    if depth>9:return None
    if isinstance(value,dict):
        allowed={'snapshot','unavailable','owner','item','items','present','group','slot','uid','template','count','quests','quest','active','completed','record_owner','objectives','id','scene','handle_index','handle_generation','stage','gate','target','known','passage_enabled','paired_enabled','trigger','definition_present','active_count','geometry_count','geometry_sha256','geometry_enabled','actor','hp','max_hp','mp','max_mp','buffs','temporary_weapon','mount','stamina','geometry','unavailable_fields','part','definition','definition_sha256','effect_vector','linked_factor','lines','enabled','template','mode','stack_path','stack_decay','expired','caster','factor','stack_count','timers','index','remaining','budget','paused','forced_expiry','elapsed','duration','delay','retired'}
        return {k:effect_data(v,depth+1)for k,v in value.items()if k in allowed}
    if isinstance(value,list):return [effect_data(v,depth+1)for v in value[:512]]
    if type(value)is float and not math.isfinite(value):return None
    if type(value)in (int,float,bool)or value is None:return value
    if isinstance(value,str):return value[:100]
    return None


def lifecycle_shape(row):
    """Coalesce steady progression, preserving transitions such as pause and stack_count changes."""
    def shape(value):
        if isinstance(value,list):return [shape(v)for v in value]
        if isinstance(value,dict):return {k:(v>0 if k=='delay'and type(v)in(int,float)else shape(v))for k,v in value.items()if k not in('remaining','elapsed')}
        return value
    return shape(row.get('snapshot'))

class ClientDeliveryJournal:
    def __init__(self):
        self.rows=deque(maxlen=256);self.status=deque(maxlen=8);self.omitted=0;self.byte_size=0

    def record(self,message):
        value=message.get('payload',{})
        if value.get('event')!='client_delivery_trace' or value.get('phase')not in PHASES:return False
        row={k:value[k]for k in ('phase','sequence','trace_id','timestamp','dropped','thread','kind','event_id',
            'payload_bytes','frame_bytes','payload_mode','receive_scope','site_rva','role','result',
            'cursor_before','cursor_after','read_only','hooks','reason','response_result','checkpoint','effect','native_effect_calls','line_id','requested_enabled','quest_enumeration_unavailable','component','status','elapsed_ms','window_ms','observation_id','geometry_index','part_index','manager_enabled','manager_limit','association','event_thread','coalesced_samples')if k in value and type(value[k])in(int,float,bool,str)}
        row={k:v[:180]if isinstance(v,str)else v for k,v in row.items()}
        for key in ('before','after','cursor_after'):
            if key in value and value[key]is None:row[key]=None
        for key in ('payload_sha256','frame_sha256','client_sha256','profile_sha256'):
            if isinstance(value.get(key),str)and re.fullmatch('[a-f0-9]{64}',value[key]):row[key]=value[key]
        for key in ('uid','target_uid'):
            if isinstance(value.get(key),str)and re.fullmatch('[0-9]{1,20}',value[key]):row[key]=value[key]
        for key in ('before','after'):
            state=value.get(key)
            if isinstance(state,dict):
                row[key]=effect_data(state)if value['phase']in ('state_observed','effect_observed','lifecycle_observed')else{k:state[k]for k in ('handle_index','handle_generation','stage','part','suspended')if type(state.get(k))is int}
        if value['phase']=='lifecycle_observed' and isinstance(value.get('owner'),str)and value['owner'].isdecimal():row['owner']=value['owner'][:20]
        if value['phase']=='effect_observed' and 'definition'in value:row['definition']=effect_data(value['definition'])
        if value['phase']in ('state_observed','lifecycle_observed'):
            for key in ('snapshot','unavailable','scene'):
                if key in value:row[key]=effect_data(value[key])
        for key in ('script_source','script_instance','script_sha256'):
            if isinstance(message.get(key),str):row[key]=message[key][:128]
        if row['phase']in ('ready','disabled'):
            self.status.append(row);return True
        if row['phase']=='lifecycle_observed'and row.get('status')=='sample':
            comparable=[r for r in self.rows if all(r.get(k)==row.get(k)for k in('phase','status','script_instance','trace_id','component','observation_id'))]
            if len(comparable)>=3 and lifecycle_shape(comparable[-2])==lifecycle_shape(comparable[-1])==lifecycle_shape(row):
                removed=comparable[-2];self.rows.remove(removed);self.byte_size-=removed['_size']
                row['coalesced_samples']=1+removed.get('coalesced_samples',0)
        size=len(json.dumps(row,separators=(',',':')).encode('utf8'))
        if size>256*1024:self.omitted+=1;return False
        while self.rows and (len(self.rows)==self.rows.maxlen or self.byte_size+size>256*1024):
            removed=self.rows.popleft();self.byte_size-=removed.pop('_size');self.omitted+=1
        row['_size']=size;self.byte_size+=size
        self.rows.append(row);return True

    def snapshot(self):
        return dict(schema=1,events=deepcopy(list(self.status)+[{k:v for k,v in row.items()if k!='_size'}for row in self.rows]),omitted=self.omitted,
                    interpretation='Decode, dispatch return and observed state are distinct; absent observations do not prove absent execution.')
