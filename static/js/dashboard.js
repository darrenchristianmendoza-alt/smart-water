// static/js/dashboard.js — Smart Water Monitor with LLM Integration

const ACCENT='#00cfff',GREEN='#00e887',YELLOW='#ffd040',RED='#ff4455',ORANGE='#ff8c00',MUTED='#3a6070';

Chart.defaults.color=MUTED; Chart.defaults.borderColor='#0e2d42';
Chart.defaults.font.family="'Share Tech Mono', monospace"; Chart.defaults.font.size=10;

function baseOpts(yLabel='') {
  return {
    responsive:true, maintainAspectRatio:false, animation:{duration:0},
    plugins:{legend:{display:false},tooltip:{backgroundColor:'#0c1c28',borderColor:'#0e2d42',
      borderWidth:1,titleColor:ACCENT,bodyColor:'#c8e4f0',padding:10}},
    scales:{
      x:{grid:{color:'#0e2d42'},ticks:{maxTicksLimit:6,maxRotation:0,font:{size:9}}},
      y:{grid:{color:'#0e2d42'},title:{display:!!yLabel,text:yLabel,color:MUTED,font:{size:9}},ticks:{font:{size:9}}}
    }
  };
}
const lineChart=(id,color,lbl)=>new Chart(document.getElementById(id).getContext('2d'),{
  type:'line',data:{labels:[],datasets:[{data:[],borderColor:color,backgroundColor:color+'14',
  borderWidth:1.5,pointRadius:0,tension:0.3,fill:true}]},options:baseOpts(lbl)});
const barChart=(id,color,lbl)=>new Chart(document.getElementById(id).getContext('2d'),{
  type:'bar',data:{labels:[],datasets:[{data:[],backgroundColor:color+'77',
  borderColor:color,borderWidth:1,borderRadius:3}]},options:baseOpts(lbl)});

const C = {
  voltage:lineChart('chartVoltage',ACCENT,'V'), current:lineChart('chartCurrent',GREEN,'A'),
  power:lineChart('chartPower',YELLOW,'W'),     energy:lineChart('chartEnergy','#aa88ff','kWh'),
  daily:barChart('chartDaily',ACCENT,'kWh'),   weekly:barChart('chartWeekly',GREEN,'%'),
  monthly:barChart('chartMonthly',YELLOW,'hrs'),
};

// ── Clock ──────────────────────────────────────────────────────────────────
setInterval(()=>document.getElementById('clock').textContent=
  new Date().toLocaleTimeString('en-US',{hour12:false}),1000);

// ── Toast ──────────────────────────────────────────────────────────────────
let toastTmr;
function toast(msg,cls='alert-ok'){
  const el=document.getElementById('toast');
  el.textContent=msg; el.className='toast show '+cls;
  clearTimeout(toastTmr); toastTmr=setTimeout(()=>el.className='toast',3500);
}

// ── Helpers ────────────────────────────────────────────────────────────────
const f=(v,d=2)=>v!=null?Number(v).toFixed(d):'—';
function badge(s){
  const m={RUNNING:'badge-running',IDLE:'badge-idle',BATTERY:'badge-battery',FAULT:'badge-fault'};
  return `<span class="badge ${m[s]||'badge-idle'}">${s}</span>`;
}
function yn(v,cls){return v?`<span class="${cls}">YES</span>`:`<span class="no-mark">—</span>`;}

// Highlight key phrases in AI text
function highlightAI(text) {
  return text
    .replace(/\b(met|good|excellent|normal|healthy|optimal|restored|saved)\b/gi,
      '<span class="ai-highlight-good">$1</span>')
    .replace(/\b(warning|caution|attention|monitor|check|unusual|elevated|high)\b/gi,
      '<span class="ai-highlight-warn">$1</span>')
    .replace(/\b(fault|fail|error|critical|missed|below|cut|outage|overc\w+)\b/gi,
      '<span class="ai-highlight-bad">$1</span>');
}

// ══════════════════════════════════════════════════════════════════════════
//  LLM / AI ENGINE
// ══════════════════════════════════════════════════════════════════════════

let llmOnline = false;

// Check LLM status on load and every 30s
async function checkLLMStatus() {
  try {
    const s = await fetch('/api/llm/status').then(r=>r.json());
    llmOnline = s.connected;
    const badge = document.getElementById('llmBadge');
    if (s.connected) {
      badge.textContent = `🤖 ${s.model}`;
      badge.className   = 'llm-badge ok';
      badge.title       = `Connected to ${s.url}\nModel: ${s.model}`;
    } else {
      badge.textContent = '🤖 OFFLINE';
      badge.className   = 'llm-badge err';
      badge.title       = `Cannot reach ${s.url}\nUpdate OLLAMA_URL in config.py`;
    }
  } catch { llmOnline=false; }
}

