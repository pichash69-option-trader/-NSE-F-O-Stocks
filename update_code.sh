#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# update_code.sh — pull the latest CODE from GitHub and restart the dashboard.
# (Data/nse.db is untouched — that updates separately via run_daily.py / cron.)
#
# Run on the EC2 from inside the repo folder:
#     bash update_code.sh
# ---------------------------------------------------------------------------
set -e
cd "$(cd "$(dirname "$0")" && pwd)"

echo "1) Pulling latest code from GitHub..."
git pull origin main

echo "2) Installing any new dependencies..."
venv/bin/pip install -q -r requirements.txt

echo "3) Restarting the dashboard..."
pkill -f "streamlit run dashboard.py" 2>/dev/null || true
sleep 2
nohup venv/bin/streamlit run dashboard.py \
      --server.port 8501 --server.address 0.0.0.0 >> streamlit.log 2>&1 &
sleep 3

echo
echo "Done ✅  — code updated, dashboard restarted on :8501"
echo "Open:  http://<your-elastic-ip>:8501"
