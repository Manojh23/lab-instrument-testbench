#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
python -m pytest --cov=testbench --cov-branch --cov-report=term-missing --cov-report=xml:reports/coverage.xml --junitxml=reports/junit.xml "$@"
