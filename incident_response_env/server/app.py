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


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the dashboard at root."""
    return DASHBOARD_HTML


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
    """Return baseline scores, walkthroughs, and AI-vs-human comparison."""
    return {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "scores": {
            "easy": {"ai": 0.80, "human": 0.90, "scenarios": 5},
            "medium": {"ai": 0.57, "human": 0.80, "scenarios": 4},
            "hard": {"ai": 0.28, "human": 0.70, "scenarios": 3},
            "expert": {"ai": 0.09, "human": 0.74, "scenarios": 2},
        },
        "total_scenarios": 14,
        "note": "Expert tier is fully solvable by humans (0.74 in 9 steps) but defeats the 120B parameter model, demonstrating significant RL training potential.",
        "walkthroughs": {
            "easy": {
                "scenario": "Disk Full on Log Server",
                "optimal_steps": [
                    "check_logs log-server",
                    "restart_service log-server",
                    "submit_root_cause disk full on log-server, /var/log at 98%, log rotation stopped",
                ],
                "expected_score": 0.87,
                "explanation": "Direct investigation of alerting service, confirm root cause in logs, restart to clear, diagnose.",
            },
            "medium": {
                "scenario": "Database Connection Pool Exhaustion",
                "optimal_steps": [
                    "check_logs database-primary",
                    "get_metrics database-primary",
                    "check_dependencies database-primary",
                    "check_logs user-service",
                    "restart_service database-primary",
                    "submit_root_cause slow query causing lock contention, exhausting connection pool on database-primary",
                ],
                "expected_score": 0.80,
                "explanation": "Follow the dependency chain: DB logs reveal slow queries, metrics confirm pool saturation, trace upstream, fix, diagnose.",
            },
            "hard": {
                "scenario": "Crypto-Mining Attack Disguised as Memory Leak",
                "optimal_steps": [
                    "check_logs payment-service",
                    "get_metrics payment-service",
                    "check_process_list payment-service",
                    "check_network payment-service",
                    "kill_process payment-service (pid=9821)",
                    "submit_root_cause crypto mining malware attack on payment-service, unauthorized process xmrig",
                ],
                "expected_score": 0.87,
                "explanation": "Key insight: check_process_list reveals disguised miner. Must kill_process (not restart), then verify via network connections.",
            },
            "expert": {
                "scenario": "Database Split-Brain During Network Partition",
                "optimal_steps": [
                    "check_logs database-primary",
                    "check_logs database-replica",
                    "get_metrics database-primary",
                    "get_metrics database-replica",
                    "check_network network-switch",
                    "check_logs network-switch",
                    "get_dependency_graph",
                    "restart_service database-replica",
                    "submit_root_cause network partition caused split-brain, both databases accepting writes independently",
                ],
                "expected_score": 0.74,
                "explanation": "Must investigate both DB nodes to detect divergent WAL positions. Network switch reveals the partition. Fence the replica, not the primary.",
            },
        },
    }


@app.get("/postmortem")
async def get_postmortem():
    """Return structured post-mortem incident report after episode ends."""
    return env.get_postmortem()


@app.get("/mcp/tools")
async def mcp_tools():
    """MCP-compatible tool discovery. Returns available commands as JSON schemas.
    Tools may be revoked mid-episode during security lockdown scenarios."""
    if env._cluster is None:
        return {"tools": [], "note": "No active episode. Call reset first."}
    tools = env._cluster.get_available_tools()
    revoked = list(env._cluster._revoked_tools)
    return {
        "tools": tools,
        "revoked": revoked,
        "lockdown_active": len(revoked) > 0,
    }


@app.get("/env/state")
async def get_env_state():
    """Return detailed environment state (extends OpenEnv /state)."""
    state = env.state
    return {
        "episode_id": state.episode_id,
        "task_id": state.task_id,
        "scenario_id": state.scenario_id,
        "step_count": state.step_count,
        "max_steps": state.max_steps,
        "current_health": state.current_health,
        "initial_health": state.initial_health,
        "root_cause_found": state.root_cause_found,
        "done": state.done,
        "cumulative_reward": state.cumulative_reward,
        "services_investigated": state.services_investigated,
        "services_restarted": state.services_restarted,
        "destructive_actions": state.destructive_actions,
        "actions_taken": state.actions_taken,
    }


# ── Web UI API Endpoints ──────────────────────────────────────────────────


class ResetRequest(BaseModel):
    task_id: str = "easy"
    scenario_index: int = -1
    seed: int = -1
    mode: str = "auto"


class StepRequest(BaseModel):
    command: str
    target: str = ""
    parameters: dict = {}
    mode: str = "auto"


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
    seed = req.seed if req.seed >= 0 else None
    obs = env.reset(task_id=req.task_id, scenario_index=req.scenario_index, seed=seed, mode=req.mode)
    result = _obs_to_dict(obs)
    result["services"] = sorted(env._cluster.services.keys()) if env._cluster else []
    result["hybrid_active"] = env._cluster._hybrid_mode if env._cluster else False
    return result


@app.post("/web/step")
async def web_step(req: StepRequest):
    action = SREAction(command=req.command, target=req.target, parameters=req.parameters)
    obs = env.step(action)
    result = _obs_to_dict(obs)
    result["evidence_notes"] = env.state.evidence_notes
    result["grader"] = env.get_grader_result() if obs.done else None
    return result



@app.get("/web/hybrid-status")
async def hybrid_status():
    """Check if real infrastructure services are available."""
    try:
        from .infrastructure import _get_hybrid_services
        metrics, _ = _get_hybrid_services()
        if metrics is not None:
            return {
                "available": True,
                "redis": metrics.redis_available,
                "sqlite": metrics.sqlite_available,
            }
    except Exception:
        pass
    return {"available": False, "redis": False, "sqlite": False}


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
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0B0B0F;--bg-elevated:#111118;--bg-card:rgba(22,22,29,.60);
  --bg-input:#0D0D12;--bg-term:#0D0D12;
  --border:rgba(255,255,255,.05);--border-hover:rgba(255,255,255,.10);--border-focus:#8B5CF6;
  --text:#E5E7EB;--text-dim:#6B7280;--text-bright:#F9FAFB;--text-muted:#4B5563;
  --accent:#8B5CF6;--accent-glow:rgba(139,92,246,.30);--accent-dim:rgba(139,92,246,.12);
  --cyan:#22D3EE;--green:#34D399;--green-dim:rgba(52,211,153,.10);
  --yellow:#FBBF24;--yellow-dim:rgba(251,191,36,.10);
  --red:#EF4444;--red-dim:rgba(239,68,68,.10);--red-glow:rgba(239,68,68,.30);
  --orange:#F97316;--purple:#A78BFA;--purple-dim:rgba(167,139,250,.12);
  --mono:'JetBrains Mono',Consolas,'Courier New',monospace;
  --sans:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
  --r:12px;--r-lg:16px;--r-sm:8px;
}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--sans);
  overflow:hidden;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
::selection{background:var(--accent-glow);color:#fff}
@keyframes fadeSlide{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@keyframes pulseGlow{0%,100%{box-shadow:0 0 4px 0 var(--red-glow)}50%{box-shadow:0 0 12px 4px var(--red-glow)}}
@keyframes scoreGlow{0%,100%{text-shadow:0 0 16px var(--accent-glow)}50%{text-shadow:0 0 32px var(--accent-glow)}}
.app{display:flex;flex-direction:column;height:100vh}
.topbar{display:flex;align-items:center;gap:20px;padding:12px 28px;
  background:var(--bg-elevated);border-bottom:1px solid var(--border);flex-shrink:0}
.topbar-left{display:flex;align-items:center;gap:14px;margin-right:auto}
.topbar-logo{width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,#8B5CF6,#6D28D9);
  display:flex;align-items:center;justify-content:center;
  font-size:13px;font-weight:700;color:#fff;flex-shrink:0;
  box-shadow:0 0 20px rgba(139,92,246,.25)}
.topbar-title{font-size:15px;font-weight:600;color:var(--text-bright);letter-spacing:-.3px}
.topbar-sub{font-size:10px;color:var(--text-dim);margin-top:2px;letter-spacing:.4px;text-transform:uppercase}
.topbar-metrics{display:flex;align-items:center;gap:28px}
.metric{display:flex;flex-direction:column;align-items:center;gap:5px}
.metric-label{font-size:9px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px}
.health-ring{position:relative;width:52px;height:52px}
.health-ring svg{transform:rotate(-90deg)}
.health-ring circle{fill:none;stroke-width:3.5;stroke-linecap:round}
.health-ring .ring-bg{stroke:rgba(255,255,255,.04)}
.health-ring .ring-fg{transition:stroke-dashoffset .8s cubic-bezier(.4,0,.2,1),stroke .5s ease}
.health-ring-val{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:11px;font-weight:700}
.score-val{font-family:var(--mono);font-size:24px;font-weight:700;color:var(--accent);
  animation:scoreGlow 3s ease-in-out infinite}
.step-val{font-family:var(--mono);font-size:15px;font-weight:600;color:var(--text)}
/* Tabs */
.tab-bar{display:flex;gap:0;padding:0 28px;background:var(--bg-elevated);
  border-bottom:1px solid var(--border);flex-shrink:0}
.tab{padding:10px 20px;font-size:12px;font-weight:500;color:var(--text-muted);
  cursor:pointer;border-bottom:2px solid transparent;transition:all .2s;user-select:none}
.tab:hover{color:var(--text)}
.tab.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-content{display:none;flex:1;overflow:hidden}
.tab-content.active{display:flex}
/* Service map */
.svc-map{width:100%;padding:16px}
.svc-map svg{width:100%}
.svc-node{transition:fill .3s}
.svc-label{font-family:var(--mono);font-size:10px;fill:var(--text);text-anchor:middle}
.svc-edge{stroke:rgba(255,255,255,.1);stroke-width:1;fill:none;marker-end:url(#arrowhead)}
/* Postmortem tab */
.pm-wrap{flex:1;overflow-y:auto;padding:24px 32px;max-width:800px;margin:0 auto}
.pm-title{font-size:20px;font-weight:700;color:var(--text-bright);margin-bottom:16px}
.pm-section{margin-bottom:20px}
.pm-section h3{font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;
  letter-spacing:.8px;margin-bottom:8px}
.pm-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.03);
  font-size:13px}
.pm-row .pm-label{color:var(--text-dim)}.pm-row .pm-val{color:var(--text);font-weight:500;font-family:var(--mono)}
.pm-timeline-item{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.03);font-size:12px}
.pm-step-num{color:var(--accent);font-weight:700;font-family:var(--mono);min-width:32px}
.pm-action{color:var(--cyan);font-family:var(--mono)}.pm-finding{color:var(--text-dim)}
.main{display:flex;flex-direction:column;flex:1;overflow:hidden}
.main-inner{display:flex;flex:1;overflow:hidden}
.panel-left{flex:0 0 62%;display:flex;flex-direction:column;padding:12px 0 12px 12px}
.panel-right{flex:1;display:flex;flex-direction:column;overflow-y:auto;padding:12px;gap:12px;
  max-height:calc(100vh - 120px)}
.panel-right::-webkit-scrollbar{width:4px}
.panel-right::-webkit-scrollbar-thumb{background:rgba(255,255,255,.06);border-radius:2px}
.terminal-wrap{flex:1;display:flex;flex-direction:column;overflow:hidden;
  border-radius:var(--r-lg);background:var(--bg-term);border:1px solid var(--border);
  box-shadow:0 4px 24px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.03)}
.terminal-titlebar{display:flex;align-items:center;gap:7px;padding:11px 18px;
  background:rgba(255,255,255,.02);border-bottom:1px solid var(--border);flex-shrink:0}
.terminal-dot{width:11px;height:11px;border-radius:50%;opacity:.85}
.dot-red{background:#EF4444}.dot-yellow{background:#FBBF24}.dot-green{background:#34D399}
.terminal-titlebar-text{font-size:11px;color:var(--text-muted);margin-left:10px;font-family:var(--mono)}
.terminal{flex:1;overflow-y:auto;padding:18px 22px;font-family:var(--mono);font-size:12px;
  line-height:1.75;white-space:pre-wrap;word-break:break-word}
.terminal::-webkit-scrollbar{width:4px}
.terminal::-webkit-scrollbar-thumb{background:rgba(255,255,255,.05);border-radius:2px}
.term-step{padding-bottom:14px;margin-bottom:14px;border-bottom:1px solid rgba(255,255,255,.03);
  animation:fadeSlide .2s ease}
.term-step:last-child{border-bottom:none}
.term-cmd{color:var(--cyan);font-weight:600;margin-bottom:5px}
.term-cmd::before{content:'$ ';color:var(--text-muted);font-weight:400}
.term-time{color:var(--text-muted);font-size:10px;margin-left:8px}
.term-output{color:var(--text)}
.term-error{color:var(--red);font-weight:500}
.term-warn{color:var(--yellow)}
.term-info{color:var(--accent)}
.term-critical{color:#FF6B6B;font-weight:700;background:var(--red-dim);
  padding:2px 6px;border-radius:4px;border-left:2px solid var(--red)}
.term-welcome{color:var(--text-dim);text-align:center;padding:70px 30px}
.term-welcome h2{color:var(--text-bright);font-family:var(--sans);font-size:26px;
  margin-bottom:12px;font-weight:700;letter-spacing:-.4px}
.term-welcome p{font-family:var(--sans);font-size:13px;line-height:1.7;
  max-width:460px;margin:0 auto;color:var(--text-dim)}
.term-welcome .tiers{margin-top:24px;display:flex;justify-content:center;gap:12px;flex-wrap:wrap}
.tier-tag{font-size:11px;font-weight:600;padding:6px 16px;border-radius:20px;border:1px solid var(--border);
  margin-bottom:4px}
.tier-easy{color:var(--green);border-color:rgba(52,211,153,.25);background:var(--green-dim)}
.tier-medium{color:var(--yellow);border-color:rgba(251,191,36,.25);background:var(--yellow-dim)}
.tier-hard{color:var(--red);border-color:rgba(239,68,68,.25);background:var(--red-dim)}
.tier-expert{color:var(--purple);border-color:rgba(167,139,250,.25);background:var(--purple-dim)}
.card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--r);
  overflow:hidden;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  transition:border-color .25s,box-shadow .25s}
.card:hover{border-color:var(--border-hover);box-shadow:0 4px 20px rgba(0,0,0,.2)}
.card-header{padding:11px 16px;font-size:10px;font-weight:600;text-transform:uppercase;
  letter-spacing:.8px;color:var(--text-muted);border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:7px;background:rgba(255,255,255,.015)}
.card-header-icon{font-size:12px;opacity:.6}
.card-body{padding:14px 16px;min-height:40px;overflow-y:auto;font-size:12px;
  max-height:200px;scrollbar-width:thin;scrollbar-color:#333 transparent}
.card-body::-webkit-scrollbar{width:4px}
.card-body::-webkit-scrollbar-thumb{background:#333;border-radius:2px}
.card-body::-webkit-scrollbar-track{background:transparent}
.card-body.cb-alerts{max-height:200px}
.card-body.cb-commands{max-height:280px}
.card-body.cb-evidence{max-height:180px}
.card-body.cb-actions{max-height:180px}
.alert-item{display:flex;align-items:flex-start;gap:9px;padding:8px 0;
  border-bottom:1px solid rgba(255,255,255,.03);animation:fadeSlide .2s ease}
.alert-item:last-child{border-bottom:none}
.sev-pill{font-size:9px;font-weight:700;padding:3px 9px;border-radius:20px;text-transform:uppercase;
  white-space:nowrap;flex-shrink:0;letter-spacing:.4px}
.sev-critical{background:var(--red-dim);color:var(--red);border:1px solid rgba(239,68,68,.2);
  animation:pulseGlow 2.5s infinite}
.sev-warning{background:var(--yellow-dim);color:var(--yellow);border:1px solid rgba(251,191,36,.15)}
.sev-info{background:var(--accent-dim);color:var(--accent);border:1px solid rgba(139,92,246,.15)}
.alert-text{color:var(--text);font-size:13px;line-height:1.5;word-break:break-word}
.alert-svc{color:var(--accent);font-size:11px;font-family:var(--mono);margin-top:3px;cursor:pointer;
  transition:color .15s}
.alert-svc:hover{color:var(--cyan);text-decoration:underline}
.cmd-list-item{padding:5px 10px;font-family:var(--mono);font-size:10.5px;color:var(--text-dim);
  border-radius:var(--r-sm);transition:all .15s;cursor:pointer;line-height:1.65;user-select:none}
.cmd-list-item:hover{background:rgba(139,92,246,.06);color:var(--text)}
.cmd-list-item .cmd-name{color:var(--accent);font-weight:500}
.cmd-list-item .cmd-arg{color:var(--text-muted)}
.action-item{padding:5px 0;font-family:var(--mono);font-size:11px;color:var(--text-dim);
  border-bottom:1px solid rgba(255,255,255,.03);animation:fadeSlide .15s ease}
.action-item:last-child{border-bottom:none}
.action-item .step-num{color:var(--accent);font-weight:600}
.empty{color:var(--text-muted);padding:18px 0;text-align:center;font-size:11px}
.term-hint{color:var(--text-muted);font-size:11px;font-family:var(--sans);margin-top:6px;
  font-style:italic;opacity:.7}
.bottombar{display:flex;align-items:center;gap:10px;padding:14px 28px;
  background:var(--bg-elevated);border-top:1px solid var(--border);flex-shrink:0}
.bottombar select,.bottombar input,.bottombar button{font-family:var(--sans);font-size:13px;outline:none}
.task-pill{padding:9px 16px;background:var(--bg-input);color:var(--text);
  border:1px solid var(--border);border-radius:24px;cursor:pointer;font-weight:500;
  -webkit-appearance:none;appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236B7280'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 12px center;padding-right:30px;transition:border-color .2s}
.task-pill:focus{border-color:var(--border-focus)}
.mode-toggle{display:flex;align-items:center;background:var(--bg-input);border:1px solid var(--border);
  border-radius:24px;overflow:hidden;flex-shrink:0}
.mode-opt{padding:8px 14px;font-size:12px;font-weight:500;color:var(--text-dim);cursor:pointer;
  transition:all .2s;white-space:nowrap;display:flex;align-items:center;gap:6px;
  border:none;background:none;font-family:var(--sans)}
.mode-opt.active{color:var(--text-bright);background:rgba(139,92,246,.15)}
.mode-opt:hover:not(.active){color:var(--text);background:rgba(255,255,255,.03)}
.mode-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.mode-dot.on{background:var(--green);box-shadow:0 0 6px var(--green)}
.mode-dot.off{background:var(--text-muted)}
.btn{padding:9px 20px;cursor:pointer;font-weight:600;border:none;border-radius:24px;
  transition:all .2s;font-size:13px}
.btn:hover{transform:translateY(-1px)}.btn:active{transform:none}
.btn-new{background:linear-gradient(135deg,#8B5CF6,#6D28D9);color:#fff;
  box-shadow:0 2px 12px rgba(139,92,246,.25)}
.btn-new:hover{box-shadow:0 6px 24px rgba(139,92,246,.35)}
.btn-exec{background:linear-gradient(135deg,#7C3AED,#4F46E5);color:#fff;
  box-shadow:0 2px 12px rgba(124,58,237,.25)}
.btn-exec:hover{box-shadow:0 6px 24px rgba(124,58,237,.4)}
.btn-exec:disabled,.btn-exec:disabled:hover{opacity:.25;cursor:not-allowed;transform:none;box-shadow:none}
.cmd-input{flex:1;padding:11px 18px;background:var(--bg-input);color:var(--text);
  border:1px solid var(--border);border-radius:var(--r);
  font-family:var(--mono);font-size:13px;transition:border-color .2s,box-shadow .2s}
.cmd-input:focus{border-color:var(--border-focus);box-shadow:0 0 0 3px var(--accent-glow)}
.cmd-input::placeholder{color:var(--text-muted)}.cmd-input:disabled{opacity:.25}
.svc-picker{display:none;position:absolute;bottom:100%;left:0;right:0;margin-bottom:6px;
  padding:6px;background:var(--bg-elevated);border:1px solid var(--border-hover);
  border-radius:var(--r);box-shadow:0 8px 32px rgba(0,0,0,.5);z-index:50;
  flex-wrap:wrap;gap:6px}
.svc-picker.visible{display:flex}
.svc-chip{padding:5px 12px;font-family:var(--mono);font-size:11px;color:var(--text);
  background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.2);
  border-radius:16px;cursor:pointer;transition:all .15s;white-space:nowrap}
.svc-chip:hover{background:rgba(139,92,246,.2);border-color:var(--accent);color:var(--text-bright)}
.cmd-wrap{position:relative;flex:1;display:flex}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.80);backdrop-filter:blur(10px);
  display:flex;align-items:center;justify-content:center;z-index:100;
  opacity:0;pointer-events:none;transition:opacity .3s}
.overlay.visible{opacity:1;pointer-events:auto}
.summary-card{background:var(--bg-card);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:40px 48px;max-width:450px;width:92%;
  text-align:center;backdrop-filter:blur(20px);
  box-shadow:0 32px 80px rgba(0,0,0,.6);animation:fadeSlide .3s ease}
.summary-card h2{font-size:18px;color:var(--text-bright);margin-bottom:4px;font-weight:600}
.summary-card .score-big{font-size:58px;font-weight:700;font-family:var(--mono);margin:20px 0;letter-spacing:-2px}
.summary-card .detail{font-size:12px;color:var(--text-dim);line-height:2.1}
.summary-card .detail span{color:var(--text);font-weight:500}
.summary-card .detail a{color:var(--accent);font-weight:500}
.summary-card button{margin-top:24px}
@media(max-width:900px){
  .main{flex-direction:column}
  .panel-left{flex:none;height:55%;padding:8px}
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
      <div class="topbar-logo"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><circle cx="6" cy="6" r="1" fill="#fff"/><circle cx="6" cy="18" r="1" fill="#fff"/></svg></div>
      <div class="topbar-text">
        <div class="topbar-title">Incident Response Simulator</div>
        <div class="topbar-sub">OpenEnv DevSecOps Environment</div>
      </div>
    </div>
    <div class="topbar-metrics">
      <div class="metric">
        <div class="metric-label">Health</div>
        <div class="health-ring">
          <svg width="52" height="52" viewBox="0 0 52 52">
            <circle class="ring-bg" cx="26" cy="26" r="22"/>
            <circle id="health-ring-fg" class="ring-fg" cx="26" cy="26" r="22"
              stroke="var(--green)" stroke-dasharray="138.23" stroke-dashoffset="138.23"/>
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
    <div class="tab-bar">
      <div class="tab active" onclick="switchTab('dashboard')">Dashboard</div>
      <div class="tab" onclick="switchTab('servicemap')">Service Map</div>
      <div class="tab" onclick="switchTab('postmortem')">Post-Mortem</div>
      <div class="tab" onclick="switchTab('baseline')">Baseline</div>
    </div>
    <!-- Dashboard tab -->
    <div id="tab-dashboard" class="tab-content active">
      <div class="panel-left">
        <div class="terminal-wrap">
          <div class="terminal-titlebar">
            <div class="terminal-dot dot-red"></div>
            <div class="terminal-dot dot-yellow"></div>
            <div class="terminal-dot dot-green"></div>
            <span class="terminal-titlebar-text">incident-response @ production</span>
          </div>
          <div id="terminal" class="terminal">
            <div class="term-welcome">
              <h2>Welcome, On-Call Engineer</h2>
              <p>Select a difficulty tier and click <b>New Episode</b>.</p>
              <div class="tiers">
                <span class="tier-tag tier-easy">Easy - single alert, 10 steps</span>
                <span class="tier-tag tier-medium">Medium - correlated failures, 15 steps</span>
                <span class="tier-tag tier-hard">Hard - security ambiguity, 20 steps</span>
                <span class="tier-tag tier-expert">Expert - forensic investigation, 25 steps</span>
              </div>
              <p style="margin-top:20px;font-size:12px;color:var(--text-muted);line-height:1.8;max-width:420px">
                1. Click alert service names to investigate<br>
                2. Use the commands panel on the right<br>
                3. Fix the issue, then submit your diagnosis<br>
                4. Check <b>Service Map</b> tab for live dependency graph<br>
                5. Check <b>Post-Mortem</b> tab for detailed scoring<br>
                <span style="color:var(--accent)">Tip:</span> Click any command to auto-fill. Click a service pill to complete it.
              </p>
            </div>
          </div>
        </div>
      </div>
      <div class="panel-right">
        <div class="card">
          <div class="card-header"><span class="card-header-icon">&#9888;</span> Active Alerts</div>
          <div id="alerts-panel" class="card-body cb-alerts"><div class="empty">No active episode</div></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-header-icon">&#9881;</span> Commands</div>
          <div class="card-body cb-commands" style="padding:4px 6px">
            <div class="cmd-list-item"><span class="cmd-name">check_logs</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">get_metrics</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">list_alerts</span></div>
            <div class="cmd-list-item"><span class="cmd-name">check_dependencies</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">get_dependency_graph</span></div>
            <div class="cmd-list-item"><span class="cmd-name">trace_failure</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">restart_service</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">scale_up</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">rollback_deploy</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">kill_process</span> <span class="cmd-arg">{service} pid=PID</span></div>
            <div class="cmd-list-item"><span class="cmd-name">check_process_list</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">check_network</span> <span class="cmd-arg">{service}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">add_note</span> <span class="cmd-arg">{text}</span></div>
            <div class="cmd-list-item"><span class="cmd-name">view_notes</span></div>
            <div class="cmd-list-item"><span class="cmd-name">get_runbook</span></div>
            <div class="cmd-list-item"><span class="cmd-name">submit_root_cause</span> <span class="cmd-arg">{diagnosis}</span></div>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-header-icon">&#128270;</span> Evidence Board</div>
          <div id="evidence-panel" class="card-body cb-evidence"><div class="empty">No notes yet</div></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-header-icon">&#9654;</span> Actions Taken</div>
          <div id="actions-panel" class="card-body cb-actions"><div class="empty">No actions yet</div></div>
        </div>
      </div>
    </div>
    <!-- Service Map tab -->
    <div id="tab-servicemap" class="tab-content" style="flex-direction:column;padding:16px;overflow-y:auto">
      <div class="card" style="flex:none">
        <div class="card-header"><span class="card-header-icon">&#128268;</span> Service Dependency Map</div>
        <div class="card-body" style="max-height:none;padding:12px">
          <div id="svc-map" class="svc-map">
            <svg viewBox="0 0 600 280" height="260">
              <defs><marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="rgba(255,255,255,.15)"/></marker></defs>
              <line class="svc-edge" x1="300" y1="45" x2="300" y2="90"/>
              <line class="svc-edge" x1="260" y1="125" x2="150" y2="170"/>
              <line class="svc-edge" x1="340" y1="125" x2="450" y2="170"/>
              <line class="svc-edge" x1="300" y1="125" x2="300" y2="170"/>
              <line class="svc-edge" x1="150" y1="205" x2="100" y2="240"/>
              <line class="svc-edge" x1="150" y1="205" x2="200" y2="240"/>
              <line class="svc-edge" x1="300" y1="205" x2="300" y2="240"/>
              <line class="svc-edge" x1="450" y1="205" x2="500" y2="240"/>
              <rect id="node-frontend" class="svc-node" x="255" y="20" width="90" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="300" y="40">frontend</text>
              <rect id="node-api-gateway" class="svc-node" x="240" y="95" width="120" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="300" y="115">api-gateway</text>
              <rect id="node-user-service" class="svc-node" x="85" y="175" width="130" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="150" y="195">user-service</text>
              <rect id="node-worker-queue" class="svc-node" x="240" y="175" width="120" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="300" y="195">worker-queue</text>
              <rect id="node-payment-service" class="svc-node" x="385" y="175" width="130" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="450" y="195">payment-service</text>
              <rect id="node-cache-redis" class="svc-node" x="40" y="240" width="120" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="100" y="260">cache-redis</text>
              <rect id="node-database-primary" class="svc-node" x="180" y="240" width="140" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="250" y="260">database-primary</text>
              <rect id="node-dns-resolver" class="svc-node" x="340" y="240" width="120" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="400" y="260">dns-resolver</text>
              <rect id="node-config-server" class="svc-node" x="480" y="240" width="120" height="30" rx="6" fill="#374151"/>
              <text class="svc-label" x="540" y="260">config-server</text>
              <rect id="node-log-server" class="svc-node" x="340" y="175" width="0" height="0" rx="6" fill="#374151"/>
              <rect id="node-database-replica" class="svc-node" x="340" y="175" width="0" height="0" rx="6" fill="#374151"/>
              <rect id="node-network-switch" class="svc-node" x="340" y="175" width="0" height="0" rx="6" fill="#374151"/>
            </svg>
          </div>
        </div>
      </div>
      <div class="card" style="flex:none">
        <div class="card-header"><span class="card-header-icon">&#128200;</span> Health Timeline</div>
        <div class="card-body" style="max-height:200px;min-height:180px;padding:8px 12px"><canvas id="health-chart"></canvas></div>
      </div>
    </div>
    <!-- Post-Mortem tab -->
    <div id="tab-postmortem" class="tab-content" style="flex-direction:column">
      <div id="pm-content" class="pm-wrap">
        <div class="empty" style="padding:80px 0">Complete an episode to view the post-mortem report.</div>
      </div>
    </div>
    <!-- Baseline tab -->
    <div id="tab-baseline" class="tab-content" style="flex-direction:column">
      <div id="bl-content" class="pm-wrap">
        <div class="empty" style="padding:80px 0">Loading baseline data...</div>
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
    <div class="mode-toggle" id="mode-toggle">
      <button class="mode-opt active" data-mode="simulated" onclick="setMode('simulated')">Simulated</button>
      <button class="mode-opt" data-mode="hybrid" onclick="setMode('hybrid')">Hybrid-Real <span id="hybrid-dot" class="mode-dot off"></span></button>
    </div>
    <button class="btn btn-new" onclick="startEpisode()">New Episode</button>
    <div class="cmd-wrap">
      <div id="svc-picker" class="svc-picker"></div>
      <input id="cmd-input" class="cmd-input" placeholder="Type a command... e.g. check_logs payment-service"
             disabled onkeydown="if(event.key==='Enter')executeCmd()" oninput="onCmdInput()">
    </div>
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

// Health timeline chart
const ctx = $('health-chart').getContext('2d');
window.healthChart = new Chart(ctx, {
  type: 'line',
  data: { labels: [], datasets: [{ data: [], borderColor: '#34D399', borderWidth: 2.5,
    pointRadius: 4, pointBackgroundColor: '#34D399', pointBorderColor: '#0B0B0F',
    pointBorderWidth: 1.5, fill: true,
    backgroundColor: 'rgba(52,211,153,.08)', tension: 0.35 }] },
  options: { responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
    plugins: { legend: { display: false }, tooltip: { backgroundColor: '#16161D',
      borderColor: 'rgba(255,255,255,.1)', borderWidth: 1, titleColor: '#E5E7EB',
      bodyColor: '#A78BFA', bodyFont: { family: "'JetBrains Mono'" },
      callbacks: { label: function(c) { return c.parsed.y.toFixed(0) + '%'; } } } },
    scales: { x: { display: true, grid: { color: 'rgba(255,255,255,.04)' },
      ticks: { color: '#4B5563', font: { size: 9, family: "'JetBrains Mono'" } },
      title: { display: true, text: 'Step', color: '#4B5563', font: { size: 9 } } },
      y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,.05)' },
      ticks: { color: '#4B5563', font: { size: 9, family: "'JetBrains Mono'" },
        stepSize: 25, callback: function(v) { return v + '%'; } } } } }
});

function colorize(text) {
  return text.replace(/^(.*\\bERROR\\b.*)$/gm, '<span class="term-error">$1</span>')
    .replace(/^(.*\\bWARN\\b.*)$/gm, '<span class="term-warn">$1</span>')
    .replace(/^(.*\\bINFO\\b.*)$/gm, '<span class="term-info">$1</span>')
    .replace(/^(.*\\bCRITICAL\\b.*)$/gm, '<span class="term-critical">$1</span>')
    .replace(/^(.*\\bFATAL\\b.*)$/gm, '<span class="term-critical">$1</span>');
}

function updateHealth(h) {
  const ring = $('health-ring-fg');
  const circum = 138.23;
  ring.style.strokeDashoffset = circum - (circum * h / 100);
  const c = h > 70 ? 'var(--green)' : h > 40 ? 'var(--yellow)' : 'var(--red)';
  ring.style.stroke = c;
  $('health-val').textContent = h.toFixed(0) + '%';
  $('health-val').style.color = c;
  // Update chart
  if (window.healthChart) {
    window.healthChart.data.labels.push(window.healthChart.data.labels.length + 1);
    window.healthChart.data.datasets[0].data.push(h);
    window.healthChart.data.datasets[0].borderColor = h > 70 ? '#34D399' : h > 40 ? '#FBBF24' : '#EF4444';
    window.healthChart.update('none');
  }
}

function updateAlerts(alerts) {
  if (!alerts.length) { $('alerts-panel').innerHTML = '<div class="empty">No active alerts</div>'; return; }
  $('alerts-panel').innerHTML = alerts.map(a =>
    '<div class="alert-item">' +
    '<span class="sev-pill sev-' + a.severity + '">' + a.severity + '</span>' +
    '<div><div class="alert-text">' + a.message + '</div>' +
    '<div class="alert-svc" onclick="fillCmd(&quot;check_logs ' + a.service + '&quot;)">' + a.service + '</div></div></div>'
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

var _hintHistory = [];
function getHint(cmd) {
  _hintHistory.push(cmd || '');
  var cmds = _hintHistory;
  var hasFix = cmds.some(function(c) { return /^(restart_service|rollback_deploy|scale_up|kill_process)/.test(c); });
  var hasSubmit = cmds.some(function(c) { return /^submit_root_cause/.test(c); });
  var logCount = cmds.filter(function(c) { return /^check_logs/.test(c); }).length;
  var investCount = cmds.filter(function(c) { return /^(check_logs|get_metrics|check_process_list|check_network)/.test(c); }).length;
  if (!cmd) return 'Start by clicking list_alerts or clicking a service name in the alerts panel';
  if (/^list_alerts/.test(cmd)) return 'Click a service name above to check its logs';
  if (hasFix && !hasSubmit && cmds.length - cmds.indexOf(cmds.filter(function(c) { return /^(restart|rollback|scale|kill)/.test(c); }).pop()) > 2)
    return 'Submit your root cause diagnosis with submit_root_cause';
  if (hasFix && !hasSubmit) return 'System health changed. Submit your root cause diagnosis with submit_root_cause';
  if (/^(check_logs|get_metrics)/.test(cmd) && investCount < 3) return 'Try get_metrics or check_dependencies on this service, or check_logs on another alerted service';
  if (investCount >= 3) return 'Try get_dependency_graph to see the full service map, or trace_failure on the most suspicious service';
  return '';
}

function appendTerminal(cmd, output, showHint) {
  const el = document.createElement('div');
  el.className = 'term-step';
  const time = new Date().toLocaleTimeString();
  var hint = showHint ? getHint(cmd) : '';
  el.innerHTML = (cmd ? '<div class="term-cmd">' + cmd + ' <span class="term-time">' + time + '</span></div>' : '') +
    '<div class="term-output">' + colorize(output.replace(/</g,'&lt;').replace(/>/g,'&gt;')) + '</div>' +
    (hint ? '<div class="term-hint">' + hint + '</div>' : '');
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
  if (window.healthChart) { window.healthChart.data.labels = []; window.healthChart.data.datasets[0].data = []; window.healthChart.update('none'); }
  try {
    const res = await fetch('/web/reset', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ task_id: taskId, mode: _envMode === 'hybrid' ? 'auto' : 'simulated' })
    });
    const data = await res.json();
    episodeActive = true;
    if (typeof data.hybrid_active !== 'undefined') {
      var dot = $('hybrid-dot');
      if (dot) { dot.classList.toggle('on', data.hybrid_active); dot.classList.toggle('off', !data.hybrid_active); }
    }
    _currentServices = data.services || [];
    hideServicePicker();
    $('cmd-input').disabled = false;
    $('exec-btn').disabled = false;
    $('cmd-input').focus();
    updateHealth(data.system_health);
    $('step-display').textContent = data.step_count + '/' + data.max_steps;
    $('score-display').textContent = data.score.toFixed(2);
    updateAlerts(data.alerts);
    updateServiceMap(data.alerts);
    updateActions();
    _hintHistory = [];
    appendTerminal('', data.output, true);
  } catch (e) {
    appendTerminal('', 'ERROR: Failed to start episode: ' + e.message, false);
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
    appendTerminal(parsed.command + (parsed.target ? ' ' + parsed.target : ''), data.output, true);
    updateHealth(data.system_health);
    $('step-display').textContent = data.step_count + '/' + data.max_steps;
    $('score-display').textContent = data.score.toFixed(2);
    updateAlerts(data.alerts);
    updateServiceMap(data.alerts);
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

var _envMode = 'simulated';
var _hybridAvailable = false;

function setMode(mode) {
  _envMode = mode;
  document.querySelectorAll('.mode-opt').forEach(function(el) {
    el.classList.toggle('active', el.getAttribute('data-mode') === mode);
  });
}

(async function checkHybridStatus() {
  try {
    var res = await fetch('/web/hybrid-status');
    var d = await res.json();
    _hybridAvailable = d.available;
    var dot = $('hybrid-dot');
    if (dot) {
      dot.classList.toggle('on', d.available);
      dot.classList.toggle('off', !d.available);
    }
    if (d.available) setMode('hybrid');
  } catch(e) {}
})();

var _autoExec = ['list_alerts','get_dependency_graph','view_notes','get_runbook'];
var _noService = ['list_alerts','get_dependency_graph','view_notes','get_runbook','submit_root_cause','add_note'];
var _currentServices = [];
var _pendingCmd = '';

function showServicePicker(cmd) {
  _pendingCmd = cmd;
  var picker = $('svc-picker');
  picker.innerHTML = _currentServices.map(function(s) {
    return '<div class="svc-chip" onclick="pickService(&quot;'+s+'&quot;)">' + s + '</div>';
  }).join('');
  picker.classList.add('visible');
}

function hideServicePicker() { $('svc-picker').classList.remove('visible'); _pendingCmd = ''; }

function pickService(svc) {
  var inp = $('cmd-input');
  inp.value = _pendingCmd + svc;
  hideServicePicker();
  executeCmd();
}

function onCmdInput() {
  var val = $('cmd-input').value.trim();
  var words = val.split(/\\s+/);
  // Hide picker if user types manually
  if (words.length >= 2) hideServicePicker();
}

function fillCmd(text) {
  var inp = $('cmd-input');
  if (inp.disabled) return;
  var cmd = text.trim();
  // Auto-execute commands that need no argument
  if (_autoExec.indexOf(cmd) >= 0) {
    inp.value = cmd;
    hideServicePicker();
    executeCmd();
    return;
  }
  inp.value = text;
  inp.focus();
  // Show service picker for commands that need a service
  var base = cmd.replace(/\\s+$/, '');
  if (_noService.indexOf(base) < 0 && _currentServices.length > 0) {
    showServicePicker(text);
    inp.setAttribute('placeholder', '\u2190 pick a service or type one');
  } else {
    hideServicePicker();
    inp.setAttribute('placeholder', '\u2190 type argument and press Enter');
  }
  setTimeout(function() { inp.setAttribute('placeholder', 'Type a command... e.g. check_logs payment-service'); }, 5000);
}

// Make command list items clickable
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.cmd-list-item').forEach(function(el) {
    el.addEventListener('click', function() {
      var name = el.querySelector('.cmd-name');
      if (name) fillCmd(name.textContent + ' ');
    });
  });
  // Close picker on outside click
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.cmd-wrap') && !e.target.closest('.cmd-list-item')) hideServicePicker();
  });
});

function switchTab(name) {
  var tabs = ['dashboard','servicemap','postmortem','baseline'];
  document.querySelectorAll('.tab').forEach(function(t,i) {
    t.classList.toggle('active', tabs[i] === name);
  });
  document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
  $('tab-' + name).classList.add('active');
  if (name === 'postmortem') loadPostmortem();
  if (name === 'baseline') loadBaseline();
}

function updateServiceMap(alerts) {
  const svcColors = {};
  if (alerts) alerts.forEach(a => {
    const sev = a.severity;
    if (!svcColors[a.service] || sev === 'critical') svcColors[a.service] = sev;
  });
  document.querySelectorAll('.svc-node').forEach(n => {
    const svc = n.id.replace('node-','');
    const sev = svcColors[svc];
    if (sev === 'critical') n.setAttribute('fill','#7F1D1D');
    else if (sev === 'warning') n.setAttribute('fill','#78350F');
    else n.setAttribute('fill','#374151');
  });
}

async function loadPostmortem() {
  try {
    const res = await fetch('/postmortem');
    const d = await res.json();
    if (d.error) { $('pm-content').innerHTML = '<div class="empty" style="padding:80px 0">' + d.error + '</div>'; return; }
    let h = '<div class="pm-title">' + d.incident_title + '</div>';
    h += '<div class="pm-section"><div class="pm-row"><div class="pm-label">Difficulty</div><div class="pm-val">' + d.difficulty + '</div></div>';
    h += '<div class="pm-row"><div class="pm-label">Score</div><div class="pm-val" style="color:var(--accent)">' + d.final_score + '</div></div>';
    h += '<div class="pm-row"><div class="pm-label">Root Cause Found</div><div class="pm-val">' + (d.root_cause_identified ? 'Yes' : 'No') + '</div></div>';
    h += '<div class="pm-row"><div class="pm-label">Steps</div><div class="pm-val">' + d.total_steps + ' / ' + d.optimal_steps + ' optimal</div></div>';
    h += '<div class="pm-row"><div class="pm-label">Efficiency</div><div class="pm-val">' + d.efficiency_rating + '</div></div>';
    h += '<div class="pm-row"><div class="pm-label">Health</div><div class="pm-val">' + d.health_initial.toFixed(0) + '% &rarr; ' + d.health_final.toFixed(0) + '%</div></div></div>';
    h += '<div class="pm-section"><h3>Timeline</h3>';
    d.timeline.forEach(t => {
      h += '<div class="pm-timeline-item"><div class="pm-step-num">#' + t.step + '</div><div class="pm-action">' + t.action + '</div><div class="pm-finding">' + t.finding + '</div></div>';
    });
    h += '</div>';
    if (d.evidence_notes && d.evidence_notes.length) {
      h += '<div class="pm-section"><h3>Evidence Notes</h3>';
      d.evidence_notes.forEach(n => { h += '<div class="pm-timeline-item"><div class="pm-step-num">[' + n.step + ']</div><div class="pm-finding">' + n.text + '</div></div>'; });
      h += '</div>';
    }
    $('pm-content').innerHTML = h;
  } catch(e) { $('pm-content').innerHTML = '<div class="empty" style="padding:80px 0">Error loading post-mortem.</div>'; }
}

var _blChart = null;
async function loadBaseline() {
  try {
    var res = await fetch('/baseline');
    var d = await res.json();
    var s = d.scores;
    var tiers = [
      {name:'Easy',   k:'easy',   ai:s.easy.ai,   human:s.easy.human,   n:s.easy.scenarios,   gap:(s.easy.human-s.easy.ai).toFixed(2),     status:'Manageable', color:'var(--green)'},
      {name:'Medium', k:'medium', ai:s.medium.ai, human:s.medium.human, n:s.medium.scenarios, gap:(s.medium.human-s.medium.ai).toFixed(2), status:'Challenging',color:'var(--yellow)'},
      {name:'Hard',   k:'hard',   ai:s.hard.ai,   human:s.hard.human,   n:s.hard.scenarios,   gap:(s.hard.human-s.hard.ai).toFixed(2),     status:'Very Hard',  color:'var(--orange)'},
      {name:'Expert', k:'expert', ai:s.expert.ai, human:s.expert.human, n:s.expert.scenarios, gap:(s.expert.human-s.expert.ai).toFixed(2), status:'Unsolved',   color:'var(--red)'}
    ];
    var h = '<div class="pm-title">Baseline Performance - Human vs AI</div>';
    h += '<p style="color:var(--text-muted);font-size:12px;margin-bottom:20px">Tested with ' + d.model + '</p>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px">';
    h += '<tr style="border-bottom:1px solid rgba(255,255,255,.08);color:var(--text-muted);font-size:11px;text-transform:uppercase;letter-spacing:.5px">';
    h += '<th style="padding:8px 0;text-align:left">Tier</th><th>Scenarios</th><th>AI Score</th><th>Human Score</th><th>Gap</th><th style="text-align:right">Status</th></tr>';
    tiers.forEach(function(t) {
      h += '<tr style="border-bottom:1px solid rgba(255,255,255,.04)">';
      h += '<td style="padding:10px 0;font-weight:600;color:var(--text-bright)">' + t.name + '</td>';
      h += '<td style="text-align:center;font-family:var(--mono);color:var(--text-dim)">' + t.n + '</td>';
      h += '<td style="text-align:center;font-family:var(--mono);color:var(--accent)">' + t.ai.toFixed(2) + '</td>';
      h += '<td style="text-align:center;font-family:var(--mono);color:var(--cyan)">' + t.human.toFixed(2) + '</td>';
      h += '<td style="text-align:center;font-family:var(--mono);color:var(--text)">' + t.gap + '</td>';
      h += '<td style="text-align:right"><span style="color:' + t.color + '">&bull;</span> <span style="color:var(--text-dim);font-size:12px">' + t.status + '</span></td>';
      h += '</tr>';
    });
    h += '</table>';
    h += '<p style="color:var(--text-dim);font-size:12px;margin-bottom:6px">Total scenarios: ' + d.total_scenarios + '</p>';
    h += '<p style="color:var(--text-dim);font-size:12px;margin-bottom:24px">' + (d.note || '') + '</p>';
    h += '<div style="max-width:500px;height:220px;margin:0 auto"><canvas id="bl-chart"></canvas></div>';

    // Walkthroughs
    var wt = d.walkthroughs;
    if (wt) {
      h += '<div style="margin-top:36px;border-top:1px solid rgba(255,255,255,.06);padding-top:28px">';
      h += '<div class="pm-title">Optimal Walkthroughs</div>';
      h += '<p style="color:var(--text-muted);font-size:12px;margin-bottom:24px">Step-by-step solutions for one scenario per tier. Follow along in the dashboard to verify.</p>';
      var tierOrder = ['easy','medium','hard','expert'];
      var tierLabels = {easy:'Easy',medium:'Medium',hard:'Hard',expert:'Expert'};
      var tierColors = {easy:'var(--green)',medium:'var(--yellow)',hard:'var(--orange)',expert:'var(--red)'};
      tierOrder.forEach(function(tk) {
        var w = wt[tk];
        if (!w) return;
        h += '<div style="margin-bottom:28px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--r);padding:20px;animation:fadeSlide .3s ease">';
        h += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">';
        h += '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + tierColors[tk] + '"></span>';
        h += '<span style="font-weight:600;color:var(--text-bright);font-size:14px">' + tierLabels[tk] + ': ' + w.scenario + '</span>';
        h += '<span style="margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--accent)">Score: ' + w.expected_score.toFixed(2) + '</span>';
        h += '</div>';
        h += '<div style="margin-bottom:12px">';
        w.optimal_steps.forEach(function(step, idx) {
          var isInvestigate = step.startsWith('check_') || step.startsWith('get_') || step.startsWith('list_') || step.startsWith('trace_');
          var isFix = step.startsWith('restart_') || step.startsWith('kill_') || step.startsWith('rollback_') || step.startsWith('scale_');
          var isSubmit = step.startsWith('submit_');
          var stepColor = isSubmit ? 'var(--accent)' : isFix ? 'var(--green)' : 'var(--cyan)';
          var icon = isSubmit ? '&#10003;' : isFix ? '&#9881;' : '&#9658;';
          h += '<div style="display:flex;align-items:flex-start;gap:12px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.03)">';
          h += '<span style="flex-shrink:0;width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.04);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;color:var(--text-dim)">' + (idx+1) + '</span>';
          h += '<div style="flex:1;min-width:0">';
          h += '<code style="font-family:var(--mono);font-size:12px;color:' + stepColor + ';word-break:break-all">' + step + '</code>';
          h += '</div>';
          h += '<span style="flex-shrink:0;font-size:10px;color:var(--text-muted);margin-top:2px">' + icon + '</span>';
          h += '</div>';
        });
        h += '</div>';
        h += '<div style="font-size:12px;color:var(--text-dim);padding:10px 12px;background:rgba(139,92,246,.06);border-radius:var(--r-sm);border-left:3px solid var(--accent)">';
        h += '<strong style="color:var(--text)">Strategy:</strong> ' + w.explanation;
        h += '</div>';
        h += '</div>';
      });
      h += '</div>';
    }

    $('bl-content').innerHTML = h;
    // Render chart
    var ctx2 = document.getElementById('bl-chart').getContext('2d');
    if (_blChart) _blChart.destroy();
    _blChart = new Chart(ctx2, {
      type: 'bar',
      data: {
        labels: ['Easy','Medium','Hard','Expert'],
        datasets: [
          { label: 'AI', data: tiers.map(function(t){return t.ai;}), backgroundColor: 'rgba(139,92,246,.7)', borderRadius: 4 },
          { label: 'Human', data: tiers.map(function(t){return t.human;}), backgroundColor: 'rgba(34,211,238,.7)', borderRadius: 4 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#6B7280', font: { size: 11 } } } },
        scales: {
          x: { grid: { color: 'rgba(255,255,255,.04)' }, ticks: { color: '#6B7280' } },
          y: { min: 0, max: 1, grid: { color: 'rgba(255,255,255,.04)' }, ticks: { color: '#6B7280', callback: function(v){ return v.toFixed(1); } } }
        }
      }
    });
  } catch(e) { $('bl-content').innerHTML = '<div class="empty" style="padding:80px 0">Error loading baseline data.</div>'; }
}
</script>
</body>
</html>
"""


@app.get("/web", response_class=HTMLResponse)
async def web_dashboard():
    """Serve the interactive SRE dashboard."""
    return DASHBOARD_HTML
