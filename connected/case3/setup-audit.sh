#!/bin/bash
set -e

LITELLM_HOST="192.168.1.101"
LITELLM_USER="ec2-user"
LITELLM_PASS="qwer1234!!"

# LiteLLM Input/Output Audit Logger 생성
cat > /tmp/audit_logger.py <<'PY'
import json
import re
from datetime import datetime, timezone

from litellm.integrations.custom_logger import CustomLogger

AUDIT_FILE = "/app/llm-input-audit.jsonl"

SYSTEM_REMINDER_PATTERN = re.compile(
    r"<system-reminder>.*?</system-reminder>",
    re.DOTALL,
)


class InputAuditLogger(CustomLogger):

    def _write_audit(self, source, value):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "action": "ALLOW",
            "input": value,
            "output": value,
        }

        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _clean_user_text(self, text):
        text = SYSTEM_REMINDER_PATTERN.sub("", text)
        return text.strip()

    async def async_log_success_event(
        self,
        kwargs,
        response_obj,
        start_time,
        end_time,
    ):
        messages = kwargs.get("messages", [])

        for message in messages:
            if message.get("role") != "user":
                continue

            content = message.get("content")

            if not isinstance(content, list):
                continue

            for item in content:
                if not isinstance(item, dict):
                    continue

                # 실제 사용자 입력
                if item.get("type") == "text":
                    text = item.get("text")

                    if not isinstance(text, str):
                        continue

                    # Claude Code Session Title 생성 요청 제외
                    if "<session>" in text:
                        continue

                    # Claude Code 내부 System Reminder 제외
                    text = self._clean_user_text(text)

                    if text:
                        self._write_audit("user", text)

                # Claude Code가 Tool로 읽은 실제 데이터
                elif item.get("type") == "tool_result":
                    text = item.get("content")

                    if isinstance(text, str):
                        self._write_audit("tool_result", text)


audit_logger = InputAuditLogger()
PY

# Audit Logger를 CN-LITELLM으로 전송
sshpass -p "${LITELLM_PASS}" \
scp /tmp/audit_logger.py \
${LITELLM_USER}@${LITELLM_HOST}:/tmp/audit_logger.py

# Audit Logger 배치
sshpass -p "${LITELLM_PASS}" \
ssh ${LITELLM_USER}@${LITELLM_HOST} \
"sudo mv /tmp/audit_logger.py /opt/litellm/audit_logger.py && \
sudo docker cp /opt/litellm/audit_logger.py litellm:/app/audit_logger.py"

# LiteLLM Audit Callback 설정
sshpass -p "${LITELLM_PASS}" \
ssh ${LITELLM_USER}@${LITELLM_HOST} \
"sudo tee -a /opt/litellm/config.yaml > /dev/null <<'YAML'

litellm_settings:
  callbacks: audit_logger.audit_logger
YAML
sudo docker exec litellm rm -f /app/llm-input-audit.jsonl
sudo docker restart litellm > /dev/null"

# CN-ADMIN 임시 파일 삭제
rm -f /tmp/audit_logger.py

echo
echo "LiteLLM Input/Output Audit enabled."
