/* Read-only projection of persisted game observations. No game rules live here. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const SVG = 'http://www.w3.org/2000/svg';
  const token = new URLSearchParams(location.hash.slice(1)).get('access_token');
  if (token) history.replaceState(null, '', location.pathname + location.search);
  const modes = {pattern: '发现规律', creation: '创造', resonance: '运行与重演'};
  const kinds = {mirror: '反射', reflect: '反射', delay: '延迟', echo: '回声', gate: '门', reservoir: '蓄积门', merge: '汇合', source: '脉冲源'};
  const origins = {preview: '结构变化后的预览', perform: 'AI 运行的过程', begin: 'AI 控制的演奏', reperform: 'AI 重新控制熟悉作品', probe: 'AI 检查的过程', replay: 'AI 付费原样重演', fork: 'AI 改变条件后的过程', extend: 'AI 接着演奏的后续', hold: 'AI 选择保持的已知节奏', tap: 'AI 轻推后的过程'};
  const actionNames = {enter: '进入区域', select_piece: '选择作品', inspect: '检查规律', probe: '观察信号', hypothesize: '提出假设', complete: '完成发现', combine: '组合节点', connect: '改变连接', transform: '变换节点', tune: '调整参数', configure: '调整参数', reshape: '改变节点作用', perform: '运行世界', begin: '开始交互演奏', reperform: '重新演奏熟悉作品', wait: '等待四拍', release: '放开蓄积门', continue: '继续四拍', extend: '接着演下一段', hold: '保持已知节奏', tap: '轻推一下', stop: '停止本段演奏', run: '运行世界', seal: '保存作品', revise: '继续修改作品', replay: '原样重演', fork: '尝试变化', deepen: '继续深入', vary: '改变风格', finish: '完成体验', abandon: '离开当前区域', leave: '主动结束游玩', restore: '取回作品继续修改', import: '带入已有作品'};
  const paramNames = {left: '起点', right: '终点', relation: '关系', node: '节点', operation: '变化', phase: '相位', delay: '延迟', threshold: '阈值', period: '输入周期', release_tick: '开门拍数', kind: '节点作用', answer: '答案', style: '风格', value: '数值', parameter: '参数', field: '参数', name: '名称', source: '输入节点'};
  const valueNames = {supports: '支持', tensions: '抵消', reflects: '反射', invert: '反相', mirror: '反转', rotate: '旋转', order: '规律重复', complexity: '复杂结构', reveal: '逐步揭示', narrative: '叙事', relationship: '关系', agency: '自主控制'};
  const kindNames = {'rule-script': '规则脚本', 'random-script': '随机脚本', 'model-client': '模型客户端', 'live-assistant': '助手逐步选择', unspecified: '未声明接入类型'};
  const state = {sessions: [], selectedId: new URLSearchParams(location.search).get('session'), explicitSelection: new URLSearchParams(location.search).has('session'), selectionEpoch: 0, detailRequest: 0, detailController: null, detail: null, detailKey: null, listKey: null, selectedNode: null, selectedEvent: null, manualEventSelection: false, trace: null, frameIndex: 0, showCurrentStructure: false, playback: null, connected: false, stopped: false};

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function svg(tag, attributes = {}, text) {
    const node = document.createElementNS(SVG, tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  const array = value => Array.isArray(value) ? value : [];
  const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const number = (value, fallback = 0) => typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  const text = (value, fallback = '—') => typeof value === 'string' && value ? value : fallback;
  const signed = value => value > 0 ? '+' + value : String(value);
  const short = (value, limit = 45) => { const chars = Array.from(String(value)); return chars.length > limit ? chars.slice(0, limit - 1).join('') + '…' : chars.join(''); };
  function pieceName(visible, id) {
    const piece = array(visible.pieces).find(item => item.id === id);
    return text(piece?.label, id === 'custom' ? '自定义作品' : text(id, '未选择作品'));
  }
  function cycleText(cycle) {
    if (!(number(cycle.period) > 0)) return '';
    return '完整状态已确认 ' + number(cycle.period) + ' 拍循环 · 无新输入或干预时保持';
  }
  function targetName(action, outcome) {
    const visible = object(state.detail?.observation?.observation);
    if (action.type === 'select_piece') return pieceName(visible, action.target);
    if (['extend', 'hold', 'tap'].includes(action.type)) {
      const id = outcome.piece_id || outcome.experience?.piece_id;
      return id ? pieceName(visible, id) : '演奏中的作品';
    }
    if (['replay', 'reperform', 'fork', 'restore'].includes(action.type)) {
      const saved = array(visible.saved_experiences).find(item => item.id === action.target);
      return saved ? text(saved.label, '保存的过程') : '保存的过程';
    }
    const area = array(visible.catalog).find(item => item.id === action.target);
    return area ? areaName(area) : text(action.target, '');
  }
  function processStatus(experience) {
    const labels = {boundary: '本段结束 · 可以选择后续', waiting_release: '存量仍在门内 · 等待玩家放开', settled: '自然收束 · 已无待传播信号', stopped: '玩家已停止本段演奏', limit: '达到总推进上限 · 本次截断', completed: '有限过程已结束'};
    return labels[experience.state] || '过程已保存';
  }
  function date(at, full = false) {
    const value = new Date(number(at) * 1000);
    return Number.isFinite(value.getTime()) ? value.toLocaleString('zh-CN', full ? {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'} : {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}) : '—';
  }
  function activity(summary) { return summary.activity === 'active' ? '正在游玩' : summary.state === 'ended' ? '已结束' : '暂无活动'; }
  function areaName(area) { return area && (modes[area.mode] || area.label || area.id) || '尚未进入区域'; }
  function outcomeText(outcome) {
    outcome = object(outcome);
    if (outcome.kind === 'start') return '创建了新的游玩会话。';
    if (outcome.kind === 'leave') return 'AI 自主结束了这次游玩。';
    if (outcome.correct === true) return '假设与世界规律一致。';
    if (outcome.correct === false) return '这次假设未通过，世界仍可继续探索。';
    if (outcome.kind === 'replay') return '再次触发已保存的同一过程。';
    if (outcome.kind === 'fork') return '改变了一个条件，运行了新的过程。';
    if (outcome.kind === 'extend') return '承接门、存量和在路上的信号，接着演奏同一个运行。';
    if (outcome.kind === 'hold') return '在已确认的循环中，选择保持这段已知节奏。';
    if (outcome.kind === 'tap') return '给当前过程轻推一个脉冲，随后继续展开；这次干预另行记录。';
    if (outcome.kind === 'select_piece' || (outcome.piece_id && outcome.kind === 'selection')) return '选择了一件作品，随后可以演奏或继续创作。';
    if (outcome.kind === 'begin') return '开始交互演奏，并推进前四拍。';
    if (outcome.kind === 'reperform') return '使用已保存的作品，重新决定本次演奏的控制时刻。';
    if (outcome.kind === 'wait') return '玩家选择保持蓄积门关闭，再推进四拍。';
    if (outcome.kind === 'release') return '玩家选择打开蓄积门，并推进四拍。';
    if (outcome.kind === 'continue') return '玩家选择再推进四拍，已有信号继续传播。';
    if (outcome.kind === 'stop') return '玩家停止了本段演奏，已发生的过程仍保留。';
    if (outcome.created_node) return '加入节点 ' + text(outcome.created_node.id) + '：' + text(outcome.created_node.concept);
    if (outcome.connection) return '连接 ' + text(outcome.connection.source) + ' → ' + text(outcome.connection.target);
    if (outcome.transformed_node) return '节点 ' + text(outcome.transformed_node.id) + ' 的状态已改变。';
    if (outcome.kind === 'selection') return '进入' + (modes[outcome.mode] || '新的体验') + '区域。';
    if (outcome.kind === 'seal') return '已留下这一版作品，可继续修改或回看。';
    if (outcome.kind === 'revise') return '保留原有结构，继续修改作品。';
    const process = object(outcome.performance || outcome.process);
    if (array(process.frames).length) return '产生了 ' + process.frames.length + ' 拍真实信号变化。';
    return outcome.completed ? '完成了这段体验。' : '世界状态已保存。';
  }

  async function fetchJSON(path, signal) {
    const response = await fetch(path, {cache: 'no-store', signal, headers: token ? {Authorization: 'Bearer ' + token} : {}});
    if (!response.ok) throw new Error(response.status === 401 ? '服务需要访问令牌，请使用带有 access_token 片段的本机链接。' : response.status === 404 ? '这条游玩记录不存在。' : '服务暂时无法提供数据。');
    return response.json();
  }
  function stopPlayback() {
    if (state.playback !== null) clearInterval(state.playback);
    state.playback = null;
    $('play-record').textContent = '播放记录';
    $('playback-tag').hidden = !state.trace || state.frameIndex >= array(state.trace.frames).length - 1;
  }
  function connectionStatus(status, error) {
    state.connected = !error;
    const connection = $('connection-message').parentElement;
    if (error) {
      connection.dataset.state = 'disconnected';
      $('connection-message').textContent = '连接中断';
      $('connection-error').textContent = error + ' 将自动重试；已加载的历史内容仍可查看。';
      $('connection-error').hidden = false;
      if (state.detail) {
        $('view-label').textContent = '连接中断 · 上次收到的记录';
        $('session-state').textContent = '当前活动状态未知';
        $('session-state').dataset.active = 'false';
        if (!$('experience-section').hidden) $('experience-status').textContent = '连接中断 · 上次保存状态';
        if (!$('current-run-section').hidden) $('current-run-status').textContent = '连接中断 · 上次收到的运行状态';
      }
      stopPlayback();
      return;
    }
    $('connection-error').hidden = true;
    const count = number(status.active_sessions);
    connection.dataset.state = count > 0 ? 'active' : 'waiting';
    $('connection-message').textContent = count > 0 ? count + ' 个会话正在游玩' : status.state === 'ended' ? '本次游玩已结束' : '暂无 AI 在玩';
  }
  function renderSessions() {
    const key = JSON.stringify([state.selectedId, state.sessions.map(s => [s.session_id, s.turn, s.activity, s.state, s.energy, s.client_info])]);
    $('session-count').textContent = state.sessions.length ? state.sessions.length + ' 局' : '0 局';
    $('sessions-empty').hidden = state.sessions.length !== 0;
    if (key === state.listKey) return;
    state.listKey = key;
    const fragment = document.createDocumentFragment();
    state.sessions.forEach(summary => {
      const item = element('div');
      item.setAttribute('role', 'listitem');
      const button = element('button', 'session-row');
      button.type = 'button';
      button.setAttribute('aria-current', String(summary.session_id === state.selectedId));
      button.setAttribute('aria-label', text(summary.player_id) + '，' + activity(summary) + '，第 ' + number(summary.turn) + ' 回合');
      const header = element('span', 'session-row-header');
      header.append(element('span', 'session-player', text(summary.player_id)), element('span', 'session-activity ' + (summary.activity === 'active' ? 'active' : ''), activity(summary)));
      const model = element('span', 'session-model', text(summary.model_id));
      model.title = text(summary.model_id);
      const footer = element('span', 'session-row-footer');
      footer.append(element('span', '', number(summary.turn) + ' / ' + number(summary.max_turns, 24) + ' 回合'), element('span', 'date', date(summary.created_at, true)));
      button.append(header, model, footer);
      button.addEventListener('click', () => selectSession(summary.session_id));
      item.append(button);
      fragment.append(item);
    });
    $('session-list').replaceChildren(fragment);
  }
  async function selectSession(id, {explicit = true} = {}) {
    if (typeof id !== 'string' || !id) return;
    state.explicitSelection = explicit;
    if (id === state.selectedId && state.detail) return;
    state.selectedId = id;
    state.selectionEpoch++;
    state.detailKey = null;
    state.selectedNode = null;
    state.selectedEvent = null;
    state.manualEventSelection = false;
    state.showCurrentStructure = false;
    stopPlayback();
    const url = new URL(location.href);
    if (explicit) url.searchParams.set('session', id);
    else url.searchParams.delete('session');
    url.hash = '';
    history.replaceState(null, '', url.pathname + url.search);
    renderSessions();
    $('session-content').hidden = true;
    $('welcome').hidden = false;
    $('welcome-title').textContent = '正在读取记录';
    $('welcome-message').textContent = '从服务端获取这次游玩的状态。';
    try { await loadDetail(id, state.selectionEpoch); }
    catch (error) { if (error.name !== 'AbortError' && id === state.selectedId) { connectionStatus({}, error.message); $('welcome-title').textContent = '暂时无法读取记录'; $('welcome-message').textContent = '可以稍后重试，或选择另一条游玩记录。'; } }
  }
  function renderOverview(summary, observation) {
    $('welcome').hidden = true;
    $('session-content').hidden = false;
    $('view-label').textContent = state.connected ? summary.activity === 'active' ? '实时 · 正在接收 AI 的行动' : summary.state === 'ended' ? '历史记录 · 本局已结束' : '暂停 · 等待 AI 继续' : '连接中断 · 上次收到的记录';
    const version = number(summary.engine_version, 1);
    $('rules-label').textContent = version >= 4 ? 'V' + version + ' · 连续演奏' : version === 3 ? 'V3 · 回环演奏' : version === 2 ? 'V2 · 共享信号世界' : '旧版记录';
    $('player-title').textContent = text(summary.player_id);
    $('model-title').textContent = text(summary.model_id);
    $('turn-number').textContent = String(number(summary.turn)).padStart(2, '0');
    $('turn-total').textContent = ' / ' + number(summary.max_turns, 24) + ' 回合';
    $('energy-value').textContent = number(summary.energy) + ' Energy';
    $('turn-progress').max = Math.max(1, number(summary.max_turns, 24));
    $('turn-progress').value = number(summary.turn);
    $('area-label').textContent = areaName(summary.area);
    const visible = object(observation.observation);
    $('piece-label').hidden = !visible.piece_id;
    $('piece-label').textContent = visible.piece_id ? '当前选择：' + pieceName(visible, visible.piece_id) : '';
    const declared = object(summary.client_info);
    $('client-label').textContent = kindNames[declared.kind] || text(declared.label, '接入类型未声明');
    $('client-label').title = '类型由接入方声明';
    $('session-state').textContent = state.connected ? activity(summary) : '当前活动状态未知';
    $('session-state').dataset.active = String(state.connected && summary.activity === 'active');
    const counts = object(summary.counts);
    const actionCount = kind => array(state.detail?.events).filter(event => event.action?.type === kind).length;
    const reperformances = number(counts.reperformances, actionCount('reperform'));
    const behaviors = [(version >= 2 ? '原样重演 ' : '旧版从头重玩 ') + number(counts.replays) + ' 次'];
    if (version >= 4) behaviors.push('接着演 ' + number(counts.extensions, actionCount('extend')) + ' 次', '保持节奏 ' + number(counts.holds, actionCount('hold')) + ' 次', '轻推 ' + number(counts.taps, actionCount('tap')) + ' 次');
    if (version >= 3) behaviors.push('重新演奏 ' + reperformances + ' 次');
    behaviors.push('尝试变体 ' + number(counts.forks) + ' 次', '回访修改 ' + number(counts.revisions) + ' 次');
    $('behavior-summary').textContent = behaviors.join(' · ');
    const endReason = observation.end_reason;
    $('end-reason').hidden = summary.state !== 'ended';
    $('end-reason').textContent = endReason === 'voluntary_leave' ? 'AI 主动选择结束，还剩 ' + number(summary.energy) + ' Energy。' : '本局已经结束，世界和行动记录均已保留。';
  }
  function renderCurrentRun(visible, summary) {
    const run = object(visible.current_run);
    const section = $('current-run-section');
    section.hidden = !Object.keys(run).length;
    if (section.hidden) return;
    $('current-run-title').textContent = '当前运行 · ' + pieceName(visible, run.piece_id);
    const active = summary.activity === 'active' && state.connected;
    const running = run.state === 'running';
    const cycle = object(run.cycle);
    const resumable = run.can_extend === true;
    const status = running ? active ? '进行中 · 等待玩家下一次选择' : '暂停 · 等待玩家继续' : run.state === 'waiting_release' ? processStatus(run) : resumable ? number(cycle.period) > 0 ? '可选择保持已知节奏、轻推或离开' : '可选择接着演、轻推或离开' : processStatus(run);
    $('current-run-status').textContent = summary.state === 'ended' ? '本局已结束 · 保留最后运行状态' : state.connected ? status : '连接中断 · 上次收到的运行状态';
    $('current-run-progress').textContent = '已推进 ' + number(run.tick) + ' 拍';
    $('current-run-cycle').hidden = !(number(cycle.period) > 0);
    $('current-run-cycle').textContent = cycleText(cycle);
    const shown = object(visible.experience || visible.performance?.experience);
    const other = shown.run_id && (shown.run_id !== run.run_id || number(shown.tick) !== number(run.tick) || visible.performance?.origin === 'replay');
    $('current-run-context').hidden = !other;
    $('current-run-context').textContent = other ? '下方展示另一份过程记录；这里保留真实待续运行的状态。' : '';
  }
  function renderExperience(visible, summary) {
    const experience = object(visible.experience || visible.performance?.experience);
    const section = $('experience-section');
    section.hidden = !Object.keys(experience).length;
    if (section.hidden) return;
    const origin = visible.performance?.origin;
    const labels = {begin: '交互演奏', reperform: '重新演奏熟悉作品', replay: '原样重演', fork: '熟悉变奏', perform: '一次运行', preview: '制作预览', probe: '规律检查', extend: '接着演的后续', hold: '保持已知节奏', tap: '轻推后的过程'};
    const piece = experience.piece_id ? pieceName(visible, experience.piece_id) + ' · ' : '';
    $('experience-mode').textContent = piece + (labels[origin] || '演奏记录');
    const running = experience.state === 'running';
    const recorded = origin === 'replay';
    $('experience-status').textContent = recorded ? '正在展示原样重演的记录' : summary.state === 'ended' ? '本局已结束 · 保留最后过程' : running ? summary.activity === 'active' && state.connected ? '进行中 · 等待玩家下一次选择' : '暂停 · 等待玩家继续' : processStatus(experience);
    $('experience-progress').textContent = '已推进 ' + number(experience.tick) + ' / ' + number(experience.horizon, 24) + ' 拍';
    $('experience-gate').textContent = experience.gate_open === true ? '已打开' : experience.gate_open === false ? '保持关闭' : '状态未提供';
    const reservoirs = Object.entries(object(experience.reservoirs));
    $('experience-storage').textContent = reservoirs.length ? reservoirs.map(([id, value]) => id + ' ' + signed(number(value))).join(' · ') : '未提供';
    const action = object(summary.last_action);
    $('experience-action').textContent = action.type ? '本局最后行动：' + (actionNames[action.type] || action.type) : '';
    $('experience-caption').textContent = '展示过程的保存状态' + (typeof experience.segment_end === 'number' ? ' · 当前付费段至第 ' + experience.segment_end + ' 拍' : '') + ' · 时间轴只查看已经发生的记录';
    const list = $('experience-events');
    list.replaceChildren();
    array(experience.events).slice(-4).forEach(event => {
      const row = element('li');
      row.append(element('span', 'experience-event-tick', '第 ' + number(event.tick) + ' 拍'), element('span', 'experience-event-message', text(event.message, event.kind || '状态变化')));
      list.append(row);
    });
  }
  function renderPieces(visible) {
    const pieces = array(visible.pieces);
    $('pieces-section').hidden = pieces.length === 0;
    const list = $('pieces-list');
    list.replaceChildren();
    pieces.forEach(piece => {
      const row = element('li', 'piece-item');
      row.dataset.selected = String(piece.id === visible.piece_id);
      row.append(element('strong', '', text(piece.label, piece.id)), element('span', '', text(piece.description)));
      list.append(row);
    });
  }
  function activeMachine() {
    const visible = object(state.detail?.observation?.observation);
    if (!state.showCurrentStructure && state.trace?.machine) return object(state.trace.machine);
    return object(visible.machine || (array(visible.active_experience?.nodes).length ? visible.active_experience : {}));
  }
  function renderGraph() {
    const machine = activeMachine();
    const nodes = array(machine.nodes).slice(0, 12);
    const links = array(machine.links).slice(0, 144);
    const graph = $('machine-graph');
    graph.replaceChildren();
    $('graph-empty').hidden = nodes.length !== 0;
    $('node-inspector').hidden = nodes.length === 0;
    $('graph-source').textContent = state.trace && !state.showCurrentStructure ? '展示过程使用的结构 · 第 ' + number(state.trace.frames?.[state.frameIndex]?.tick, state.frameIndex) + ' 拍' : 'AI 当前保存的结构';
    $('structure-toggle').hidden = !state.trace?.machine;
    $('structure-toggle').textContent = state.showCurrentStructure ? '查看过程结构' : '查看当前结构';
    if (!nodes.length) return;
    const positions = new Map();
    const presetPositions = {n0: [65, 190], n1: [215, 190], n2: [390, 80], n3: [390, 295], n4: [575, 190], n5: [750, 190]};
    const orbitPositions = {n0: [60, 195], n1: [225, 195], n2: [390, 80], n3: [620, 80], n4: [710, 280], n5: [430, 300]};
    const usePresetLayout = machine.output === 'n5' && nodes.length === 6 && nodes.every(node => Object.hasOwn(presetPositions, node.id));
    const isChain = links.some(link => link.source === 'n2' && link.target === 'n3') && !links.some(link => link.source === 'n1' && link.target === 'n3');
    nodes.forEach((node, index) => {
      if (usePresetLayout) { const [x, y] = (isChain ? orbitPositions : presetPositions)[node.id]; positions.set(node.id, {x, y}); return; }
      const angle = -Math.PI / 2 + index * 2 * Math.PI / nodes.length;
      positions.set(node.id, {x: nodes.length === 1 ? 420 : 420 + Math.cos(angle) * 255, y: nodes.length === 1 ? 190 : 190 + Math.sin(angle) * 122});
    });
    const defs = svg('defs');
    [['edge-arrow', '#59654f'], ['edge-positive', '#8fbbb2'], ['edge-negative', '#d9b477']].forEach(([id, color]) => {
      const marker = svg('marker', {id, markerWidth: 8, markerHeight: 8, refX: 6, refY: 3, orient: 'auto', markerUnits: 'userSpaceOnUse'});
      marker.append(svg('path', {d: 'M0,0 L6,3 L0,6', fill: 'none', stroke: color, 'stroke-width': 1.2}));
      defs.append(marker);
    });
    graph.append(defs);
    const frame = !state.showCurrentStructure ? object(state.trace?.frames?.[state.frameIndex]) : {};
    const frameValues = object(frame.values);
    const reservoirs = object(frame.reservoirs);
    links.forEach((link, index) => {
      const a = positions.get(link.source), b = positions.get(link.target);
      if (!a || !b) return;
      const value = number(frameValues[link.source]);
      const direction = value > 0 ? 'positive' : value < 0 ? 'negative' : '';
      let d;
      if (link.source === link.target) d = `M ${a.x - 15} ${a.y - 20} C ${a.x - 68} ${a.y - 97}, ${a.x + 68} ${a.y - 97}, ${a.x + 15} ${a.y - 20}`;
      else if (usePresetLayout && link.source === machine.output && nodes.find(node => node.id === link.target)?.kind === 'reservoir') {
        d = isChain ? `M ${a.x - 25} ${a.y + 8} C ${a.x - 150} ${a.y + 50}, ${b.x - 80} ${b.y + 110}, ${b.x - 21} ${b.y + 19}` : `M ${a.x - 12} ${a.y + 25} C ${a.x - 55} 370, ${b.x + 70} 370, ${b.x + 12} ${b.y + 30}`;
      }
      else {
        const dx = b.x - a.x, dy = b.y - a.y, length = Math.max(1, Math.hypot(dx, dy));
        const sx = a.x + dx / length * 28, sy = a.y + dy / length * 28;
        const ex = b.x - dx / length * 32, ey = b.y - dy / length * 32;
        const offset = (index % 2 ? -1 : 1) * 22;
        d = `M ${sx} ${sy} Q ${(sx + ex) / 2 - dy / length * offset} ${(sy + ey) / 2 + dx / length * offset} ${ex} ${ey}`;
      }
      const path = svg('path', {d, class: 'machine-edge' + (direction ? ' is-' + direction : ''), 'marker-end': `url(#edge-${direction || 'arrow'})`});
      path.append(svg('title', {}, String(link.source) + ' → ' + String(link.target) + ' · ' + text(link.relation)));
      graph.append(path);
    });
    nodes.forEach(node => {
      const p = positions.get(node.id), value = number(frameValues[node.id]);
      const direction = value > 0 ? ' is-positive' : value < 0 ? ' is-negative' : '';
      const reservoir = node.kind === 'reservoir';
      const group = svg('g', {class: 'machine-node' + direction + (reservoir ? ' is-reservoir' : '') + (node.id === state.selectedNode ? ' is-selected' : ''), transform: `translate(${p.x},${p.y})`, tabindex: 0, role: 'button', 'aria-label': text(node.id) + '，' + (kinds[node.kind] || text(node.concept, '节点'))});
      const shape = reservoir ? svg('rect', {x: -28, y: -26, width: 56, height: 52, rx: 4, class: 'node-body'}) : svg('circle', {r: 26, class: 'node-body'});
      const role = node.id === machine.source ? '输入' : node.id === machine.output ? '输出' : node.kind === 'reservoir' ? '蓄积' : kinds[node.kind] || '节点';
      group.append(svg('title', {}, text(node.concept, node.id)), shape, svg('text', {class: 'node-id', y: 4}, role), svg('text', {class: 'node-type', y: 47}, node.id + (number(node.delay) > 0 ? ' · 延迟 ' + node.delay + ' 拍' : '')));
      if (state.trace && !state.showCurrentStructure) group.append(svg('text', {class: 'node-value', y: -40}, signed(value)));
      if (reservoir && Object.hasOwn(reservoirs, node.id)) group.append(svg('text', {class: 'node-storage', y: 69}, '存 ' + signed(number(reservoirs[node.id])) + (typeof frame.gate_open === 'boolean' ? frame.gate_open ? ' · 开' : ' · 关' : '')));
      function choose() { state.selectedNode = node.id; renderGraph(); }
      group.addEventListener('click', choose);
      group.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } });
      graph.append(group);
    });
    const selected = nodes.find(node => node.id === state.selectedNode);
    const inspector = $('node-inspector');
    if (!selected) { inspector.replaceChildren(element('span', 'muted', '点选节点'), element('span', '', '查看它在世界中的作用。')); return; }
    inspector.replaceChildren(element('strong', '', text(selected.id)), element('span', '', short(text(selected.concept), 120)));
    if (selected.kind) inspector.append(element('span', '', '作用：' + (kinds[selected.kind] || selected.kind)));
    if (typeof selected.phase === 'number') inspector.append(element('span', '', '相位 ' + selected.phase));
    if (typeof selected.delay === 'number') inspector.append(element('span', '', '延迟 ' + selected.delay + ' 拍'));
    if (typeof selected.threshold === 'number') inspector.append(element('span', '', '阈值 ' + selected.threshold));
    if (selected.kind === 'reservoir' && Object.hasOwn(reservoirs, selected.id)) {
      inspector.append(element('span', '', '本拍存量 ' + signed(number(reservoirs[selected.id]))));
      if (typeof frame.gate_open === 'boolean') inspector.append(element('span', '', frame.gate_open ? '本拍门已开' : '本拍门关闭'));
    }
  }
  function renderLegacy(visible) {
    const active = object(visible.active_experience), legacy = $('legacy-content');
    legacy.replaceChildren();
    legacy.hidden = !!visible.machine || !Object.keys(active).length || array(active.nodes).length > 0;
    if (legacy.hidden) return;
    if (Array.isArray(active.sequence)) {
      legacy.append(element('p', '', '当前可见的规律结构'), element('p', 'legacy-values', active.sequence.join('  ·  ')));
      if (typeof active.solution === 'number') legacy.append(element('p', '', '已发现的答案：' + active.solution));
    } else {
      const signal = object(active.signal);
      legacy.append(element('p', '', '旧版信号 · ' + text(signal.style, '当前体验')));
      if (Array.isArray(signal.fragments)) legacy.append(element('p', '', signal.fragments.join(' / ')));
      else if (Array.isArray(signal.symbols || signal.motif)) legacy.append(element('p', 'legacy-values', (signal.symbols || signal.motif).join(' ')));
      else legacy.append(element('p', '', '这条旧记录没有节点图或逐拍过程。'));
    }
  }
  function renderTrace() {
    const frames = array(state.trace?.frames);
    $('trace-empty').hidden = frames.length > 0;
    $('trace-content').hidden = frames.length === 0;
    $('play-record').disabled = frames.length < 2;
    $('playback-tag').hidden = !frames.length || state.playback === null && state.frameIndex >= frames.length - 1;
    if (!frames.length) { $('trace-description').textContent = '尚未运行信号'; return; }
    const summary = object(state.trace.summary), inputs = object(state.trace.inputs);
    const firstTick = number(frames[0]?.tick), lastTick = number(frames[frames.length - 1]?.tick, frames.length - 1);
    $('trace-description').textContent = (origins[state.trace.origin] || '已记录的信号过程') + ' · 记录窗口第 ' + firstTick + '–' + lastTick + ' 拍' + (typeof inputs.period === 'number' ? ' · 输入周期 ' + inputs.period : '');
    $('tick-slider').max = Math.max(0, frames.length - 1);
    $('tick-slider').value = state.frameIndex;
    const selectedTick = number(frames[state.frameIndex]?.tick, state.frameIndex);
    $('tick-slider').setAttribute('aria-valuetext', '第 ' + selectedTick + ' 拍，记录窗口 ' + firstTick + ' 至 ' + lastTick + ' 拍');
    $('tick-value').textContent = selectedTick;
    $('tick-total').textContent = firstTick + '–' + lastTick;
    const period = summary.cycle_period;
    const experience = object(state.trace.experience);
    const residue = experience.remaining_activity === true ? ' · 仍有存量或待传播信号' : experience.remaining_activity === false ? ' · 已无残留活动' : '';
    const cycle = object(experience.cycle);
    const repetition = number(cycle.period) > 0 ? ' · 完整状态循环 ' + cycle.period + ' 拍' : !Object.keys(experience).length && typeof period === 'number' && period > 0 ? ' · 周期 ' + period + ' 拍' : '';
    $('trace-summary').textContent = number(summary.active_nodes) + ' 个节点参与 · 最多同时响应 ' + number(summary.peak_activity) + ' 个节点' + residue + repetition;
    const trace = $('signal-trace');
    trace.replaceChildren();
    let ids = array(state.trace.machine?.nodes).map(node => node.id);
    if (!ids.length) ids = Array.from(new Set(frames.flatMap(frame => Object.keys(object(frame.values)))));
    ids = ids.slice(0, 12);
    const rowHeight = 19, labelWidth = 50, availableWidth = 780, cellWidth = availableWidth / frames.length;
    const height = Math.max(40, ids.length * rowHeight + 12);
    trace.setAttribute('viewBox', '0 0 840 ' + height);
    ids.forEach((id, row) => {
      trace.append(svg('text', {x: 0, y: row * rowHeight + 13, class: 'trace-node-label'}, id));
      frames.forEach((frame, index) => {
        const value = number(object(frame.values)[id]);
        const color = value > 0 ? '#8fbbb2' : value < 0 ? '#d9b477' : '#2d3527';
        const cell = svg('rect', {x: labelWidth + index * cellWidth, y: row * rowHeight, width: Math.max(1, cellWidth - 3), height: rowHeight - 4, rx: 1, fill: color, opacity: value ? Math.min(1, .45 + Math.abs(value) * .13) : .55, class: 'trace-cell'});
        cell.append(svg('title', {}, id + ' · 第 ' + number(frame.tick, index) + ' 拍 · 信号 ' + value));
        cell.addEventListener('click', () => { stopPlayback(); setTick(index); });
        trace.append(cell);
      });
    });
    trace.append(svg('rect', {x: labelWidth + state.frameIndex * cellWidth - 1, y: -2, width: Math.max(1, cellWidth - 1), height: Math.max(20, ids.length * rowHeight), class: 'trace-cursor', rx: 1}));
  }
  function setTick(index) {
    const frames = array(state.trace?.frames);
    state.frameIndex = Math.max(0, Math.min(frames.length - 1, Number(index) || 0));
    renderGraph();
    renderTrace();
  }
  function renderSaved(visible) {
    const processes = array(visible.saved_experiences), creations = array(visible.creations);
    const list = $('saved-list');
    list.replaceChildren();
    $('saved-count').textContent = String(processes.length + creations.length);
    $('saved-empty').hidden = processes.length + creations.length > 0;
    processes.forEach(process => {
      const row = element('div', 'saved-item');
      const piece = process.piece_id ? pieceName(visible, process.piece_id) : modes[process.mode] || '过程';
      row.append(element('span', '', text(process.label, process.id || '保存的过程')), element('span', 'saved-meta', piece + (process.duration || process.summary?.ticks ? ' · ' + (process.duration || process.summary.ticks) + ' 拍' : '') + (process.stopped === true ? ' · 已停止' : '')));
      list.append(row);
    });
    creations.forEach((creation, index) => {
      const row = element('div', 'saved-item');
      row.append(element('span', '', '作品 · 版本 ' + (typeof creation.revision === 'number' ? creation.revision + 1 : index + 1)), element('span', 'saved-meta', array(creation.nodes || creation.machine?.nodes).length + ' 节点 · ' + array(creation.links || creation.machine?.links).length + ' 连接'));
      list.append(row);
    });
  }
  function renderEventInspector(event) {
    const action = object(event.action), outcome = object(event.outcome);
    $('event-inspector').hidden = false;
    $('event-title').textContent = '第 ' + event.seq + ' 步 · ' + (actionNames[action.type] || (action.type ? action.type : '开始游玩'));
    $('event-result').textContent = outcomeText(outcome);
    const fields = [['时间', date(event.at)], ['消耗', number(outcome.cost) + ' Energy']];
    if (action.target) fields.push(['对象', action.target]);
    Object.entries(object(action.params)).forEach(([key, value]) => fields.push([paramNames[key] || key, typeof value === 'object' ? JSON.stringify(value) : Object.hasOwn(valueNames, String(value)) ? valueNames[value] : String(value)]));
    const fragment = document.createDocumentFragment();
    fields.forEach(([key, value]) => fragment.append(element('dt', '', key), element('dd', '', short(value, 180))));
    $('event-params').replaceChildren(fragment);
  }
  function renderEvents(events) {
    const list = $('event-list');
    list.replaceChildren();
    $('events-count').textContent = events.filter(event => event.action).length + ' 次行动';
    $('events-empty').hidden = events.length > 0;
    if (!events.length) { $('event-inspector').hidden = true; return; }
    if (!state.manualEventSelection || state.selectedEvent === null || !events.some(e => e.seq === state.selectedEvent)) state.selectedEvent = events[events.length - 1].seq;
    [...events].reverse().forEach(event => {
      const action = object(event.action), outcome = object(event.outcome);
      const li = element('li');
      const button = element('button', 'event-row');
      button.type = 'button';
      button.setAttribute('aria-pressed', String(event.seq === state.selectedEvent));
      const content = element('span');
      content.append(element('span', 'event-title', actionNames[action.type] || (action.type ? action.type : '开始游玩')), element('span', 'event-subtitle', (modes[outcome.mode] ? modes[outcome.mode] + ' · ' : '') + (action.target ? short(targetName(action, outcome), 27) + ' · ' : '') + date(event.at)));
      button.append(element('span', 'event-number', String(event.seq).padStart(2, '0')), content);
      button.addEventListener('click', () => { state.selectedEvent = event.seq; state.manualEventSelection = true; renderEvents(events); });
      li.append(button);
      list.append(li);
    });
    renderEventInspector(events.find(event => event.seq === state.selectedEvent));
  }
  function renderDetail(detail) {
    const summary = object(detail.summary), observation = object(detail.observation), visible = object(observation.observation);
    state.detail = detail;
    renderOverview(summary, observation);
    renderCurrentRun(visible, summary);
    renderExperience(visible, summary);
    const key = summary.session_id + ':' + observation.state_version;
    if (key === state.detailKey) return;
    state.detailKey = key;
    stopPlayback();
    state.trace = array(visible.performance?.frames).length ? visible.performance : null;
    state.frameIndex = state.trace ? state.trace.frames.length - 1 : 0;
    renderGraph();
    renderTrace();
    renderLegacy(visible);
    renderSaved(visible);
    renderPieces(visible);
    renderEvents(array(detail.events));
  }
  async function loadDetail(id, epoch) {
    const request = ++state.detailRequest;
    if (state.detailController) state.detailController.abort();
    const controller = new AbortController();
    state.detailController = controller;
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const detail = await fetchJSON('/v1/observer/sessions/' + encodeURIComponent(id), controller.signal);
      if (request !== state.detailRequest || epoch !== state.selectionEpoch || id !== state.selectedId) return;
      if (!detail.summary || !detail.observation || detail.summary.session_id !== id) throw new Error('服务返回的记录格式不完整。');
      renderDetail(detail);
    } catch (error) {
      if (error.name === 'AbortError') {
        if (request !== state.detailRequest || epoch !== state.selectionEpoch || id !== state.selectedId || state.stopped) return;
        throw new Error('读取记录超时。');
      }
      throw error;
    } finally { clearTimeout(timeout); }
  }
  async function poll() {
    if (state.stopped) return;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const payload = await fetchJSON('/v1/observer/sessions?limit=30', controller.signal);
      if (!Array.isArray(payload.sessions) || !payload.status) throw new Error('服务返回的会话列表不完整。');
      state.sessions = payload.sessions;
      connectionStatus(payload.status);
      const recommended = payload.recommended_session_id || state.sessions[0]?.session_id || null;
      let loaded = false;
      if (!state.explicitSelection && recommended && recommended !== state.selectedId) {
        await selectSession(recommended, {explicit: false});
        loaded = true;
      }
      renderSessions();
      if (state.selectedId && !loaded) await loadDetail(state.selectedId, state.selectionEpoch);
      else if (!state.selectedId) { $('welcome-title').textContent = '等待 AI 接入'; $('welcome-message').textContent = '这里观察 AI 怎样选择作品、继续演奏或主动离开。已有的游玩记录可以随时查看。'; }
      $('last-updated').textContent = '最近同步 ' + date(payload.checked_at || Date.now() / 1000);
    } catch (error) {
      if (!state.stopped) connectionStatus({}, error.name === 'AbortError' ? '连接超时。' : error.message || '无法连接游戏服务。');
    } finally { clearTimeout(timeout); if (!state.stopped) setTimeout(poll, 2000); }
  }
  $('structure-toggle').addEventListener('click', () => { state.showCurrentStructure = !state.showCurrentStructure; renderGraph(); });
  $('tick-slider').addEventListener('input', event => { stopPlayback(); setTick(event.target.value); });
  $('play-record').addEventListener('click', () => {
    if (state.playback !== null) { stopPlayback(); return; }
    if (array(state.trace?.frames).length < 2) return;
    state.showCurrentStructure = false;
    state.frameIndex = -1;
    $('play-record').textContent = '暂停记录';
    $('playback-tag').hidden = false;
    state.playback = setInterval(() => {
      const next = state.frameIndex + 1;
      if (next >= state.trace.frames.length) { stopPlayback(); return; }
      setTick(next);
    }, 350);
  });
  $('status-link').addEventListener('click', event => { if (token) event.currentTarget.href = '/status#access_token=' + encodeURIComponent(token); });
  window.addEventListener('pagehide', () => { state.stopped = true; stopPlayback(); if (state.detailController) state.detailController.abort(); });
  poll();
})();
