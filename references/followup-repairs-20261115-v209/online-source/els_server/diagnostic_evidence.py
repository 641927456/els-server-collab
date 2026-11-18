"""Exception provenance without locals, SQL text, packet bodies or live rereads."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import hashlib
import json
import sys
import types
from pathlib import Path

_rejections=ContextVar('diagnostic_rejections',default=None)
ROOT=Path(__file__).resolve().parent.parent


@lru_cache(maxsize=64)
def compiled_source(path,raw):
    return compile(raw,path,'exec',dont_inherit=True,optimize=sys.flags.optimize)


def find_code(module,target):
    if module.co_qualname==target.co_qualname and module.co_firstlineno==target.co_firstlineno:return module
    for value in module.co_consts:
        if isinstance(value,types.CodeType):
            found=find_code(value,target)
            if found is not None:return found
    return None


def fingerprint(error_type,frame):
    return hashlib.sha256(json.dumps(dict(type=error_type,
        file=frame.get('file'),line=frame.get('line'),
        code=frame.get('disk_source_sha256') if frame.get('disk_matches_loaded_code') else frame.get('code_sha256')),
        sort_keys=True).encode()).hexdigest()


def code_digest(code):
    def constant(value):
        if isinstance(value,types.CodeType):return body(value)
        if isinstance(value,bytes):return ['bytes',value.hex()]
        if isinstance(value,tuple):return ['tuple',[constant(v)for v in value]]
        if isinstance(value,frozenset):return ['frozenset',sorted((constant(v)for v in value),key=repr)]
        if value is Ellipsis:return ['ellipsis']
        if value is None or type(value) in (str,int,float,bool):return value
        return [type(value).__name__,repr(value)]
    def body(value):
        return [value.co_code.hex(),[constant(v)for v in value.co_consts],value.co_names,
                value.co_varnames,value.co_freevars,value.co_cellvars,value.co_argcount,
                value.co_posonlyargcount,value.co_kwonlyargcount,value.co_flags,
                value.co_firstlineno,value.co_linetable.hex(),value.co_exceptiontable.hex()]
    return hashlib.sha256(json.dumps(body(code),sort_keys=True,ensure_ascii=True).encode()).hexdigest()


def code_identity(code):
    return _code_identity(code,code.co_filename)


@lru_cache(maxsize=512)
def _code_identity(code,filename):
    path=Path(filename)
    try:name=path.resolve().relative_to(ROOT).as_posix()
    except ValueError:name=path.name
    source_matches=None
    try:
        raw=path.read_bytes();source_sha=hashlib.sha256(raw).hexdigest()
        disk_code=find_code(compiled_source(code.co_filename,raw),code)
        source_matches=disk_code is not None and disk_code==code
    except (OSError,SyntaxError,ValueError):source_sha=None
    return dict(file=name,function=code.co_name,
                code_sha256=code_digest(code),
                disk_source_sha256=source_sha,
                disk_matches_loaded_code=source_matches,
                source_basis='file read on first observation of code; verify against release before editing')


def exception_evidence(error,depth=0):
    from els_server.diagnostic_reports import redact_text
    result=dict(type=type(error).__name__,reason=redact_text(str(error)[:1200]))
    frames=[];tb=error.__traceback__
    while tb is not None:
        frames.append(dict(code_identity(tb.tb_frame.f_code),line=tb.tb_lineno))
        tb=tb.tb_next
    result['frames']=frames[-16:]
    result['frames_omitted']=max(0,len(frames)-16)
    terminal=frames[-1] if frames else {}
    result['fingerprint']=fingerprint(result['type'],terminal)
    for name in ('sqlite_errorcode','sqlite_errorname','errno','winerror'):
        value=getattr(error,name,None)
        if type(value) in (int,str):result[name]=value
    linked=error.__cause__ or (error.__context__ if not error.__suppress_context__ else None)
    if linked is not None and depth<3:
        result['cause' if error.__cause__ else 'context']=exception_evidence(linked,depth+1)
    if isinstance(error,BaseExceptionGroup) and depth<3:
        result['children']=[exception_evidence(child,depth+1) for child in error.exceptions[:4]]
        result['children_omitted']=max(0,len(error.exceptions)-4)
    return result


@contextmanager
def rejection_scope(sample):
    token=_rejections.set(sample)
    try:yield
    finally:_rejections.reset(token)


def record_rejection(error):
    sample=_rejections.get()
    if sample is not None:
        rows=sample.setdefault('rejections',[])
        if len(rows)<4:
            evidence=exception_evidence(error)
            if not evidence['frames']:
                caller=sys._getframe(1)
                evidence['condition_site']=dict(code_identity(caller.f_code),line=caller.f_lineno)
                evidence['fingerprint']=fingerprint(evidence['type'],evidence['condition_site'])
            rows.append(evidence)


def recording():
    return _rejections.get() is not None


def record_observation(topic,reason,details,*,stacklevel=1,include_site=True):
    sample=_rejections.get()
    if sample is None:return
    rows=sample.setdefault('observations',[])
    if len(rows)>=8:
        sample['observations_omitted']=sample.get('observations_omitted',0)+1
        if topic!='gameplay_progress':return
        rows.pop(0)
    row=dict(topic=topic,reason=reason,details=details)
    if include_site:
        caller=sys._getframe(stacklevel)
        row['site']=dict(code_identity(caller.f_code),line=caller.f_lineno)
    rows.append(row)


def observation_omissions():
    sample=_rejections.get()
    return 0 if sample is None else sample.get('observations_omitted',0)
