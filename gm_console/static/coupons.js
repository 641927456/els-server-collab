'use strict';
// Bearer codes stay in this authenticated page's memory/textarea only.
(() => {
    const q = id => document.getElementById(id);
    let rewards = [], pending = null;
    const clearCodes = () => { q('couponCodes').value = ''; };
    const fail = e => { if (q('loginDialog').open) clearCodes(); error(e); };
    const busy = async (button, fn) => {
        button.disabled = true;
        try { await fn(); } catch (e) { fail(e); }
        finally { button.disabled = false; }
    };
    const number = id => Number(q(id).value);
    function show(result) {
        clearCodes();
        q('couponReceipt').textContent = JSON.stringify({
            operation_id: result.operation_id, created_at: result.created_at,
            revoked_at: result.revoked_at, replayed: result.replayed,
            already_revoked: result.already_revoked, policy: result.policy
        }, null, 2);
        if (Array.isArray(result.codes) && result.codes.every(v => typeof v === 'string')) {
            q('couponCodes').value = result.codes.join('\n');
        }
    }
    function row() {
        if (q('couponRewards').children.length >= 8) throw Error('每批最多配置8行不同奖励');
        const box = el('div', 'form-pair'), select = el('select'), count = el('input');
        select.required = true; select.setAttribute('aria-label', '已核定普通永久单件');
        for (const r of rewards) {
            const option = el('option', '', r.name + ' · #' + r.template + ' · 角色族 ' + r.unit_type);
            option.value = r.template; select.append(option);
        }
        count.type = 'number'; count.min = '1'; count.max = '99'; count.step = '1'; count.value = '1';
        count.required = true; count.setAttribute('aria-label', '奖励数量');
        const remove = el('button', 'text-button', '移除此行'); remove.type = 'button';
        remove.onclick = () => box.remove();
        box.append(select, count, remove); q('couponRewards').append(box);
    }
    q('couponLoad').onclick = e => busy(e.currentTarget, async () => {
        const result = await api('coupon-rewards'); rewards = result.rows;
        q('couponRewards').replaceChildren(); row();
        q('couponAdd').disabled = false; q('couponIssue').disabled = false;
        q('couponScope').textContent = rewards.length + '个已核普通永久时装单件；每行按角色族限制提取。';
    });
    q('couponAdd').onclick = () => { try { row(); } catch (e) { fail(e); } };
    q('couponIssueForm').onsubmit = e => {
        e.preventDefault(); busy(e.submitter, async () => {
            if (pending) throw Error('先查询或重提保留的原操作，勿生成替代批次');
            const rows = [...q('couponRewards').children].map(n => ({
                template: Number(n.querySelector('select').value), quantity: Number(n.querySelector('input').value)
            }));
            if (!rows.length || rows.length > 8 || new Set(rows.map(r => r.template)).size !== rows.length ||
                rows.reduce((n, r) => n + r.quantity, 0) > 99) throw Error('需1至8行不同奖励，总数量不超过99');
            const bound = q('couponAccount').value.trim();
            const value = {
                operation_id: crypto.randomUUID(), reason: q('couponReason').value,
                count: number('couponCount'), max_redemptions: number('couponUses'),
                starts_at: q('couponStart').value ? Math.floor(new Date(q('couponStart').value).getTime() / 1000) : 0,
                expires_at: Math.floor(new Date(q('couponExpiry').value).getTime() / 1000),
                account_id: bound ? Number(bound) : null, rewards: rows
            };
            if (bound && (!Number.isSafeInteger(value.account_id) || value.account_id < 2 || value.max_redemptions !== 1))
                throw Error('绑定账号需有效整数ID且每码限兑换1次');
            const ok = await confirm('发行兑换码', '奖励和期限提交后不可更改。每码每账号最多兑换一次；兑换后由玩家在现金保管箱提取。', '发行', value.reason);
            if (!ok) return;
            value.reason = ok.reason;
            pending = {action: 'coupon-issue', value};
            q('couponOperation').value = value.operation_id; q('couponOperationAction').value = pending.action;
            q('couponPending').textContent = '原操作已保留在本页内存；结果不明时先查询，不会自动换码或重发。';
            show(await api(pending.action, pending.value)); pending = null;
            q('couponPending').textContent = '发行已确认。原操作编号可用于认证后重新查看同一批原码。';
        });
    };
    q('couponRevokeForm').onsubmit = e => {
        e.preventDefault(); busy(e.submitter, async () => {
            if (pending) throw Error('请先核实保留的原操作');
            const ok = await confirm('撤销尚未兑换的码', '仅阻止本批后续兑换，不回收已生成订单或已提取物品。', '撤销', q('couponRevokeReason').value);
            if (!ok) return;
            pending = {action: 'coupon-revoke', value: {operation_id: crypto.randomUUID(), reason: ok.reason, batch_id: q('couponBatch').value.trim()}};
            q('couponOperation').value = pending.value.operation_id; q('couponOperationAction').value = pending.action;
            q('couponPending').textContent = '已保留原撤销操作。结果不明时先查询。';
            show(await api(pending.action, pending.value)); pending = null;
            q('couponPending').textContent = '撤销结果已确认；已兑换权益保留。';
        });
    };
    q('couponInspect').onclick = e => busy(e.currentTarget, async () => {
        const operation = q('couponOperation').value.trim(), action = q('couponOperationAction').value;
        const query = new URLSearchParams({operation_id: operation, action});
        const result = await api('coupon-operation?' + query);
        if (result.committed) {
            show(result.receipt);
            if (pending?.value.operation_id === operation && pending.action === action) pending = null;
            q('couponPending').textContent = '已查到持久回执；显示原批次，不重新发行。';
        } else {
            clearCodes(); q('couponPending').textContent = '同一游戏工作队列核查后未找到提交；仅可显式重提本页保留的原请求。';
        }
    });
    q('couponRetry').onclick = e => busy(e.currentTarget, async () => {
        if (!pending) throw Error('本页没有可重提的原请求；不要用新UUID替代未知批次');
        const result = await api('coupon-operation?' + new URLSearchParams({operation_id: pending.value.operation_id, action: pending.action}));
        if (result.committed) show(result.receipt);
        else show(await api(pending.action, pending.value));
        pending = null; q('couponPending').textContent = '原操作结果已确认。';
    });
    q('couponList').onclick = e => busy(e.currentTarget, async () => {
        const result = await api('coupon-list?offset=' + number('couponOffset'));
        q('couponBatches').textContent = JSON.stringify(result, null, 2);
    });
    q('couponClear').onclick = clearCodes;
    q('logout').addEventListener('click', () => { clearCodes(); pending = null; });
    addEventListener('pagehide', () => { clearCodes(); pending = null; });
    // Convenience only; the authoritative clock/window is checked under SQLite's write lock.
    const expiry = new Date(Date.now() + 7 * 86400000);
    q('couponExpiry').value = new Date(expiry.getTime() - expiry.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
})();
