#!/bin/bash
set -euo pipefail

API_FILE="/opt/knowledge/knowledge_api.py"
BACKUP_FILE="/opt/knowledge/knowledge_api.py.bak"

# 기존 Knowledge API 백업
if [ -f "$BACKUP_FILE" ]; then
    echo "ERROR: 백업 파일이 이미 존재합니다: $BACKUP_FILE"
    exit 1
fi

# 사용자별 Retrieval ACL 적용
python3 - "$API_FILE" "$BACKUP_FILE" <<'PY'
from pathlib import Path
import re
import sys
import textwrap

path = Path(sys.argv[1])
backup = Path(sys.argv[2])

source = path.read_text()

# ACL 적용 대상 코드 확인
pattern = r"(?m)^([ \t]*)allowed_documents = documents[ \t]*$"
matches = list(re.finditer(pattern, source))

if len(matches) != 1:
    raise SystemExit("ERROR: ACL 적용 대상 코드를 찾을 수 없습니다.")

if not re.search(r"\bprincipal\b", source):
    raise SystemExit("ERROR: 사용자 Identity 처리를 확인할 수 없습니다.")

# 기존 들여쓰기 유지
indent = matches[0].group(1)

replacement = textwrap.indent("""ACL = {
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

allowed_documents = [
    doc for doc in documents
    if doc["name"] in ACL.get(principal, set())
]""", indent)

updated = (
    source[:matches[0].start()]
    + replacement
    + source[matches[0].end():]
)

# Python 문법 검증
compile(updated, str(path), "exec")

# 백업 및 변경 사항 저장
backup.write_text(source)
path.write_text(updated)

print("Retrieval ACL 적용 완료")
print(f"Backup: {backup}")
PY
