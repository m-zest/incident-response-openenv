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
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#06090f;--bg-elevated:#0c1018;--bg-card:#111822;--bg-card-hover:#161e2a;
  --bg-input:#0a0f18;--bg-surface:rgba(17,24,34,.65);
  --border:rgba(56,68,90,.45);--border-subtle:rgba(56,68,90,.25);--border-focus:#3b82f6;
  --text:#c9d1d9;--text-dim:#6b7b8d;--text-bright:#e6edf3;--text-muted:#4a5568;
  --accent:#3b82f6;--accent-glow:rgba(59,130,246,.35);
  --cyan:#22d3ee;--cyan-glow:rgba(34,211,238,.25);
  --green:#34d399;--green-dim:rgba(52,211,153,.15);
  --yellow:#fbbf24;--yellow-dim:rgba(251,191,36,.12);
  --red:#ef4444;--red-dim:rgba(239,68,68,.12);--red-glow:rgba(239,68,68,.3);
  --orange:#f97316;--purple:#a78bfa;--purple-glow:rgba(167,139,250,.2);
  --glass:rgba(17,24,34,.55);--glass-border:rgba(255,255,255,.06);
  --mono:'JetBrains Mono',Consolas,'Courier New',monospace;
  --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --radius:10px;--radius-lg:14px;--radius-sm:6px;
}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--sans);overflow:hidden;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
::selection{background:var(--accent-glow);color:var(--text-bright)}

@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse-red{0%,100%{box-shadow:0 0 0 0 var(--red-glow)}50%{box-shadow:0 0 8px 3px var(--red-glow)}}
@keyframes glow-score{0%,100%{text-shadow:0 0 12px var(--cyan-glow)}50%{text-shadow:0 0 24px var(--cyan-glow),0 0 48px rgba(34,211,238,.1)}}

/* ── Layout ── */
.app{display:flex;flex-direction:column;height:100vh}

/* ── Top bar ── */
.topbar{display:flex;align-items:center;gap:20px;padding:10px 24px;
  background:var(--bg-elevated);border-bottom:1px solid var(--border-subtle);flex-shrink:0;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}
