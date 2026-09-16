#!/bin/bash
set -e

LITELLM_DIR="/opt/litellm"
CONTAINER="litellm"
CONFIG="${LITELLM_DIR}/config.yaml"

cat <<'PY' | sudo tee ${LITELLM_DIR}/audit_logger.py > /dev/null
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

                if item.get("type") == "text":
                    text = item.get("text")

                    if not isinstance(text, str):
                        continue

                    if "<session>" in text:
                        continue

                    text = self._clean_user_text(text)

                    if text:
                        self._write_audit("user", text)

                elif item.get("type") == "tool_result":
                    text = item.get("content")

                    if isinstance(text, str):
                        self._write_audit("tool_result", text)


audit_logger = InputAuditLogger()
PY

sudo docker cp \
  ${LITELLM_DIR}/audit_logger.py \
  ${CONTAINER}:/app/audit_logger.py

if ! grep -q "callbacks: audit_logger.audit_logger" "${CONFIG}"; then
  sudo tee -a "${CONFIG}" > /dev/null <<'YAML'

litellm_settings:
  callbacks: audit_logger.audit_logger
YAML
fi

sudo docker exec ${CONTAINER} \
  rm -f /app/llm-input-audit.jsonl

sudo docker restart ${CONTAINER} > /dev/null

echo "LiteLLM Input/Output Audit enabled."
