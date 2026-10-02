#!/bin/bash
set -e

LITELLM_HOST="192.168.1.101"
LITELLM_USER="ec2-user"
LITELLM_PASS="qwer1234!!"

cat > /tmp/case4_guardrail.py <<'PY'
import re

from litellm.integrations.custom_guardrail import (
    CustomGuardrail,
    log_guardrail_information,
)
from litellm.exceptions import GuardrailRaisedException


class Case4Guardrail(CustomGuardrail):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.patterns = [
            re.compile(
                r"ignore\s+(all\s+)?previous\s+instructions?",
                re.IGNORECASE,
            ),
            re.compile(
                r"you\s+are\s+now\s+(in\s+)?developer\s+mode",
                re.IGNORECASE,
            ),
            re.compile(
                r"system\s+override",
                re.IGNORECASE,
            ),
            re.compile(
                r"reveal\s+(your\s+)?system\s+prompt",
                re.IGNORECASE,
            ),
        ]

    def _extract_texts(self, messages):
        texts = []

        for message in messages or []:
            if not isinstance(message, dict):
                continue

            content = message.get("content", "")

            if isinstance(content, str):
                texts.append(content)

            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            texts.append(text)

        return texts

    @log_guardrail_information
    async def async_pre_call_hook(
        self,
        user_api_key_dict,
        cache,
        data,
        call_type,
    ):
        messages = data.get("messages", [])

        for text in self._extract_texts(messages):
            for pattern in self.patterns:
                if pattern.search(text):
                    raise GuardrailRaisedException(
                        guardrail_name="case4-regex",
                        message="Prompt Injection pattern detected. Request blocked.",
                    )

        return data
PY

cat > /tmp/config.yaml <<'YAML'
model_list:
  - model_name: bedrock-sonnet-4-6
    litellm_params:
      model: bedrock/global.anthropic.claude-sonnet-4-6
      aws_region_name: ap-northeast-2

general_settings:
  master_key: "sk-cnlsg-baseline-changeme"

guardrails:
  - guardrail_name: case4-regex
    litellm_params:
      guardrail: case4_guardrail.Case4Guardrail
      mode: pre_call
      default_on: true
YAML

sshpass -p "${LITELLM_PASS}" scp \
  /tmp/case4_guardrail.py \
  "${LITELLM_USER}@${LITELLM_HOST}:/tmp/case4_guardrail.py"

sshpass -p "${LITELLM_PASS}" scp \
  /tmp/config.yaml \
  "${LITELLM_USER}@${LITELLM_HOST}:/tmp/config.yaml"

sshpass -p "${LITELLM_PASS}" ssh \
  "${LITELLM_USER}@${LITELLM_HOST}" \
  "sudo cp /tmp/case4_guardrail.py /opt/litellm/case4_guardrail.py && \
   sudo cp /tmp/config.yaml /opt/litellm/config.yaml && \
   sudo docker restart litellm"

echo "Case 4 Regex Guardrail applied."
