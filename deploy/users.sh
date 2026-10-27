#!/usr/bin/env bash
# Operator panel accounts on the server:
#   sudo bash /opt/dartsense/deploy/users.sh add jan --name "Jan Kowalski"
#   sudo bash /opt/dartsense/deploy/users.sh passwd jan
#   sudo bash /opt/dartsense/deploy/users.sh list | disable jan | enable jan
set -euo pipefail
APP=/opt/dartsense
cd "$APP"
exec sudo -u dartsense "$APP/.venv/bin/python" -m backend.users "$@"
