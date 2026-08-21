#!/usr/bin/env bash
# Generate realistic test data using LLM (1min.ai)
# Usage: ./scripts/generate_test_data_llm.sh

set -e

cd "$(dirname "$0")/.."

source venv/bin/activate

python -m backend.utils.generate_test_data_llm \
  --jira-stories 50 \
  --jira-bugs 15 \
  --jira-sprints 5 \
  --servicenow-incidents 25 \
  --servicenow-deployments 10 \
  --splunk-logs 500
