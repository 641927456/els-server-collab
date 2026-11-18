let clientNoticeDirty = false;
let clientNoticeRevision = null;

function renderClientNotices(force = false) {
    const config = state?.client_notices;
    const available = Boolean(config && state.ready);
    $('#clientNoticeFields').disabled = !available;
    $('#reloadClientNotice').disabled = !available;
    const status = $('#clientNoticeStatus');
    if (!available) {
        status.textContent = '尚未读取客户端提示配置，请等待配套游戏服务就绪。';
        return;
    }
    if (clientNoticeDirty && !force) {
        status.textContent = config.revision === clientNoticeRevision ? '有未保存的修改。' :
            '配置已被更新；你的草稿已保留，请重新载入后核对。';
        return;
    }
    status.textContent = config.enabled ? '服务端配置：开启。配套客户端同步后，按原生时机显示。' :
        '服务端配置：关闭。配套客户端同步后，不再显示这条提示。';
    if (!force && clientNoticeRevision === config.revision) return;
    clientNoticeRevision = config.revision;
    clientNoticeDirty = false;
    $('#clientNoticeEnabled').checked = config.enabled;
    $('#clientNoticeText').value = config.text;
    $('#clientNoticeOriginal').textContent = config.original_text;
}

$('#clientNoticeEnabled').onchange = $('#clientNoticeText').oninput = () => clientNoticeDirty = true;
$('#restoreClientNotice').onclick = () => {
    $('#clientNoticeText').value = state.client_notices.original_text;
    $('#clientNoticeEnabled').checked = true;
    clientNoticeDirty = true;
    $('#clientNoticeStatus').textContent = '已填入原文并开启，请保存后生效。';
};
$('#reloadClientNotice').onclick = event => action(event.currentTarget, async () => {
    if (clientNoticeDirty && !await confirm('重新载入客户端提示', '将放弃这条提示尚未保存的修改。', '', '重新载入客户端提示')) return;
    state = await api('status');
    renderClientNotices(true);
});
$('#clientNoticeForm').onsubmit = event => {
    event.preventDefault();
    action(event.submitter, async () => {
        if (!state?.ready || !state.client_notices) throw Error('请等待配套游戏服务就绪');
        const settings = {enabled: $('#clientNoticeEnabled').checked, text: $('#clientNoticeText').value};
        const expected_revision = clientNoticeRevision;
        const result = await confirm(settings.enabled ? '保存客户端提示' : '关闭客户端提示',
            (settings.enabled ? settings.text : '停止显示防诈骗与官方联系方式提示，保留正文。') +
            '\n配套客户端通常在 30 秒内同步；已显示的聊天记录不会清除。', '', $('#clientNoticeReason').value);
        if (!result) return;
        state.client_notices = await api('client-notices', {
            operation_id: result.operation_id, reason: result.reason, settings, expected_revision});
        clientNoticeDirty = false;
        renderClientNotices(true);
        toast('客户端提示配置已保存');
    });
};

renderClientNotices();
