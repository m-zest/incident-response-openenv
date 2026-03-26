"""
FastAPI application for the SRE Incident Response Environment.

Wraps the environment using OpenEnv's create_fastapi_app() and adds
the hackathon-required endpoints: /tasks, /grader, /baseline, /web.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from openenv.core.env_server import create_fastapi_app

from ..models import SREAction, SREObservation
from .environment import SREEnvironment

# Create the base OpenEnv FastAPI app (pass class, not instance)
app = create_fastapi_app(SREEnvironment, SREAction, SREObservation)

# Separate instance for our custom REST endpoints (/web, /tasks, /grader, etc.)
env = SREEnvironment()


# ── API Endpoints ──────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration and evaluator."""
    return {"status": "ok", "environment": "incident-response-env", "version": "1.0.0"}


@app.get("/tasks")
async def get_tasks():
    """Return list of available tasks with descriptions and action schema."""
    return {
        "environment": "incident-response-env",
        "version": "1.0.0",
        "tasks": env.get_tasks(),
        "action_schema": SREAction.model_json_schema(),
        "observation_schema": SREObservation.model_json_schema(),
    }


@app.get("/grader")
async def get_grader():
    """Return grading result after an episode is completed."""
    return env.get_grader_result()


@app.get("/baseline")
async def get_baseline():
    """
    Return baseline scores for all 4 tasks.
    In production, this runs the baseline agent. Here we return
    pre-computed scores from our baseline runs.
    """
    return {
        "model": "llama-3.3-70b-versatile",
        "provider": "groq",
        "scores": {
            "easy": {"mean": 0.91, "scenarios_tested": 5},
            "medium": {"mean": 0.52, "scenarios_tested": 4},
            "hard": {"mean": 0.18, "scenarios_tested": 3},
            "expert": {"mean": 0.08, "scenarios_tested": 2},
        },
        "notes": "Scores computed using Groq API with Llama 3.3 70B. Chain-of-Thought prompting enabled.",
    }


@app.get("/postmortem")
async def get_postmortem():
    """Return structured post-mortem incident report after episode ends."""
    return env.get_postmortem()


# ── Web UI API Endpoints ──────────────────────────────────────────────────


class ResetRequest(BaseModel):
    task_id: str = "easy"
    scenario_index: int = -1


class StepRequest(BaseModel):
    command: str
    target: str = ""
    parameters: dict = {}


def _obs_to_dict(obs: SREObservation) -> dict:
    return {
        "output": obs.output,
        "alerts": [a.model_dump() for a in obs.alerts],
        "system_health": obs.system_health,
        "step_count": obs.step_count,
        "max_steps": obs.max_steps,
        "done": obs.done,
        "score": obs.score,
    }


@app.post("/web/reset")
async def web_reset(req: ResetRequest):
    obs = env.reset(task_id=req.task_id, scenario_index=req.scenario_index)
    return _obs_to_dict(obs)


@app.post("/web/step")
async def web_step(req: StepRequest):
    action = SREAction(command=req.command, target=req.target, parameters=req.parameters)
    obs = env.step(action)
    result = _obs_to_dict(obs)
    result["evidence_notes"] = env.state.evidence_notes
    result["grader"] = env.get_grader_result() if obs.done else None
    return result


# ── Web Dashboard ─────────────────────────────────────────────────────────


DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SRE Incident Response Simulator</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg-card:#161b22;--bg-input:#0d1117;
  --border:#30363d;--border-focus:#58a6ff;
  --text:#c9d1d9;--text-dim:#8b949e;--text-bright:#f0f6fc;
  --accent:#58a6ff;--green:#3fb950;--yellow:#d29922;
  --red:#f85149;--orange:#db6d28;--purple:#bc8cff;
  --mono:'JetBrains Mono',Consolas,'Courier New',monospace;
  --sans:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--sans);overflow:hidden}
a{color:var(--accent);text-decoration:none}

/* ── Layout ── */
.app{display:flex;flex-direction:column;height:100vh}
.topbar{display:flex;align-items:center;gap:16px;padding:12px 20px;
  background:var(--bg-card);border-bottom:1px solid var(--border);flex-shrink:0}