/**
 * Core AI interpret function.
 * @param {string} endpoint   - e.g. 'live', 'daily', 'weekly', 'monthly'
 * @param {object|null} data  - row data to send, or null to use server latest
 * @param {string} bodyId     - id of .ai-body div to write result into
 * @param {string} footerId   - id of .ai-footer div
 * @param {string} panelId    - id of .ai-panel div (for state classes)
 * @param {HTMLElement} btn   - the button that triggered this
 */
async function aiInterpret(endpoint, data, bodyId, footerId, panelId, btn) {
  if (!llmOnline) {
    showAIError(bodyId, panelId,
      'Ollama server is offline. Paste your ngrok URL into config.py and restart Flask.');
    return;
  }

  const panel  = document.getElementById(panelId);
  const body   = document.getElementById(bodyId);
  const footer = document.getElementById(footerId);

  // Loading state
  panel.className  = 'ai-panel loading';
  body.innerHTML   = `<div class="ai-spinner"><div class="spinner"></div>Mistral is analyzing…</div>`;
  footer.textContent = '';
  if (btn) { btn.disabled=true; btn.textContent='ANALYZING…'; }

  try {
    const fetchOpts = {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: data ? JSON.stringify(data) : '{}'
    };
    const result = await fetch(`/api/llm/interpret/${endpoint}`, fetchOpts)
                         .then(r=>r.json());

    if (result.success) {
      panel.className = 'ai-panel done';
      body.innerHTML  = `<div class="ai-text">${highlightAI(result.interpretation)}</div>`;
      footer.textContent = `Model: ${result.model} · ${new Date().toLocaleTimeString()}`;
    } else {
      showAIError(bodyId, panelId, result.error || 'Unknown error from Mistral.');
    }
  } catch(e) {
    showAIError(bodyId, panelId, `Network error: ${e.message}`);
  } finally {
    if (btn) { btn.disabled=false; btn.textContent=btn.dataset.label||'ANALYZE'; }
  }
}

function showAIError(bodyId, panelId, msg) {
  document.getElementById(panelId).className = 'ai-panel error';
  document.getElementById(bodyId).innerHTML  =
    `<div class="ai-error">⚠ ${msg}</div>`;
}

// ── Button wiring ─────────────────────────────────────────────────────────

// DAILY
let lastDailyRow = null;
const btnDaily = document.getElementById('btnInterpretDaily');
btnDaily.dataset.label = 'ANALYZE LATEST DAY';
btnDaily.onclick = () => aiInterpret('daily', lastDailyRow, 'aiBodyDaily', 'aiFooterDaily', 'aiPanelDaily', btnDaily);

// WEEKLY
let lastWeeklyRow = null;
const btnWeekly = document.getElementById('btnInterpretWeekly');
btnWeekly.dataset.label = 'ANALYZE LATEST WEEK';
btnWeekly.onclick = () => aiInterpret('weekly', lastWeeklyRow, 'aiBodyWeekly', 'aiFooterWeekly', 'aiPanelWeekly', btnWeekly);

// MONTHLY
let lastMonthlyRow = null;
const btnMonthly = document.getElementById('btnInterpretMonthly');
btnMonthly.dataset.label = 'ANALYZE LATEST MONTH';
btnMonthly.onclick = () => aiInterpret('monthly', lastMonthlyRow, 'aiBodyMonthly', 'aiFooterMonthly', 'aiPanelMonthly', btnMonthly);

// ── Modal (row-level AI analysis) ─────────────────────────────────────────
const modalOverlay = document.getElementById('modalOverlay');
document.getElementById('modalClose').onclick = () => modalOverlay.classList.remove('open');
modalOverlay.addEventListener('click', e => { if(e.target===modalOverlay) modalOverlay.classList.remove('open'); });

async function openRowModal(type, data, metaHtml) {
  document.getElementById('modalTitle').textContent = `AI ANALYSIS — ${type.toUpperCase()}`;
  document.getElementById('modalMeta').innerHTML    = metaHtml;
  document.getElementById('modalBody').innerHTML    =
    `<div class="ai-spinner"><div class="spinner"></div>Mistral is analyzing…</div>`;
  modalOverlay.classList.add('open');

  try {
    const r = await fetch(`/api/llm/interpret/${type}`,{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(data)
    }).then(r=>r.json());

    if (r.success) {
      document.getElementById('modalBody').innerHTML =
        `<div class="ai-text">${highlightAI(r.interpretation)}</div>
         <div style="margin-top:14px;font-family:'Share Tech Mono',monospace;font-size:9px;color:var(--muted)">
           Model: ${r.model} · ${new Date().toLocaleTimeString()}</div>`;
    } else {
      document.getElementById('modalBody').innerHTML =
        `<div class="ai-error">⚠ ${r.error}</div>`;
    }
  } catch(e) {
    document.getElementById('modalBody').innerHTML =
      `<div class="ai-error">⚠ Network error: ${e.message}</div>`;
  }
}

