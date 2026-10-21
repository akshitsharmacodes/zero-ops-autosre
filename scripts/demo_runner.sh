#!/bin/bash
set -e

echo "=========================================================="
echo "          AutoSRE (Team Zero-Ops) Demo Runner             "
echo "=========================================================="

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "1. Seeding victim repository with realistic git history..."
./scripts/seed_victim_repo.sh

echo "2. Verifying initial victim regression test failure on leaky commit..."
source .venv/bin/activate
pytest victim_service/tests/test_leak_regression.py || echo "--> Expected failure caught unclosed cursor regression!"

echo "3. Testing full LangGraph state machine with self-healing retry..."
python -c "
import sys, time
sys.path.insert(0, 'backend')
from agent.graph import create_autosre_graph
from agent.state import AgentState

graph = create_autosre_graph()
state: AgentState = {
    'incident_id': 'INC-DEMO-RUN',
    'status': 'ALERT_RECEIVED',
    'attempt': 0,
    'max_attempts': 3,
    'alert_payload': {'val': 98},
    'diagnostics_result': {},
    'suspect_commit': {},
    'leaking_code': '',
    'patch': '',
    'unified_diff': '',
    'risk': 'High',
    'confidence': 0.94,
    'sandbox_result': {},
    'error_trace': None,
    'guardrails_result': {},
    'pr_url': None,
    'postmortem': None,
    'timeline': [],
    'mttr_seconds': 0,
    'start_time': time.time(),
    'mode': 'cached'
}
res = graph.invoke(state)
print('==> Demo Run Result:')
print('    Status:', res['status'])
print('    Attempts:', res['attempt'])
print('    PR URL:', res['pr_url'])
print('    MTTR:', res['mttr_seconds'], 'seconds')
"

echo "=========================================================="
echo "          AutoSRE Demo Execution Completed!               "
echo "=========================================================="
