const $ = (id) => document.getElementById(id);
const state = {runs: [], evaluation: null, overview: null, section: 'decisions', offset: 0,
  page: null, paused: false, busy: false, request: 0, events: [], lastSuccess: null, connected: null, errorText: ''};
const labels = {cash: 'وجه نقد', hold_shared_risk: 'نگهداری با ریسک مشترک', rule: 'قاعده بدون AI', rule_ai: 'قاعده + AI'};
const statusLabels = {AVAILABLE: 'موجود', UNAVAILABLE: 'در دسترس نیست', EMPTY: 'بدون رکورد', STALE: 'داده کهنه', INVALID: 'شاهد نامعتبر'};
const featureUnits = {last_close: 'TMN', trend_sma_fast: 'TMN', trend_sma_slow: 'TMN', atr_14: 'TMN',
  available_tmn_cash: 'TMN', current_position_base: 'USDT', rsi_14: 'index', volume_ratio: 'ratio'};
function node(tag, content, className) {
  const el = document.createElement(tag);
  if (content !== undefined && content !== null) el.textContent = content;
  if (className) el.className = className;
  return el;
}
function format(value, unit = '') {
  if (value === null || value === undefined) return 'نامعلوم';
  // Formatting only; no floating-point money arithmetic or rounding.
  const s = String(value), parts = s.split('.');
  const formatted = /e/i.test(s) ? s : parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (parts.length > 1 ? '.' + parts[1] : '');
  return formatted + (unit ? ' ' + unit : '');
}
function short(value, unit='') {
  if (value == null) return 'نامعلوم';
  const match=String(value).match(/^(-?\d+)(?:\.(\d+))?$/);
  if (!match) return format(value,unit);
  const fraction=match[2] || '';
  return (/[1-9]/.test(fraction.slice(2)) ? '≈ ' : '') + format(match[1]+(fraction ? '.'+fraction.slice(0,2) : ''),unit);
}
function time(value, both = false) {
  if (!value) return 'زمان نامعلوم';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return 'زمان نامعتبر';
  const zone = $('timezone').value;
  const display = (z) => new Intl.DateTimeFormat('en-GB', {timeZone: z, dateStyle: 'short', timeStyle: 'medium'}).format(date) + ' · ' + z;
  return both ? display('Asia/Tehran') + '\n' + display('UTC') : display(zone);
}
function options(select, rows, old) {
  select.replaceChildren(...rows.map(([value, title]) => {
    const option = node('option', title); option.value = value; return option;
  }));
  if (rows.some(([v]) => v === old)) select.value = old;
}
async function api(route, params = {}) {
  const controller = new AbortController();
  const deadline = setTimeout(() => controller.abort(), 6000);
  try {
    const query = new URLSearchParams(params).toString();
    const response = await fetch('/api/v1/' + route + (query ? '?' + query : ''), {cache: 'no-store', signal: controller.signal});
    const data = await response.json();
    if (!response.ok) throw new Error(data.status === 'INVALID' ? 'شاهد یا درخواست نامعتبر است' : 'منبع انتخاب‌شده در دسترس نیست');
    return data;
  } finally { clearTimeout(deadline); }
}
function selection(extra = {}) {return {run: $('run').value, dataset: $('dataset').value, ...extra};}
function setNotice(title, message, error = false) {
  $('alert').className = 'notice ' + (error ? 'error' : 'warning');
  $('alert').replaceChildren(node('strong', title), node('span', message));
}
function renderOffline() {
  $('connection').textContent='قطع اتصال / OFFLINE';$('mode').textContent='OFFLINE';
  $('mode-description').textContent='آخرین داده ذخیره‌شده؛ اتصال جاری برقرار نیست';
  $('feed-status').textContent='STALE / اتصال قطع';
  setNotice('ارتباط API قطع است','آخرین داده ذخیره‌شده نمایش داده می‌شود. زمان آخرین دریافت: '+time(state.lastSuccess)+'؛ '+state.errorText,true);
}
function renderOverview() {
  const o = state.overview;
  if (!o) return;
  const feed = o.observation;
  $('mode').textContent = feed.mode;
  $('mode-description').textContent = feed.mode === 'OBSERVE_ONLY' ? 'آخرین اجرای مشاهده عمومی · بدون سفارش' : 'حالت موتور تأیید نشده است';
  $('worker').textContent = 'Worker: ' + feed.worker;
  $('feed-status').textContent = (statusLabels[feed.status] || feed.status) + ' / ' + feed.status;
  $('feed-time').textContent = time(feed.observed_at);
  $('feed-time').title = time(feed.observed_at, true);
  $('feed-age').textContent = feed.freshness_seconds == null ? 'freshness نامعلوم' : format(feed.freshness_seconds, 'ثانیه از مشاهده') + ' · سلامت worker نامعلوم';
  $('clock').textContent = time(o.server_time);
  $('reserved').textContent = format(o.reservation.amount, 'USD');
  $('reservation-count').textContent = format(o.reservation.requests, 'رزرو') + ' · ' + format(o.reservation.reserved_tokens, 'token رزروشده') + ' · ' + o.reservation.status;
  $('usage').textContent = format(o.archived_usage.input_tokens) + ' / ' + format(o.archived_usage.output_tokens);
  $('model-info').textContent = [o.model.model || 'مدل نامعلوم', o.model.provider || 'provider نامعلوم',
    format(o.model.decisions, 'تصمیم snapshot تاریخی'), format(o.model.average_latency_seconds, 'ثانیه میانگین تشخیصی'),
    'timeout / error: نامعلوم', 'توافق با baseline اثبات مزیت مالی نیست.'].join(' · ');
  if ($('account-status')) {
    if (o.account && o.account.status === 'AVAILABLE') {
      $('account-status').textContent = o.account.reconciliation === 'PAPER_INTERNAL_LEDGER' ? 'دفتر کل کاغذی؛ پول مجازی' : 'مشاهدهٔ ذخیره‌شدهٔ حساب اعتباری';
      $('account-equity').textContent = 'ارزش حساب: ' + format(o.account.equity_tmn, 'TMN');
      const tmnFree = o.account.balances && o.account.balances.TMN ? o.account.balances.TMN.free : null;
      const assets = Object.entries(o.account.balances || {}).filter(([asset]) => asset !== 'TMN')
        .map(([asset, balance]) => format(balance.total, asset));
      $('account-detail').textContent = 'نقدینگی آزاد: ' + format(tmnFree, 'TMN') + ' · دارایی‌ها: ' + (assets.join(' · ') || 'دارایی غیرتومانی ثبت نشده');
    } else {
      $('account-status').textContent = (statusLabels[o.account && o.account.status] || (o.account && o.account.status) || 'UNAVAILABLE');
      $('account-equity').textContent = 'منتظر اتصال موتور';
      $('account-detail').textContent = 'موجودی آزاد / قفل‌شده / ارزش حساب: نامعلوم';
    }
  }
  if ($('reflections-list') && o.reflections) {
    const list = $('reflections-list');
    const items = o.reflections.items || [];
    if (!items.length) {
      list.replaceChildren(node('p', 'هنوز معامله خروجی یا درسی در حافظه پایدار ثبت نشده است.', 'empty'));
    } else {
      list.replaceChildren(...items.map(ref => {
        const item = node('div', null, 'event');
        const body = node('div');
        body.append(
          node('strong', ref.symbol + ' · سود/زیان: ' + format(ref.net_pnl_tmn, 'TMN') + ' (' + format(ref.return_pct, '%') + ') · دلیل: ' + (ref.exit_reason || '—')),
          node('p', 'درس ثبت‌شده: ' + ref.lesson),
          node('small', time(ref.recorded_at) + ' · شناسه: ' + ref.reflection_id)
        );
        item.append(node('b', ref.net_pnl_tmn && ref.net_pnl_tmn.startsWith('-') ? 'LOSS' : 'WIN'), body);
        return item;
      }));
    }
  }
  if (feed.status === 'STALE') setNotice('داده ذخیره‌شده کهنه است', 'اتصال جاری موتور تأیید نشده؛ زمان آخرین مشاهده را بررسی کنید. حساب صرافی منتظر اتصال موتور است.');
  else setNotice('حساب و worker جاری تأیید نشده‌اند', 'شواهد محلی برای بررسی در دسترس‌اند؛ وضعیت سرور داشبورد، سلامت ربات یا آمادگی معامله نیست.');
  state.events = [
    {severity:'WARNING', title:'حساب UNAVAILABLE', message:'خروجی تأییدشده صرافی باید توسط موتور فراهم شود؛ اتصال خصوصی در داشبورد وجود ندارد.'},
    {severity:'WARNING', title:'Worker UNKNOWN', message:'آخرین heartbeat ذخیره‌شده، فعالیت جاری worker را ثابت نمی‌کند.'},
    ...feed.warnings.map(w => ({severity:'WARNING', title:w, message:'محدودیت منبع مشاهده؛ زمان و provenance را بررسی کنید.'})),
    ...(feed.errors || []).map(e => ({severity:'ERROR', title:e.error_type || 'خطای بدون نوع ثبت‌شده', message:'تلاش '+format(e.attempt)+' · منبع مشاهده را در موتور بررسی کنید؛ داشبورد درخواست مجدد بازار نمی‌فرستد.'})),
    ...(feed.events || []).map(e => ({severity:e.event_type.endsWith('ERROR') ? 'ERROR' : 'INFO', title:e.event_type, message:time(e.observed_at) + ' · ' + e.event_id})),
  ];
  renderEvents();
  if (state.connected === false) renderOffline();
}
function renderEvents() {
  const records = state.events.filter(e => $('severity').value === 'ALL' || e.severity === $('severity').value);
  $('events').replaceChildren(...records.map(e => {
    const row = node('div', null, 'event');
    const body = node('div'); body.append(node('strong', e.title), node('p', e.message));
    row.append(node('b', e.severity), body); return row;
  }));
  if (!records.length) $('events').append(node('p', 'هیچ رویدادی در فیلتر حاضر نیست؛ نبود گزارش خطا اثبات نبود خطا نیست.', 'empty'));
}
function svg(tag, attrs, content) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  if (content !== undefined) el.textContent = content;
  return el;
}
function renderChart() {
  const e = state.evaluation;
  if (!e) return;
  const field = $('chart-kind').value, arm = e.arms.find(a => a.name === $('arm').value);
  const arms = $('compare').checked && e.comparable ? e.arms : (arm ? [arm] : []);
  const series = arms.filter(a => a.curve.length && a.curve.every(p => p[field] !== null && p.observed_at));
  $('chart').replaceChildren(); $('legend').replaceChildren();
  $('chart-title').textContent = field === 'equity_tmn' ? 'ارزش خالص · TMN' : 'افت از قله · درصد';
  if (!series.length) {
    $('chart').append(node('div', 'UNAVAILABLE · این artifact منحنی معتبر ندارد؛ داده جایگزین ساخته نمی‌شود.', 'empty'));
    $('chart').setAttribute('aria-label', 'نمودار در دسترس نیست');
    return;
  }
  const all = series.flatMap(a => a.curve.map(p => Number(p[field])));
  let lo = Math.min(...all), hi = Math.max(...all);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return;
  const pad = hi === lo ? Math.max(Math.abs(hi) * .002, 1) : (hi - lo) * .12;
  lo -= pad; hi += pad;
  const first = Date.parse(series[0].curve[0].observed_at), last = Date.parse(series[0].curve.at(-1).observed_at);
  const x = t => 90 + (Date.parse(t) - first) / (last - first || 1) * 640;
  const y = value => 215 - (Number(value) - lo) / (hi - lo) * 190;
  const chart = svg('svg', {viewBox:'0 0 760 260', role:'img', 'aria-label':$('chart-title').textContent + '؛ ' + series.map(a => a.name).join(', ')});
  for (let n = 0; n < 5; n++) {
    const value = lo + (hi-lo)*n/4, yy = y(value);
    chart.append(svg('line', {x1:90,x2:730,y1:yy,y2:yy}), svg('text', {x:80,y:yy+4,'text-anchor':'end'}, value.toLocaleString('en-US', {maximumFractionDigits: field === 'equity_tmn' ? 0 : 3})));
  }
  for (let n = 0; n < 3; n++) {
    const t = first + (last-first)*n/2;
    chart.append(svg('text', {x:90+320*n,y:245,'text-anchor':n===0?'start':n===2?'end':'middle'}, new Intl.DateTimeFormat('en-GB', {timeZone:$('timezone').value, month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(t)));
  }
  series.forEach((a, i) => {
    chart.append(svg('path', {d:a.curve.map((p,j) => (j?'L':'M')+x(p.observed_at).toFixed(2)+','+y(p[field]).toFixed(2)).join(' '),class:'curve-'+i}));
    const entry = node('span'); entry.append(node('i',null,'color-'+i),node('span',a.name)); $('legend').append(entry);
  });
  $('chart').append(chart);
  $('chart').setAttribute('aria-label', $('chart-title').textContent + ' · ' + $('timezone').value + ' · مقادیر دقیق در جدول نقاط');
}
function definition(parent, label, value, exact=value) {
  const dd=node('dd',value); dd.title=String(exact); dd.setAttribute('aria-label',String(exact)); parent.append(node('dt',label),dd);
}
function renderEvaluation() {
  const e = state.evaluation;
  if (!e) return;
  const arm = e.arms.find(a => a.name === $('arm').value);
  $('evidence').textContent = e.evidence_kind;
  $('research-state').textContent = [e.gate || 'گیت نامعلوم', e.evidence_kind,
    e.comparable ? 'مقایسه درون همین manifest / قرارداد همسان ثبت‌شده' : 'همسانی تأیید نشده؛ نمودار تک‌شاخه',
    'اعتبار bindings نسبت به checkout جاری بازبینی نشده'].join(' · ');
  $('compare').disabled = !e.comparable;
  if (!e.comparable) $('compare').checked = false;
  $('metrics').replaceChildren();
  if (arm) {
    const m = arm.metrics;
    for (const [title,key,unit] of [['ارزش نهایی','final_equity_mtm_tmn','TMN'],['سرمایه مبنا','initial_capital_tmn','TMN'],
      ['سود/زیان محقق','total_realized_pnl','TMN'],['کارمزد','total_fees_paid_tmn','TMN'],['بیشینه exposure','peak_exposure_tmn','TMN'],
      ['بیشینه افت','max_drawdown_pct','٪']]) definition($('metrics'),title,short(m[key],unit),format(m[key],unit));
    definition($('metrics'),'قله equity / همین منحنی',short(arm.peak_equity_tmn,'TMN'),format(arm.peak_equity_tmn,'TMN'));
    definition($('metrics'),'سود/زیان باز / آخرین نقطه',short(arm.latest_unrealized_pnl_tmn,'TMN'),format(arm.latest_unrealized_pnl_tmn,'TMN'));
    for (const [asset,balance] of Object.entries(arm.latest_balances || {})) {
      definition($('metrics'),'آزاد / قفل‌شده · '+asset,short(balance.free)+' / '+short(balance.locked)+' '+asset,format(balance.free)+' / '+format(balance.locked)+' '+asset);
    }
    $('risk-note').textContent = '≈ نمایش کوتاه؛ مقدار دقیق در جدول و عنوان مقدار. ' + (arm.drawdown_basis || 'تعریف افت در دسترس نیست') + ' · سیاست جاری stop و kill-switch نامعلوم است.';
  }
  $('comparison').replaceChildren(...e.arms.map(a => {
    const row = node('tr',null,a.name === $('arm').value ? 'selected-row' : '');
    const first = node('td',labels[a.name] || a.name); first.append(node('small',a.evidence_kind || 'UNKNOWN'));
    row.append(first);
    for (const key of ['final_equity_mtm_tmn','net_return_pct','max_drawdown_pct','total_fees_paid_tmn']) row.append(node('td',format(a.metrics[key]),'num'));
    row.append(node('td',[a.counts.total_orders_including_stop_finalization,a.counts.fills_count,a.counts.closed_round_trips].map(v=>v??'؟').join(' / '),'num'));
    return row;
  }));
  $('provenance-data').replaceChildren();
  for (const [label,value] of [['run',e.run_id],['dataset',e.dataset],['نوع شاهد',e.evidence_kind],['manifest SHA256',e.sha256],
    ['revision',e.revision || 'ثبت نشده'],['code SHA256',e.bindings.code_sha256 || 'ثبت نشده'],['data SHA256',e.bindings.data_sha256 || e.acceptance.sha256 || 'ثبت نشده'],
    ['config SHA256',e.bindings.config_sha256 || 'ثبت نشده'],['protocol SHA256',e.protocol_sha256 || 'ثبت نشده'],
    ['زمان artifact',time(e.observed_at,true)],['هشدار',e.warnings.join(' · ')]]) definition($('provenance-data'),label,value);
  $('curve-data').replaceChildren();
  if (arm?.curve.length) {
    const table = node('table'), head = node('thead'), row = node('tr');
    ['زمان / '+$('timezone').value,'equity TMN','drawdown %','realized TMN','unrealized TMN'].forEach(v=>row.append(node('th',v))); head.append(row);table.append(head);
    const body = node('tbody');
    for (const p of arm.curve) {
      const tr = node('tr'); [time(p.observed_at),p.equity_tmn,p.drawdown_pct,p.realized_pnl_tmn,p.unrealized_pnl_tmn].forEach(v=>tr.append(node('td',format(v),'num')));body.append(tr);
    }
    table.append(body);$('curve-data').append(table);
  } else $('curve-data').append(node('p','منحنی موجود نیست.','empty'));
  renderChart();
}
function showDetail(record) {
  const content = $('detail-content'); content.replaceChildren();
  const add = (title,value) => content.append(node('h3',title),node('pre',JSON.stringify(value,null,2)));
  if (state.section === 'decisions') {
    add('تصمیم ثبت‌شده / نتیجه مدل با نوع شاهد همین run', {decision_id:record.decision_id,action:record.action,reason:record.reason,evidence_ids:record.evidence_ids,observed_at:record.observed_at});
    add('ورودی feature / شناسه binding', {snapshot_sha256:record.snapshot_sha256,binding:record.feature_binding,
      features:Object.fromEntries(Object.entries(record.features).map(([k,v])=>[k,{value:v,unit:featureUnits[k]}]))});
    add('نتیجه میزبان / risk gate',record.risk);
    add('سفارش و fill مرتبط با client_id',record.orders.length ? record.orders : {status:'UNAVAILABLE',client_id:record.client_id,message:'شناسه پیوند موجود نیست؛ timestamp جایگزین نمی‌شود.'});
  } else add('وضعیت ثبت‌شده / fillهای own-ledger',record);
  content.append(node('p','reconciliation و موجودی واقعی حساب در دسترس نیست. وضعیت این رکورد تاریخی است.','muted'));
  $('detail').showModal();
}
function renderRows() {
  const page = state.page;
  if (!page) return;
  const symbol = $('symbol-filter').value.trim().toUpperCase();
  const rows = page.items.filter(r => !symbol || (r.symbol || '').toUpperCase().includes(symbol));
  $('activity-list').replaceChildren(...rows.map(record => {
    const row = node('article',null,'record'), identity=node('div'), body=node('div');
    identity.append(node('strong',record.symbol || 'UNKNOWN'),node('small',record.action || record.side || 'UNKNOWN'));
    body.append(node('p',record.reason || ('وضعیت: '+(record.state || 'UNKNOWN'))),node('small',record.decision_id || record.client_id || 'شناسه نامعلوم'));
    const date=node('time',record.observed_at ? time(record.observed_at) : 'زمان ثبت نشده'); date.title=time(record.observed_at,true);
    const button=node('button','بررسی جزئیات'); button.addEventListener('click',()=>showDetail(record));
    row.append(date,identity,body,button); return row;
  }));
  if (!rows.length) $('activity-list').append(node('p', page.status === 'UNAVAILABLE' ? 'UNAVAILABLE · این artifact جزئیات این بخش را ندارد.' : 'EMPTY · رکوردی با فیلتر حاضر وجود ندارد.', 'empty'));
  $('activity-state').textContent = (statusLabels[page.status] || page.status) + ' · ' + page.evidence_kind + ' · فیلتر نماد فقط روی همین صفحه';
  $('previous').disabled = state.offset === 0;
  $('next').disabled = page.next_offset === null;
  $('page-count').textContent = format(page.total,'رکورد') + ' · صفحه ' + (Math.floor(state.offset/25)+1);
}
async function loadRows() {
  if (!$('run').value || !$('dataset').value || !$('arm').value) return;
  const request = ++state.request;
  $('activity-state').textContent = 'در حال دریافت رکوردها…';
  try {
    const page = await api(state.section, selection({arm:$('arm').value,offset:state.offset,limit:25,action:$('action').value}));
    if (request !== state.request) return;
    state.page = page;renderRows();
  } catch (e) {if (request === state.request) $('activity-state').textContent = 'INVALID / UNAVAILABLE · '+e.message;}
}
async function loadEvaluation() {
  if (!$('run').value || !$('dataset').value) return;
  $('research-state').textContent = 'در حال دریافت ارزیابی…';
  const params = selection();
  try {
    const result = await api('evaluation',params);
    if (params.run !== $('run').value || params.dataset !== $('dataset').value) return;
    state.evaluation=result;
    options($('arm'),result.arms.map(a=>[a.name,labels[a.name] || a.name]),$('arm').value);
    renderEvaluation();await loadRows();
  } catch (e) {
    state.evaluation=null;state.page=null;
    $('research-state').textContent='INVALID / UNAVAILABLE · '+e.message;
    $('chart').replaceChildren(node('p','شاهد انتخاب‌شده قابل نمایش نیست.','empty'));
    $('metrics').replaceChildren();$('comparison').replaceChildren();$('curve-data').replaceChildren();$('provenance-data').replaceChildren();$('legend').replaceChildren();
    $('activity-list').replaceChildren(node('p','UNAVAILABLE · ارزیابی قابل خواندن نیست.','empty'));
  }
}
function chooseDataset() {
  const run=state.runs.find(r=>r.run_id===$('run').value);
  options($('dataset'),(run?.datasets || []).map(v=>[v,v]),$('dataset').value);
}
async function refresh() {
  if (state.busy) return;
  state.busy=true;$('refresh').disabled=true;$('connection').textContent='در حال تازه‌سازی…';
  try {
    const [overview,runs]=await Promise.all([api('overview'),api('runs')]);
    state.connected=true;state.overview=overview;state.runs=runs.items;
    options($('run'),state.runs.map(r=>[r.run_id,((r.evidence_kind || '').includes('SYNTHETIC')?'SYNTHETIC / ':'HISTORICAL / ')+r.run_id.split(':')[1]+' · '+r.status]),$('run').value);
    renderOverview();chooseDataset();
    if (!state.runs.length) {
      $('research-state').textContent='EMPTY · هیچ artifact پشتیبانی‌شده‌ای وجود ندارد.';
      $('chart').replaceChildren(node('p','بدون شاهد؛ بدون داده جایگزین.','empty'));
      $('activity-list').replaceChildren(node('p','UNAVAILABLE · ابتدا شاهد معتبر موتور یا پژوهش لازم است.','empty'));
    } else await loadEvaluation();
    state.lastSuccess=new Date().toISOString();$('connection').textContent='API محلی متصل · worker نامعلوم';
    $('last-refresh').textContent='آخرین دریافت داشبورد: '+time(state.lastSuccess);
  } catch (e) {
    state.connected=false;state.errorText=e.message;renderOffline();
  } finally {state.busy=false;$('refresh').disabled=false;}
}
$('run').addEventListener('change',()=>{state.offset=0;chooseDataset();loadEvaluation();});
$('dataset').addEventListener('change',()=>{state.offset=0;loadEvaluation();});
$('arm').addEventListener('change',()=>{state.offset=0;renderEvaluation();loadRows();});
$('chart-kind').addEventListener('change',renderChart);
$('compare').addEventListener('change',renderChart);
$('timezone').addEventListener('change',()=>{renderOverview();renderEvaluation();renderRows();if(state.lastSuccess)$('last-refresh').textContent='آخرین دریافت داشبورد: '+time(state.lastSuccess);});
$('severity').addEventListener('change',renderEvents);
$('symbol-filter').addEventListener('input',renderRows);
$('action').addEventListener('change',()=>{state.offset=0;loadRows();});
for (const section of ['decisions','orders']) $(section+'-tab').addEventListener('click',()=>{
  state.section=section;state.offset=0;
  $('decisions-tab').setAttribute('aria-pressed',String(section==='decisions'));
  $('orders-tab').setAttribute('aria-pressed',String(section==='orders'));
  $('action').disabled=section==='orders';loadRows();
});
$('previous').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-25);loadRows();});
$('next').addEventListener('click',()=>{if(state.page?.next_offset!==null){state.offset=state.page.next_offset;loadRows();}});
$('close-detail').addEventListener('click',()=>$('detail').close());
$('pause').addEventListener('click',()=>{state.paused=!state.paused;$('pause').setAttribute('aria-pressed',String(state.paused));$('pause').textContent=state.paused?'ادامه تازه‌سازی':'توقف تازه‌سازی';$('connection').textContent=state.paused?'تازه‌سازی نمایش متوقف است':'آماده تازه‌سازی';});
$('refresh').addEventListener('click',refresh);
// Keep focused controls and open record details stable during automatic refresh.
setInterval(()=>{if(!state.paused && !document.hidden && !$('detail').open &&
  !document.activeElement?.closest('button,input,select,summary'))refresh();},15000);
refresh();