.topbar-left{display:flex;align-items:center;gap:14px;margin-right:auto}
.topbar-logo{width:32px;height:32px;border-radius:8px;
  background:linear-gradient(135deg,#3b82f6,#8b5cf6);
  display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;
  color:#fff;flex-shrink:0;box-shadow:0 2px 8px rgba(59,130,246,.3)}
.topbar-text{}
.topbar-title{font-size:14px;font-weight:600;color:var(--text-bright);letter-spacing:-.2px}
.topbar-sub{font-size:10px;color:var(--text-dim);margin-top:1px;letter-spacing:.3px}

.topbar-metrics{display:flex;align-items:center;gap:24px}
.metric{display:flex;flex-direction:column;align-items:center;gap:4px}
.metric-label{font-size:9px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.8px}

/* Radial health ring */
.health-ring{position:relative;width:48px;height:48px}
.health-ring svg{transform:rotate(-90deg)}
.health-ring circle{fill:none;stroke-width:4;stroke-linecap:round}
.health-ring .ring-bg{stroke:rgba(255,255,255,.06)}
.health-ring .ring-fg{transition:stroke-dashoffset .8s ease,stroke .5s ease}
.health-ring-val{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:11px;font-weight:700}

/* Score with glow */
.score-val{font-family:var(--mono);font-size:22px;font-weight:700;color:var(--cyan);
  animation:glow-score 3s ease-in-out infinite}
.step-val{font-family:var(--mono);font-size:14px;font-weight:600;color:var(--text)}

/* ── Main area ── */
.main{display:flex;flex:1;overflow:hidden}
.panel-left{flex:0 0 62%;display:flex;flex-direction:column;
  border-right:1px solid var(--border-subtle)}
.panel-right{flex:1;display:flex;flex-direction:column;overflow-y:auto;
  background:var(--bg);padding:8px}
.panel-right::-webkit-scrollbar{width:5px}
.panel-right::-webkit-scrollbar-thumb{background:rgba(255,255,255,.08);border-radius:3px}

/* ── Terminal ── */
.terminal-wrap{flex:1;display:flex;flex-direction:column;overflow:hidden;
  margin:8px;margin-right:0;border-radius:var(--radius-lg);
  background:var(--bg);border:1px solid var(--border-subtle);
  box-shadow:inset 0 2px 12px rgba(0,0,0,.4)}
.terminal-titlebar{display:flex;align-items:center;gap:6px;padding:10px 16px;
  border-bottom:1px solid var(--border-subtle);flex-shrink:0}
.terminal-dot{width:10px;height:10px;border-radius:50%}
.dot-red{background:#ef4444}.dot-yellow{background:#fbbf24}.dot-green{background:#34d399}
.terminal-titlebar-text{font-size:11px;color:var(--text-muted);margin-left:8px;font-family:var(--mono)}
.terminal{flex:1;overflow-y:auto;padding:16px 20px;font-family:var(--mono);font-size:12px;
  line-height:1.7;white-space:pre-wrap;word-break:break-word}
.terminal::-webkit-scrollbar{width:5px}
.terminal::-webkit-scrollbar-thumb{background:rgba(255,255,255,.06);border-radius:3px}
.term-step{padding-bottom:14px;margin-bottom:14px;border-bottom:1px solid rgba(255,255,255,.04);
  animation:fadeIn .25s ease}
.term-step:last-child{border-bottom:none}
.term-cmd{color:var(--cyan);font-weight:600;margin-bottom:5px}
.term-cmd::before{content:'> ';color:var(--text-muted)}
.term-time{color:var(--text-muted);font-size:10px;margin-left:8px}
.term-output{color:var(--text)}
.term-error{color:var(--red);font-weight:500}
.term-warn{color:var(--yellow)}
.term-info{color:var(--accent)}
.term-critical{color:#ff6b6b;font-weight:700;background:var(--red-dim);
  padding:1px 5px;border-radius:3px;border-left:2px solid var(--red)}
.term-welcome{color:var(--text-dim);text-align:center;padding:80px 30px}
.term-welcome h2{color:var(--text-bright);font-family:var(--sans);font-size:24px;
  margin-bottom:10px;font-weight:700;letter-spacing:-.3px}
.term-welcome p{font-family:var(--sans);font-size:13px;line-height:1.7;max-width:480px;margin:0 auto}
.term-welcome .tiers{margin-top:16px;display:flex;justify-content:center;gap:16px;flex-wrap:wrap}
.tier-tag{font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px;
  border:1px solid var(--border)}
.tier-easy{color:var(--green);border-color:rgba(52,211,153,.3);background:var(--green-dim)}
.tier-medium{color:var(--yellow);border-color:rgba(251,191,36,.3);background:var(--yellow-dim)}
.tier-hard{color:var(--red);border-color:rgba(239,68,68,.3);background:var(--red-dim)}
.tier-expert{color:var(--purple);border-color:rgba(167,139,250,.3);background:var(--purple-glow)}

/* ── Cards ── */
.card{background:var(--bg-card);border:1px solid var(--glass-border);border-radius:var(--radius);
  overflow:hidden;margin-bottom:8px;backdrop-filter:blur(8px);
  transition:border-color .2s}
.card:hover{border-color:var(--border)}
.card-header{padding:10px 14px;font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.7px;color:var(--text-muted);border-bottom:1px solid var(--glass-border);
  display:flex;align-items:center;gap:6px}
.card-header-icon{font-size:13px}
.card-body{padding:10px 14px;max-height:180px;overflow-y:auto;font-size:12px}
.card-body::-webkit-scrollbar{width:3px}
.card-body::-webkit-scrollbar-thumb{background:rgba(255,255,255,.06);border-radius:2px}

/* Alerts */
.alert-item{display:flex;align-items:flex-start;gap:8px;padding:7px 0;
  border-bottom:1px solid rgba(255,255,255,.03);animation:fadeIn .2s ease}
.alert-item:last-child{border-bottom:none}
.sev-pill{font-size:9px;font-weight:700;padding:3px 8px;border-radius:20px;text-transform:uppercase;
  white-space:nowrap;flex-shrink:0;letter-spacing:.3px}
.sev-critical{background:var(--red-dim);color:var(--red);border:1px solid rgba(239,68,68,.25);
  animation:pulse-red 2s infinite}
.sev-warning{background:var(--yellow-dim);color:var(--yellow);border:1px solid rgba(251,191,36,.2)}
.sev-info{background:rgba(59,130,246,.12);color:var(--accent);border:1px solid rgba(59,130,246,.2)}
.alert-text{color:var(--text);font-size:11px;line-height:1.45}
.alert-svc{color:var(--text-muted);font-size:10px;font-family:var(--mono);margin-top:1px}

/* Command list */
.cmd-list-item{padding:4px 8px;font-family:var(--mono);font-size:10.5px;color:var(--text-dim);
  border-radius:var(--radius-sm);transition:background .15s;cursor:default;line-height:1.7}
.cmd-list-item:hover{background:rgba(255,255,255,.04);color:var(--text)}
.cmd-list-item .cmd-name{color:var(--cyan);font-weight:500}
.cmd-list-item .cmd-arg{color:var(--text-muted)}

/* Actions & evidence */
.action-item{padding:5px 0;font-family:var(--mono);font-size:11px;color:var(--text-dim);
  border-bottom:1px solid rgba(255,255,255,.03);animation:fadeIn .2s ease}
.action-item:last-child{border-bottom:none}
.action-item .step-num{color:var(--accent);font-weight:600}
.empty{color:var(--text-muted);font-style:normal;padding:16px 0;text-align:center;font-size:11px}

/* ── Bottom bar (Command Palette) ── */
.bottombar{display:flex;align-items:center;gap:10px;padding:12px 24px;
  background:var(--bg-elevated);border-top:1px solid var(--border-subtle);flex-shrink:0;
  backdrop-filter:blur(12px)}
.bottombar select,.bottombar input,.bottombar button{
  font-family:var(--sans);font-size:13px;outline:none}

.task-pill{padding:8px 14px;background:var(--bg-input);color:var(--text);
  border:1px solid var(--border);border-radius:20px;cursor:pointer;font-weight:500;
  -webkit-appearance:none;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236b7b8d'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 10px center;padding-right:28px}
.task-pill:focus{border-color:var(--border-focus)}

.btn{padding:8px 18px;cursor:pointer;font-weight:600;border:none;border-radius:20px;
  transition:all .2s ease;font-size:13px}
.btn:hover{transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn-new{background:linear-gradient(135deg,#34d399,#059669);color:#fff;
  box-shadow:0 2px 8px rgba(52,211,153,.25)}
.btn-new:hover{box-shadow:0 4px 16px rgba(52,211,153,.35)}
.btn-exec{background:linear-gradient(135deg,#3b82f6,#7c3aed);color:#fff;
  box-shadow:0 2px 8px rgba(99,102,241,.25)}
.btn-exec:hover{box-shadow:0 4px 16px rgba(99,102,241,.4)}
.btn-exec:disabled,.btn-exec:disabled:hover{opacity:.3;cursor:not-allowed;
  transform:none;box-shadow:none}

.cmd-input{flex:1;padding:10px 16px;background:var(--bg-input);color:var(--text);
  border:1px solid var(--border);border-radius:var(--radius);
  font-family:var(--mono);font-size:13px;transition:border-color .2s,box-shadow .2s}
.cmd-input:focus{border-color:var(--border-focus);
  box-shadow:0 0 0 3px var(--accent-glow)}
.cmd-input::placeholder{color:var(--text-muted)}
.cmd-input:disabled{opacity:.3}

/* ── Summary overlay ── */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(8px);
  display:flex;align-items:center;justify-content:center;z-index:100;
  opacity:0;pointer-events:none;transition:opacity .3s}
.overlay.visible{opacity:1;pointer-events:auto}
.summary-card{background:var(--bg-card);border:1px solid var(--glass-border);
  border-radius:var(--radius-lg);padding:36px 44px;max-width:440px;width:92%;
  text-align:center;box-shadow:0 24px 64px rgba(0,0,0,.5);animation:fadeIn .3s ease}
.summary-card h2{font-size:18px;color:var(--text-bright);margin-bottom:4px;font-weight:600}
.summary-card .score-big{font-size:56px;font-weight:700;font-family:var(--mono);margin:20px 0;
  letter-spacing:-2px}
.summary-card .detail{font-size:12px;color:var(--text-dim);line-height:2}
.summary-card .detail span{color:var(--text);font-weight:500}
.summary-card .detail a{color:var(--accent);font-weight:500}
.summary-card button{margin-top:24px}

/* ── Responsive ── */
@media(max-width:900px){
  .main{flex-direction:column}
  .panel-left{flex:none;height:55%;border-right:none;border-bottom:1px solid var(--border-subtle)}
  .panel-right{height:45%}
  .topbar-metrics{gap:14px}
}
</style>
</head>
<body>
<div class="app">
  <!-- Top bar -->
  <div class="topbar">
    <div class="topbar-left">
      <div class="topbar-logo">SR</div>
      <div class="topbar-text">
        <div class="topbar-title">SRE Incident Response Simulator</div>
        <div class="topbar-sub">OpenEnv DevSecOps Environment</div>
      </div>
    </div>
    <div class="topbar-metrics">
      <div class="metric">
        <div class="metric-label">Health</div>
        <div class="health-ring">
          <svg width="48" height="48" viewBox="0 0 48 48">
            <circle class="ring-bg" cx="24" cy="24" r="20"/>
            <circle id="health-ring-fg" class="ring-fg" cx="24" cy="24" r="20"
              stroke="var(--green)" stroke-dasharray="125.66" stroke-dashoffset="125.66"/>
          </svg>
          <div id="health-val" class="health-ring-val" style="color:var(--text-muted)">--%</div>
        </div>
      </div>
      <div class="metric">
        <div class="metric-label">Steps</div>
        <div id="step-display" class="step-val">0/0</div>
      </div>
      <div class="metric">
        <div class="metric-label">Score</div>
        <div id="score-display" class="score-val">0.00</div>
      </div>
    </div>
  </div>

  <!-- Main panels -->
  <div class="main">
    <div class="panel-left">
      <div class="terminal-wrap">
        <div class="terminal-titlebar">
          <div class="terminal-dot dot-red"></div>
          <div class="terminal-dot dot-yellow"></div>
          <div class="terminal-dot dot-green"></div>
          <span class="terminal-titlebar-text">incident-response -- bash</span>
        </div>
        <div id="terminal" class="terminal">
          <div class="term-welcome">
            <h2>Welcome, On-Call Engineer</h2>
            <p>Select a difficulty tier and click <b>New Episode</b> to begin.
            Investigate the incident, identify the root cause, fix the system, then submit your diagnosis.</p>
            <div class="tiers">
              <span class="tier-tag tier-easy">Easy</span>
              <span class="tier-tag tier-medium">Medium</span>
              <span class="tier-tag tier-hard">Hard</span>
              <span class="tier-tag tier-expert">Expert</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="panel-right">
      <div class="card">
        <div class="card-header"><span class="card-header-icon">&#9888;</span> Active Alerts</div>
        <div id="alerts-panel" class="card-body"><div class="empty">No active episode</div></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-icon">&#9881;</span> Commands</div>
        <div class="card-body" style="max-height:none;padding:6px 8px">
          <div class="cmd-list-item"><span class="cmd-name">check_logs</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">get_metrics</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">list_alerts</span></div>
          <div class="cmd-list-item"><span class="cmd-name">check_dependencies</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">get_dependency_graph</span></div>
          <div class="cmd-list-item"><span class="cmd-name">trace_failure</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">restart_service</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">scale_up</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">rollback_deploy</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">kill_process</span> <span class="cmd-arg">{service} pid={PID}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">check_process_list</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">check_network</span> <span class="cmd-arg">{service}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">add_note</span> <span class="cmd-arg">{observation}</span></div>
          <div class="cmd-list-item"><span class="cmd-name">view_notes</span></div>
          <div class="cmd-list-item"><span class="cmd-name">submit_root_cause</span> <span class="cmd-arg">{description}</span></div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-icon">&#128270;</span> Evidence Board</div>
        <div id="evidence-panel" class="card-body"><div class="empty">No notes yet</div></div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-header-icon">&#9654;</span> Actions Taken</div>
        <div id="actions-panel" class="card-body"><div class="empty">No actions yet</div></div>
      </div>
    </div>
  </div>

  <!-- Bottom bar -->
  <div class="bottombar">
    <select id="task-select" class="task-pill">
      <option value="easy">Easy</option>
      <option value="medium">Medium</option>
      <option value="hard">Hard</option>
      <option value="expert">Expert</option>
    </select>
    <button class="btn btn-new" onclick="startEpisode()">New Episode</button>
    <input id="cmd-input" class="cmd-input" placeholder="Type command... e.g., check_logs payment-service"
           disabled onkeydown="if(event.key==='Enter')executeCmd()">
    <button id="exec-btn" class="btn btn-exec" onclick="executeCmd()" disabled>Execute</button>
  </div>
</div>

<!-- Summary overlay -->
<div id="overlay" class="overlay" onclick="closeOverlay(event)">
  <div class="summary-card">
    <h2 id="sum-title">Episode Complete</h2>
    <div id="sum-score" class="score-big" style="color:var(--green)">0.00</div>
    <div id="sum-details" class="detail"></div>
    <button class="btn btn-exec" onclick="document.getElementById('overlay').classList.remove('visible')">Continue</button>
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
  const ring = $('health-ring-fg');
  const circum = 125.66;
  ring.style.strokeDashoffset = circum - (circum * h / 100);
  ring.style.stroke = h > 70 ? 'var(--green)' : h > 40 ? 'var(--yellow)' : 'var(--red)';
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