// ── KPI update ─────────────────────────────────────────────────────────────
let prevStatus='', latestReading=null;
function updateKPIs(d) {
  if(!d) return; latestReading=d;
  document.getElementById('kpi-voltage').textContent=f(d.voltage_v,1);
  document.getElementById('kpi-current').textContent=f(d.current_a,3);
  document.getElementById('kpi-power').textContent  =f(d.power_w,1);
  document.getElementById('kpi-energy').textContent =f(d.energy_kwh,4);
  const sb=(id,p)=>document.getElementById(id).style.width=Math.min(p,100)+'%';
  sb('bar-v',((d.voltage_v-200)/40)*100); sb('bar-a',(d.current_a/5)*100);
  sb('bar-w',(d.power_w/1000)*100);       sb('bar-e',((d.energy_kwh%10)/10)*100);
  const se=document.getElementById('kpi-status');
  se.textContent=d.pump_status;
  se.className='kpi-value '+({RUNNING:'green',IDLE:'',BATTERY:'yellow',FAULT:'red'}[d.pump_status]||'');
  document.getElementById('kpi-avail').textContent=`AVAIL: ${f(d.availability_pct,1)}%`;
  document.getElementById('card-status').className='kpi-card '+(d.fault_detected?'fault':d.power_cut?'cut':'ok');
  if(d.pump_status!==prevStatus){
    if(d.pump_status==='FAULT')   toast('⚠ FAULT — Check pump current!','alert-fault');
    if(d.pump_status==='BATTERY') toast('⚡ POWER CUT — Battery backup active','alert-cut');
    if(d.pump_status==='RUNNING'&&prevStatus==='BATTERY') toast('✅ Grid power restored','alert-ok');
    prevStatus=d.pump_status;
  }
  const cb=document.getElementById('connStatus');
  cb.textContent='LIVE'; cb.className='conn-badge ok';
}

// ── Live charts ────────────────────────────────────────────────────────────
function updateLive(rows){
  const labels=rows.map(r=>r.timestamp.slice(11,19));
  const upd=(ch,field,d=1)=>{ch.data.labels=labels;ch.data.datasets[0].data=rows.map(r=>+Number(r[field]).toFixed(d));ch.update('none');};
  upd(C.voltage,'voltage_v',1);upd(C.current,'current_a',3);upd(C.power,'power_w',1);upd(C.energy,'energy_kwh',4);
}

// ── Per-second table ───────────────────────────────────────────────────────
let psPage=1,psPages=1;
function renderPS(data){
  document.getElementById('psBody').innerHTML=data.map(r=>`
    <tr class="${r.fault_detected?'row-fault':r.power_cut?'row-cut':''}">
      <td>${r.id}</td><td>${r.timestamp.slice(5)}</td>
      <td>${f(r.voltage_v,1)}</td><td>${f(r.current_a,3)}</td><td>${f(r.power_w,1)}</td>
      <td class="hide-mobile">${f(r.energy_kwh,4)}</td>
      <td>${badge(r.pump_status)}</td>
      <td class="hide-mobile">${yn(r.fault_detected,'yes-fault')}</td>
      <td class="hide-mobile">${yn(r.power_cut,'yes-cut')}</td>
      <td>${f(r.availability_pct,1)}</td>
    </tr>`).join('');
}
async function loadPS(page=1){
  const j=await fetch(`/api/per_second?page=${page}&limit=100`).then(r=>r.json());
  psPage=j.page;psPages=j.pages;renderPS(j.data);
  document.getElementById('psInfo').textContent=`${j.total.toLocaleString()} readings`;
  document.getElementById('pgLabel').textContent=`${psPage}/${psPages}`;
}
document.getElementById('pgPrev').onclick=()=>{if(psPage>1)loadPS(psPage-1);};
document.getElementById('pgNext').onclick=()=>{if(psPage<psPages)loadPS(psPage+1);};

// ── Daily ──────────────────────────────────────────────────────────────────
function renderDaily(rows){
  if(!rows.length) return;
  lastDailyRow = rows[rows.length-1];   // most recent for AI button
  C.daily.data.labels=rows.map(r=>r.date.slice(5));
  C.daily.data.datasets[0].data=rows.map(r=>+Number(r.total_energy_kwh).toFixed(3));
  C.daily.update();
  document.getElementById('dailyBody').innerHTML=rows.slice().reverse().map(r=>`
    <tr>
      <td>${r.date}</td><td>${f(r.avg_voltage_v,1)}</td>
      <td class="hide-mobile">${f(r.avg_current_a,3)}</td>
      <td>${f(r.total_energy_kwh,3)}</td><td>${f(r.pump_hours,1)}</td>
      <td>${f(r.availability_pct,1)}%</td>
      <td class="hide-mobile">${r.power_cuts??0}</td>
      <td class="hide-mobile">${r.faults??0}</td>
      <td class="hide-mobile">${f(r.energy_saved_kwh,3)}</td>
      <td><button class="ai-row-btn" onclick='openRowModal("daily",${JSON.stringify(r)},
        "Date: <b>${r.date}</b> · Avail: <b>${f(r.availability_pct,1)}%</b> · Cuts: <b>${r.power_cuts??0}</b>")'>🤖</button></td>
    </tr>`).join('');
}

