#!/bin/bash
set -e

LITELLM_HOST="192.168.1.101"
LITELLM_USER="ec2-user"
LITELLM_PASS="qwer1234!!"

# LiteLLM Input Guardrail 생성
# - AWS Access Key : BLOCK
# - 주민등록번호   : MASK
# - Guardrail 처리 전/후 Audit 기록
cat > /tmp/input_guardrail.py <<'PY'
import json
import re
from datetime import datetime, timezone

from litellm.integrations.custom_guardrail import (
    CustomGuardrail,
    log_guardrail_information,
)
from litellm.exceptions import GuardrailRaisedException

AUDIT_FILE = "/app/llm-input-audit.jsonl"

AWS_ACCESS_KEY_PATTERN = re.compile(
    r"\bAKIA[0-9A-Z]{16}\b"
)

RRN_PATTERN = re.compile(
    r"\b(\d{6})-(\d)\d{6}\b"
)


class InputGuardrail(CustomGuardrail):

    def __init__(self, **kwargs):
        self.optional_params = kwargs
        super().__init__(**kwargs)

    def _write_audit(self, source, action, input_value, output_value):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "action": action,
            "input": input_value,
            "output": output_value,
        }

        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _process_text(self, text, source):

        # AWS Access Key 탐지 → 원문 기록 후 Provider 전달 차단
        if AWS_ACCESS_KEY_PATTERN.search(text):
            self._write_audit(
                source=source,
                action="BLOCK",
                input_value=text,
                output_value=None,
            )

            raise GuardrailRaisedException(
                message="AWS Access Key detected. Request blocked.",
                guardrail_name="input-security",
            )

        # 주민등록번호 탐지 → 원문과 마스킹 결과 기록
        masked_text = RRN_PATTERN.sub(
            r"\1-\2******",
            text,
        )

        if masked_text != text:
            self._write_audit(
                source=source,
                action="MASK",
                input_value=text,
                output_value=masked_text,
            )

        return masked_text

    @log_guardrail_information
    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data,
        call_type,
    ):
        messages = data.get("messages", [])

        for message in messages:
            content = message.get("content")

            if isinstance(content, str):
                message["content"] = self._process_text(
                    content,
                    message.get("role", "message"),
                )
                continue

            if not isinstance(content, list):
                continue

            for item in content:
                if not isinstance(item, dict):
                    continue

                # 일반 Text Message
                if item.get("type") == "text":
                    text = item.get("text")

                    if isinstance(text, str):
                        item["text"] = self._process_text(
                            text,
                            "user",
                        )

                # Claude Code가 Tool로 읽은 실제 데이터
                elif item.get("type") == "tool_result":
                    text = item.get("content")

                    if isinstance(text, str):
                        item["content"] = self._process_text(
                            text,
                            "tool_result",
                        )

        return data
PY

# Guardrail 파일 전송
sshpass -p "${LITELLM_PASS}" \
scp /tmp/input_guardrail.py \
${LITELLM_USER}@${LITELLM_HOST}:/tmp/input_guardrail.py

# Guardrail 배치 및 컨테이너 반영
sshpass -p "${LITELLM_PASS}" \
ssh ${LITELLM_USER}@${LITELLM_HOST} \
"sudo mv /tmp/input_guardrail.py /opt/litellm/input_guardrail.py && \
sudo docker cp /opt/litellm/input_guardrail.py litellm:/app/input_guardrail.py"

# LiteLLM Guardrail 설정
sshpass -p "${LITELLM_PASS}" \
ssh ${LITELLM_USER}@${LITELLM_HOST} \
"sudo tee -a /opt/litellm/config.yaml > /dev/null <<'YAML'

guardrails:
  - guardrail_name: input-security
    litellm_params:
      guardrail: input_guardrail.InputGuardrail
      mode: pre_call
      default_on: true
YAML
sudo docker restart litellm > /dev/null"

# CN-ADMIN 임시 파일 삭제
rm -f /tmp/input_guardrail.py

echo
echo "LiteLLM Input Guardrail enabled."
echo "  AWS Access Key : BLOCK"
echo "  RRN            : MASK"
