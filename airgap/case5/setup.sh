#!/bin/bash
set -e

BASE_DIR="/opt/knowledge"
DOCS_DIR="${BASE_DIR}/docs"

echo "[1/3] Creating Knowledge directories"

sudo mkdir -p "${DOCS_DIR}"


echo "[2/3] Installing Case 5 files"

sudo cp ./knowledge_api.py "${BASE_DIR}/knowledge_api.py"
sudo cp ./docs/*.md "${DOCS_DIR}/"

sudo chmod 755 "${BASE_DIR}/knowledge_api.py"
sudo chmod 644 "${DOCS_DIR}"/*.md


echo "[3/3] Starting Knowledge API"

sudo pkill -f "/opt/knowledge/knowledge_api.py" 2>/dev/null || true

sudo nohup python3 "${BASE_DIR}/knowledge_api.py" \
  > /tmp/knowledge-api.log 2>&1 &

sleep 1

echo
echo "Case 5 Knowledge API ready"
echo "Endpoint: http://10.10.1.103:8080/search"