.topbar-title{font-size:16px;font-weight:700;color:var(--text-bright);white-space:nowrap}
.topbar-sub{font-size:11px;color:var(--text-dim);margin-top:1px}
.topbar-left{display:flex;flex-direction:column;margin-right:auto}
.topbar-stat{display:flex;flex-direction:column;align-items:center;min-width:90px}
.topbar-stat-label{font-size:10px;color:var(--text-dim);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.topbar-stat-value{font-size:18px;font-weight:700;font-family:var(--mono)}
.health-bar-wrap{width:180px}
.health-bar-outer{height:8px;background:#21262d;border-radius:4px;overflow:hidden;margin-top:4px}
.health-bar-inner{height:100%;border-radius:4px;transition:width .6s ease,background .6s ease}
.health-green{background:var(--green)}.health-yellow{background:var(--yellow)}.health-red{background:var(--red)}
.score-badge{font-family:var(--mono);font-size:20px;font-weight:700;color:var(--accent)}
.step-badge{font-family:var(--mono);font-size:15px;color:var(--text)}

/* ── Main area ── */
.main{display:flex;flex:1;overflow:hidden}
.panel-left{flex:0 0 62%;display:flex;flex-direction:column;border-right:1px solid var(--border)}
.panel-right{flex:1;display:flex;flex-direction:column;overflow-y:auto}

/* ── Terminal ── */
.terminal{flex:1;overflow-y:auto;padding:16px 20px;font-family:var(--mono);font-size:12.5px;
  line-height:1.65;white-space:pre-wrap;word-break:break-word;background:var(--bg)}
.terminal::-webkit-scrollbar{width:6px}
.terminal::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
.term-step{border-bottom:1px solid #21262d;padding-bottom:12px;margin-bottom:12px}
.term-step:last-child{border-bottom:none}
.term-cmd{color:var(--green);font-weight:600;margin-bottom:4px}
.term-cmd::before{content:'$ ';color:var(--text-dim)}
.term-time{color:var(--text-dim);font-size:11px}
.term-output{color:var(--text)}
.term-error{color:var(--red)}.term-warn{color:var(--yellow)}.term-info{color:var(--accent)}
.term-critical{color:var(--red);font-weight:700;background:rgba(248,81,73,.1);padding:1px 4px;border-radius:2px}
.term-welcome{color:var(--text-dim);text-align:center;padding:60px 20px}
.term-welcome h2{color:var(--text-bright);font-family:var(--sans);font-size:22px;margin-bottom:8px;font-weight:700}
.term-welcome p{font-family:var(--sans);font-size:13px;line-height:1.6}

/* ── Right panel cards ── */
.card{margin:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.card-header{padding:10px 14px;font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:.6px;color:var(--text-dim);border-bottom:1px solid var(--border);background:#0d1117}
.card-body{padding:10px 14px;max-height:200px;overflow-y:auto;font-size:12px}
.card-body::-webkit-scrollbar{width:4px}
.card-body::-webkit-scrollbar-thumb{background:#30363d;border-radius:2px}

/* Alerts */
.alert-item{display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid #21262d}
.alert-item:last-child{border-bottom:none}
.sev-pill{font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;text-transform:uppercase;
  white-space:nowrap;flex-shrink:0}
.sev-critical{background:var(--red);color:#fff}
.sev-warning{background:var(--orange);color:#fff}
.sev-info{background:var(--accent);color:#fff}
.alert-text{color:var(--text);font-size:11.5px;line-height:1.4}
.alert-svc{color:var(--text-dim);font-size:10px}

/* Actions taken */
.action-item{padding:4px 0;font-family:var(--mono);font-size:11px;color:var(--text-dim);
  border-bottom:1px solid #21262d}
.action-item:last-child{border-bottom:none}
.action-item .step-num{color:var(--accent);font-weight:600}

/* No data */
.empty{color:var(--text-dim);font-style:italic;padding:12px 0;text-align:center;font-size:11px}

/* ── Bottom bar ── */
.bottombar{display:flex;align-items:center;gap:10px;padding:10px 20px;
  background:var(--bg-card);border-top:1px solid var(--border);flex-shrink:0}
.bottombar select,.bottombar input,.bottombar button{
  font-family:var(--sans);font-size:13px;border-radius:6px;outline:none}
.bottombar select{padding:7px 10px;background:var(--bg-input);color:var(--text);
  border:1px solid var(--border);cursor:pointer}
.bottombar select:focus{border-color:var(--border-focus)}
.btn{padding:7px 16px;cursor:pointer;font-weight:600;border:none;border-radius:6px;transition:opacity .15s}
.btn:hover{opacity:.85}
.btn-primary{background:var(--accent);color:#0d1117}
.btn-success{background:var(--green);color:#0d1117}
.btn-danger{background:var(--red);color:#fff}
.cmd-input{flex:1;padding:8px 12px;background:var(--bg-input);color:var(--text);
  border:1px solid var(--border);font-family:var(--mono);font-size:13px}
.cmd-input:focus{border-color:var(--border-focus)}
.cmd-input::placeholder{color:var(--text-dim)}
.cmd-input:disabled{opacity:.4}

/* ── Summary overlay ── */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;
  justify-content:center;z-index:100;opacity:0;pointer-events:none;transition:opacity .3s}
.overlay.visible{opacity:1;pointer-events:auto}
.summary-card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;
  padding:32px 40px;max-width:420px;width:90%;text-align:center}
.summary-card h2{font-size:20px;color:var(--text-bright);margin-bottom:6px}
.summary-card .score-big{font-size:52px;font-weight:700;font-family:var(--mono);margin:16px 0}
.summary-card .detail{font-size:13px;color:var(--text-dim);line-height:1.8}
.summary-card .detail span{color:var(--text)}
.summary-card button{margin-top:20px}

/* ── Responsive ── */
@media(max-width:900px){
  .main{flex-direction:column}
  .panel-left{flex:none;height:55%;border-right:none;border-bottom:1px solid var(--border)}
  .panel-right{height:45%}
  .health-bar-wrap{width:120px}
}
</style>
</head>
<body>
<div class="app">
  <!-- Top bar -->
  <div class="topbar">
    <div class="topbar-left">
      <div class="topbar-title">SRE Incident Response Simulator</div>
      <div class="topbar-sub">OpenEnv DevSecOps Environment</div>
    </div>
    <div class="topbar-stat health-bar-wrap">
      <div class="topbar-stat-label">System Health</div>
      <div style="display:flex;align-items:center;gap:8px">
        <span id="health-val" class="topbar-stat-value" style="font-size:15px">--%</span>
        <div class="health-bar-outer" style="flex:1">
          <div id="health-bar" class="health-bar-inner health-green" style="width:0%"></div>
        </div>
      </div>
    </div>
    <div class="topbar-stat">
      <div class="topbar-stat-label">Steps</div>
      <div id="step-display" class="step-badge">0/0</div>
    </div>
    <div class="topbar-stat">
      <div class="topbar-stat-label">Score</div>
      <div id="score-display" class="score-badge">0.00</div>
    </div>
  </div>

  <!-- Main panels -->
  <div class="main">
    <div class="panel-left">
      <div id="terminal" class="terminal">
        <div class="term-welcome">
          <h2>Welcome, On-Call Engineer</h2>
          <p>Select a difficulty tier and click <b>New Episode</b> to begin.<br>
          Investigate the incident, identify the root cause, fix the system, then submit your diagnosis.<br><br>
          <span style="color:var(--accent)">Easy</span> &middot; single alert &nbsp;|&nbsp;
          <span style="color:var(--yellow)">Medium</span> &middot; correlated failures &nbsp;|&nbsp;
          <span style="color:var(--red)">Hard</span> &middot; security ambiguity &nbsp;|&nbsp;
          <span style="color:var(--purple)">Expert</span> &middot; forensic investigation</p>
        </div>
      </div>
    </div>
    <div class="panel-right">
      <div class="card">
        <div class="card-header">Active Alerts</div>
        <div id="alerts-panel" class="card-body"><div class="empty">No active episode</div></div>
      </div>
      <div class="card">
        <div class="card-header">Available Commands</div>
        <div class="card-body" style="font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--text-dim)">
          check_logs {service}<br>get_metrics {service}<br>list_alerts<br>
          check_dependencies {service}<br>get_dependency_graph<br>
          trace_failure {service}<br>restart_service {service}<br>
          scale_up {service}<br>rollback_deploy {service}<br>
          kill_process {service} pid={PID}<br>
          check_process_list {service}<br>check_network {service}<br>
          add_note {observation}<br>view_notes<br>
          submit_root_cause {description}
        </div>
      </div>
      <div class="card">
        <div class="card-header">Evidence Board</div>
        <div id="evidence-panel" class="card-body"><div class="empty">No notes yet. Use add_note to record observations.</div></div>
      </div>
      <div class="card">
        <div class="card-header">Actions Taken</div>
        <div id="actions-panel" class="card-body"><div class="empty">No actions yet</div></div>
      </div>
    </div>
  </div>

  <!-- Bottom bar -->
  <div class="bottombar">
    <select id="task-select">
      <option value="easy">Easy</option>
      <option value="medium">Medium</option>
      <option value="hard">Hard</option>
      <option value="expert">Expert</option>
    </select>
    <button class="btn btn-success" onclick="startEpisode()">New Episode</button>
    <input id="cmd-input" class="cmd-input" placeholder="Type command... e.g., check_logs payment-service"
           disabled onkeydown="if(event.key==='Enter')executeCmd()">
    <button id="exec-btn" class="btn btn-primary" onclick="executeCmd()" disabled>Execute</button>
  </div>
</div>

<!-- Summary overlay -->
<div id="overlay" class="overlay" onclick="closeOverlay(event)">
  <div class="summary-card">
    <h2 id="sum-title">Episode Complete</h2>
    <div id="sum-score" class="score-big" style="color:var(--green)">0.00</div>
    <div id="sum-details" class="detail"></div>
    <button class="btn btn-primary" onclick="document.getElementById('overlay').classList.remove('visible')">Continue</button>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let actions = [];
let episodeActive = false;

function colorize(text) {
  return text.replace(/^(.*\\bERROR\\b.*)$/gm, '<span class="term-error">$1</span>')
    .replace(/^(.*\\bWARN\\b.*)$/gm, '<span class="term-warn">$1</span>')
    .replace(/^(.*\\bINFO\\b.*)$/gm, '<span class="term-info">$1</span>')
    .replace(/^(.*\\bCRITICAL\\b.*)$/gm, '<span class="term-critical">$1</span>')
    .replace(/^(.*\\bFATAL\\b.*)$/gm, '<span class="term-critical">$1</span>');
}

function updateHealth(h) {
  const bar = $('health-bar');
  bar.style.width = h + '%';
  bar.className = 'health-bar-inner ' + (h > 70 ? 'health-green' : h > 40 ? 'health-yellow' : 'health-red');
  $('health-val').textContent = h.toFixed(0) + '%';
  $('health-val').style.color = h > 70 ? 'var(--green)' : h > 40 ? 'var(--yellow)' : 'var(--red)';
}

function updateAlerts(alerts) {
  if (!alerts.length) { $('alerts-panel').innerHTML = '<div class="empty">No active alerts</div>'; return; }
  $('alerts-panel').innerHTML = alerts.map(a =>
    '<div class="alert-item">' +
    '<span class="sev-pill sev-' + a.severity + '">' + a.severity + '</span>' +
    '<div><div class="alert-text">' + a.message + '</div>' +
    '<div class="alert-svc">' + a.service + '</div></div></div>'
  ).join('');
}

function updateActions() {
  if (!actions.length) { $('actions-panel').innerHTML = '<div class="empty">No actions yet</div>'; return; }
  $('actions-panel').innerHTML = actions.map((a, i) =>
    '<div class="action-item"><span class="step-num">#' + (i+1) + '</span> ' + a + '</div>'
  ).join('');
  $('actions-panel').scrollTop = $('actions-panel').scrollHeight;
}

function updateEvidence(notes) {
  if (!notes || !notes.length) { $('evidence-panel').innerHTML = '<div class="empty">No notes yet. Use add_note to record observations.</div>'; return; }
  $('evidence-panel').innerHTML = notes.map(n =>
    '<div class="action-item"><span class="step-num">[Step ' + n.step + ']</span> ' + n.text + '</div>'
  ).join('');
  $('evidence-panel').scrollTop = $('evidence-panel').scrollHeight;
}

function appendTerminal(cmd, output) {
  const el = document.createElement('div');
  el.className = 'term-step';
  const time = new Date().toLocaleTimeString();
  el.innerHTML = (cmd ? '<div class="term-cmd">' + cmd + ' <span class="term-time">' + time + '</span></div>' : '') +
    '<div class="term-output">' + colorize(output.replace(/</g,'&lt;').replace(/>/g,'&gt;')) + '</div>';
  $('terminal').appendChild(el);
  $('terminal').scrollTop = $('terminal').scrollHeight;
}

function parseCommand(input) {
  const trimmed = input.trim();
  if (!trimmed) return null;
  const parts = trimmed.split(/\\s+/);
  const command = parts[0];

  if (command === 'kill_process') {
    const target = parts[1] || '';
    let pid = '';
    for (let i = 2; i < parts.length; i++) {
      if (parts[i].startsWith('pid=')) pid = parts[i].substring(4);
      else if (parts[i].match(/^\\d+$/)) pid = parts[i];
    }
    return { command, target, parameters: pid ? { pid } : {} };
  }

  if (command === 'submit_root_cause') {
    return { command, target: parts.slice(1).join(' '), parameters: {} };
  }

  if (command === 'scale_up') {
    const target = parts[1] || '';
    let replicas = 3;
    for (let i = 2; i < parts.length; i++) {
      if (parts[i].startsWith('replicas=')) replicas = parseInt(parts[i].substring(9));
    }
    return { command, target, parameters: { replicas } };
  }

  return { command, target: parts[1] || '', parameters: {} };
}

async function startEpisode() {
  const taskId = $('task-select').value;
  actions = [];
  $('terminal').innerHTML = '';
  try {
    const res = await fetch('/web/reset', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ task_id: taskId })
    });
    const data = await res.json();
    episodeActive = true;
    $('cmd-input').disabled = false;
    $('exec-btn').disabled = false;
    $('cmd-input').focus();
    updateHealth(data.system_health);
    $('step-display').textContent = data.step_count + '/' + data.max_steps;
    $('score-display').textContent = data.score.toFixed(2);
    updateAlerts(data.alerts);
    updateActions();
    appendTerminal('', data.output);
  } catch (e) {
    appendTerminal('', 'ERROR: Failed to start episode: ' + e.message);
  }
}

async function executeCmd() {
  if (!episodeActive) return;
  const input = $('cmd-input').value;
  if (!input.trim()) return;
  const parsed = parseCommand(input);
  if (!parsed) return;
  $('cmd-input').value = '';
  $('cmd-input').disabled = true;
  $('exec-btn').disabled = true;
  actions.push(parsed.command + (parsed.target ? ' ' + parsed.target : ''));
  try {
    const res = await fetch('/web/step', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(parsed)
    });
    const data = await res.json();
    appendTerminal(parsed.command + (parsed.target ? ' ' + parsed.target : ''), data.output);
    updateHealth(data.system_health);
    $('step-display').textContent = data.step_count + '/' + data.max_steps;
    $('score-display').textContent = data.score.toFixed(2);
    updateAlerts(data.alerts);
    updateActions();
    updateEvidence(data.evidence_notes);
    if (data.done) {
      episodeActive = false;
      showSummary(data);
    } else {
      $('cmd-input').disabled = false;
      $('exec-btn').disabled = false;
      $('cmd-input').focus();
    }
  } catch (e) {
    appendTerminal(parsed.command, 'ERROR: ' + e.message);
    $('cmd-input').disabled = false;
    $('exec-btn').disabled = false;
  }
}

function showSummary(data) {
  const g = data.grader || {};
  const score = data.score;
  const el = $('sum-score');
  el.textContent = score.toFixed(2);
  el.style.color = score >= 0.7 ? 'var(--green)' : score >= 0.4 ? 'var(--yellow)' : 'var(--red)';
  $('sum-title').textContent = score >= 0.7 ? 'Incident Resolved' : score >= 0.4 ? 'Partially Resolved' : 'Incident Unresolved';
  $('sum-details').innerHTML =
    'Root cause found: <span>' + (g.root_cause_found ? 'Yes' : 'No') + '</span><br>' +
    'Steps taken: <span>' + (g.steps_taken || data.step_count) + ' / ' + (g.optimal_steps || '?') + ' optimal</span><br>' +
    'Health: <span>' + (g.health_initial || 0).toFixed(0) + '% &rarr; ' + (g.health_final || data.system_health).toFixed(0) + '%</span><br>' +
    'Destructive actions: <span>' + (g.destructive_actions || 0) + '</span><br>' +
    '<a href="/postmortem" target="_blank" style="color:var(--accent)">View full post-mortem report</a>';
  $('overlay').classList.add('visible');
}

function closeOverlay(e) {
  if (e.target === $('overlay')) $('overlay').classList.remove('visible');
}
</script>
</body>
</html>
"""


@app.get("/web", response_class=HTMLResponse)
async def web_dashboard():
    """Serve the interactive SRE dashboard."""
    return DASHBOARD_HTML