// ── Weekly ─────────────────────────────────────────────────────────────────
function renderWeekly(rows){
  if(!rows.length) return;
  lastWeeklyRow = rows[rows.length-1];
  C.weekly.data.labels=rows.map(r=>r.week);
  C.weekly.data.datasets[0].data=rows.map(r=>+Number(r.availability).toFixed(1));
  C.weekly.update();
  document.getElementById('weeklyBody').innerHTML=rows.slice().reverse().map(r=>`
    <tr>
      <td>${r.week}</td>
      <td class="hide-mobile">${r.week_start}–${r.week_end}</td>
      <td>${f(r.avg_voltage,1)}</td><td>${f(r.total_energy,2)}</td>
      <td>${f(r.pump_hours,1)}</td><td>${f(r.availability,1)}%</td>
      <td class="hide-mobile">${r.power_cuts??0}</td>
      <td class="hide-mobile">${r.faults??0}</td>
      <td><button class="ai-row-btn" onclick='openRowModal("weekly",${JSON.stringify(r)},
        "Week: <b>${r.week}</b> · ${r.week_start} to ${r.week_end} · Avail: <b>${f(r.availability,1)}%</b>")'>🤖</button></td>
    </tr>`).join('');
}

// ── Monthly ────────────────────────────────────────────────────────────────
function renderMonthly(rows){
  if(!rows.length) return;
  lastMonthlyRow = rows[rows.length-1];
  C.monthly.data.labels=rows.map(r=>r.month);
  C.monthly.data.datasets[0].data=rows.map(r=>+Number(r.pump_hours).toFixed(1));
  C.monthly.update();
  document.getElementById('monthlyBody').innerHTML=rows.slice().reverse().map(r=>`
    <tr>
      <td>${r.month}</td>
      <td class="hide-mobile">${r.days_recorded}</td>
      <td>${f(r.avg_voltage,1)}</td><td>${f(r.total_energy,2)}</td>
      <td>${f(r.pump_hours,1)}</td><td>${f(r.availability,1)}%</td>
      <td class="hide-mobile">${r.power_cuts??0}</td>
      <td class="hide-mobile">${r.faults??0}</td>
      <td><button class="ai-row-btn" onclick='openRowModal("monthly",${JSON.stringify(r)},
        "Month: <b>${r.month}</b> · ${r.days_recorded} days · Avail: <b>${f(r.availability,1)}%</b>")'>🤖</button></td>
    </tr>`).join('');
}

// ── Tab switching ──────────────────────────────────────────────────────────
function switchTab(tabName){
  document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
  document.querySelectorAll('.tab,.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tabName));
  document.getElementById('tab-'+tabName).classList.add('active');
  setTimeout(()=>Object.values(C).forEach(c=>c.resize()),50);
  if(tabName==='persecond') loadPS(1);
  if(['daily','weekly','monthly'].includes(tabName)) loadAgg();
}
document.querySelectorAll('.tab,.nav-btn').forEach(btn=>btn.addEventListener('click',()=>switchTab(btn.dataset.tab)));

// ── Polling ────────────────────────────────────────────────────────────────
async function pollLive(){
  try{
    const [rows,latest]=await Promise.all([
      fetch('/api/live?limit=60').then(r=>r.json()),
      fetch('/api/latest').then(r=>r.json())
    ]);
    updateKPIs(latest); updateLive(rows);
  } catch{
    const cb=document.getElementById('connStatus');
    cb.textContent='OFFLINE'; cb.className='conn-badge err';
  }
}

async function loadAgg(){
  try{
    const [daily,weekly,monthly]=await Promise.all([
      fetch('/api/daily').then(r=>r.json()),
      fetch('/api/weekly').then(r=>r.json()),
      fetch('/api/monthly').then(r=>r.json()),
    ]);
    renderDaily(daily);renderWeekly(weekly);renderMonthly(monthly);
  } catch(e){console.error(e);}
}

// ── Start ──────────────────────────────────────────────────────────────────
checkLLMStatus();
setInterval(checkLLMStatus, 30000);

pollLive();
loadAgg();
setInterval(pollLive, 1000);
setInterval(loadAgg, 30000);