#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_server.sh — one-time AWS EC2 (Ubuntu) setup for this project.
#
# Run ONCE on the server after cloning + creating the venv:
#     bash setup_server.sh
#
# It sets the timezone to IST and installs cron jobs so that:
#   - on every boot (instance Start): the dashboard starts + data updates
#   - daily at 6:30 PM IST (if the instance is on): data updates
# Idempotent — safe to run again; it replaces this project's cron lines.
# ---------------------------------------------------------------------------
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$PROJECT_DIR/venv/bin/python"
ST="$PROJECT_DIR/venv/bin/streamlit"

if [ ! -x "$PY" ]; then
  echo "ERROR: venv not found at $PROJECT_DIR/venv"
  echo "Create it first:  python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

echo "1) Timezone -> Asia/Kolkata (so 6:30 PM cron = IST market time)"
sudo timedatectl set-timezone Asia/Kolkata || true

echo "2) Installing cron jobs..."
CRON_LINES=$(cat <<EOF
@reboot cd $PROJECT_DIR && $ST run dashboard.py --server.port 8501 --server.address 0.0.0.0 >> $PROJECT_DIR/streamlit.log 2>&1
@reboot cd $PROJECT_DIR && $PY run_daily.py >> $PROJECT_DIR/boot_update.log 2>&1
30 18 * * * cd $PROJECT_DIR && $PY run_daily.py >> $PROJECT_DIR/cron.log 2>&1
EOF
)

# Keep any unrelated cron lines, drop this project's old lines, add fresh ones.
( crontab -l 2>/dev/null | grep -vF "$PROJECT_DIR" ; echo "$CRON_LINES" ) | crontab -

echo
echo "Done. Installed cron jobs:"
crontab -l | grep -F "$PROJECT_DIR" || true
echo
echo "Reboot to test auto-start:  sudo reboot"
echo "Then open:  http://<your-elastic-ip>:8501"
