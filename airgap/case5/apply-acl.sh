#!/bin/bash
set -euo pipefail

API_FILE="/opt/knowledge/knowledge_api.py"
BACKUP_FILE="/opt/knowledge/knowledge_api.py.bak"

python3 - "$API_FILE" "$BACKUP_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
backup = Path(sys.argv[2])

source = path.read_text()

old = """        # Vulnerable state:
        # 모든 Knowledge가 사용자 권한과 관계없이 Retrieval 후보가 된다.
        allowed_documents = documents"""

new = """        # API Key 기반 사용자 식별
        api_keys = {
            "cnlsg-user-key": "llm-user",
            "cnlsg-admin-key": "admin-user"
        }

        api_key = self.headers.get("X-Knowledge-Key", "")
        principal = api_keys.get(api_key)

        if principal is None:
            self.send_error(401, "Unauthorized")
            return

        # 사용자별 Retrieval ACL
        acl = {
            "llm-user": {
                "kubernetes-guide.md",
                "database-runbook.md"
            },
            "admin-user": {
                "kubernetes-guide.md",
                "database-runbook.md",
                "production-security-runbook.md"
            }
        }

        # Retrieval 이전 ACL 적용
        allowed_documents = [
            doc for doc in documents
            if doc["name"] in acl.get(principal, set())
        ]"""

if source.count(old) != 1:
    raise SystemExit(
        "ERROR: 예상한 Knowledge API 코드와 일치하지 않습니다."
    )

if backup.exists():
    raise SystemExit(
        "ERROR: 기존 백업 파일이 있습니다."
    )

updated = source.replace(old, new, 1)

# Python 문법 검증
compile(updated, str(path), "exec")

# 원본 백업 및 ACL 적용
backup.write_text(source)
path.write_text(updated)

print("Retrieval ACL 적용 완료")
print(f"Backup: {backup}")
PY
