"""Conservative causal links from actual server evaluations, never from elapsed time."""
from pathlib import Path
import hashlib


def verified_site(site,root):
    if not isinstance(site,dict) or site.get('disk_matches_loaded_code') is not True:return False
    if root is None:return False
    name=site.get('file');digest=site.get('disk_source_sha256')
    if not isinstance(name,str) or not isinstance(digest,str):return False
    root=Path(root).resolve();path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file():return False
    return hashlib.sha256(path.read_bytes()).hexdigest()==digest


def business_cause(observations,exception=None,*,source_root=None,exact_session=False):
    terminal=(exception.get('frames')or[{}])[-1] if isinstance(exception,dict) else {}
    def owns_exception(observation):
        site=observation.get('site',{})
        return (site.get('code_sha256') is not None and site.get('code_sha256')==terminal.get('code_sha256')
                and site.get('file')==terminal.get('file') and site.get('function')==terminal.get('function')
                and type(site.get('line'))is int and type(terminal.get('line'))is int
                and 0<terminal['line']-site['line']<=3)
    checks=[o for o in observations if o.get('topic')=='business_condition' and o.get('details',{}).get('passed') is False and owns_exception(o)]
    if not checks:return None
    verified=exact_session and all(verified_site(c.get('site'),source_root)for c in checks)
    return dict(status='direct_cause_verified' if verified else 'evidence_incomplete',
        direct_cause_confirmed=verified,defect_confirmed=False,
        scope='本次业务请求被拒绝的直接条件',checks=checks,
        missing=[] if verified else ['需核同次游玩关联及实际运行源码。'])


def gate_cause(details,*,source_root=None,exact_session=False):
    result=dict(status='evidence_incomplete',direct_cause_confirmed=False,defect_confirmed=False,
        links=[],missing=[],scope='本次服务端关卡条件未满足的直接原因')
    if not exact_session:result['missing'].append('缺少同账号、同次游玩关联。')
    checks=details.get('condition_checks',[])
    if not checks:
        result['missing'].append('没有当前状态下实际执行的条件判定；快照中的对象列表不能代替判定结果。')
        return result
    # OR alternatives: one failed route does not establish that the entire gate is blocked.
    count=details.get('condition_count')
    complete=type(count)is int and count>0 and len(checks)==count and {c.get('index')for c in checks}==set(range(count))
    if not complete:result['missing'].append('未覆盖当前关卡的全部可选推进条件。')
    if any(c.get('ready') is True for c in checks):
        result['status']='condition_already_satisfied'
        result['missing'].append('已有推进条件满足；需继续核通知、传输和客户端消费。')
        return result
    rejections=details.get('actor_rejections',[]);covered=0
    for check in checks:
        if check.get('ready') is not False:continue
        keys=check.get('missing_keys',[])
        identities={v['key']:v for v in check.get('missing_actors',[])if isinstance(v,dict)}
        matches={}
        for rejection in rejections:
            at=rejection.get('observed_monotonic');checked=check.get('observed_monotonic')
            if (rejection.get('scene')!=details.get('scene') or rejection.get('actor') not in keys
                or not isinstance(rejection.get('actor_identity'),dict)
                or rejection['actor_identity']!=identities.get(rejection['actor'])
                or not isinstance(at,(int,float)) or not isinstance(checked,(int,float)) or at>checked):continue
            matches[rejection['actor']]=rejection
        all_mode=check.get('mode')=='all'
        enough=(bool(matches) if all_mode else check.get('mode')=='any' and bool(keys) and set(matches)==set(keys) and not check.get('keys_omitted'))
        if check.get('reason')=='portal_not_requested':enough=False
        if not enough:
            result['missing'].append(f"条件 {check.get('index')} 缺少造成其不满足的上游证据（{check.get('reason')}）。")
            continue
        chosen=list(matches.values())[:1] if all_mode else list(matches.values())
        sites_ok=verified_site(check.get('site'),source_root) and all(verified_site(r.get('site'),source_root)for r in chosen)
        covered+=int(sites_ok)
        for rejection in chosen:
            result['links'].append(dict(condition=check['index'],actor=rejection['actor'],
                rejected_sequence=rejection.get('sequence'),reason=rejection['reason'],
                facts=rejection.get('facts',{}),rejection_site=rejection.get('site'),condition_site=check.get('site'),
                source_verified=sites_ok,
                chain='该对象的退休报告被拒绝 → 判定时仍未退休 → 实际推进条件返回 False'))
        if not sites_ok:result['missing'].append('关联条件或拒绝分支的已加载源码未与指定版本核对一致。')
    if exact_session and complete and covered==count:
        result.update(status='direct_cause_verified',direct_cause_confirmed=True)
    elif result['links']:result['status']='partial_cause_chain'
    result['missing']=list(dict.fromkeys(result['missing']))
    # The branch may implement a valid rule. No inference here declares the implementation defective.
    return result
