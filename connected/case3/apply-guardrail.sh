#!/bin/bash
set -e

LITELLM_DIR="/opt/litellm"
CONTAINER="litellm"
CONFIG="${LITELLM_DIR}/config.yaml"

cat <<'PY' | sudo tee ${LITELLM_DIR}/input_guardrail.py > /dev/null
import re

from litellm.integrations.custom_guardrail import (
    CustomGuardrail,
    log_guardrail_information,
)

AWS_ACCESS_KEY_PATTERN = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
RRN_PATTERN = re.compile(r"\b(\d{6})-(\d)\d{6}\b")


class InputGuardrail(CustomGuardrail):

    def __init__(self, **kwargs):
        self.optional_params = kwargs
        super().__init__(**kwargs)

    def _process_text(self, text):
        if AWS_ACCESS_KEY_PATTERN.search(text):
            raise ValueError(
                "AWS Access Key detected. Request blocked."
            )

        return RRN_PATTERN.sub(
            r"\1-\2******",
            text,
        )

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
                message["content"] = self._process_text(content)
                continue

            if not isinstance(content, list):
                continue

            for item in content:
                if not isinstance(item, dict):
                    continue

                if item.get("type") == "text":
                    text = item.get("text")

                    if isinstance(text, str):
                        item["text"] = self._process_text(text)

                elif item.get("type") == "tool_result":
                    text = item.get("content")

                    if isinstance(text, str):
                        item["content"] = self._process_text(text)

        return data


input_guardrail = InputGuardrail
PY

sudo docker cp \
  ${LITELLM_DIR}/input_guardrail.py \
  ${CONTAINER}:/app/input_guardrail.py

if ! grep -q "guardrail_name: input-security" "${CONFIG}"; then
  sudo tee -a "${CONFIG}" > /dev/null <<'YAML'

guardrails:
  - guardrail_name: input-security
    litellm_params:
      guardrail: input_guardrail.InputGuardrail
      mode: pre_call
      default_on: true
YAML
fi

sudo docker restart ${CONTAINER} > /dev/null

echo "LiteLLM Input Guardrail enabled."
echo "  AWS Access Key : BLOCK"
echo "  RRN            : MASK"
