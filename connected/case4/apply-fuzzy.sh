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

        self.fuzzy_patterns = [
            "ignore",
            "bypass",
            "override",
            "reveal",
            "delete",
            "system",
        ]

    def _is_similar_word(self, word, target):
        word = word.lower()
        target = target.lower()

        if len(word) != len(target):
            return False

        if len(word) < 3:
            return word == target

        return (
            word[0] == target[0]
            and word[-1] == target[-1]
            and sorted(word[1:-1]) == sorted(target[1:-1])
        )

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
                        guardrail_name="case4-fuzzy",
                        message="Prompt Injection pattern detected. Request blocked.",
                    )

            words = re.findall(r"[A-Za-z]+", text)

            for word in words:
                for target in self.fuzzy_patterns:
                    if word.lower() == target:
                        continue

                    if self._is_similar_word(word, target):
                        raise GuardrailRaisedException(
                            guardrail_name="case4-fuzzy",
                            message=f"Typoglycemia detected: {word} -> {target}. Request blocked.",
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
  - guardrail_name: case4-fuzzy
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

echo "Case 4 Fuzzy Guardrail applied."
