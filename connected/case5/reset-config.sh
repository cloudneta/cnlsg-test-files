#!/bin/bash
set -e

cat > /tmp/config.yaml << 'EOF'
model_list:
  - model_name: bedrock-sonnet-4-6
    litellm_params:
      model: bedrock/global.anthropic.claude-sonnet-4-6
      aws_region_name: ap-northeast-2

general_settings:
  master_key: "sk-cnlsg-baseline-changeme"
EOF

# 기본 설정 적용
cat /tmp/config.yaml | sshpass -p 'qwer1234!!' \
ssh ec2-user@192.168.1.101 \
"sudo tee /opt/litellm/config.yaml > /dev/null"

# LiteLLM 재시작
sshpass -p 'qwer1234!!' \
ssh ec2-user@192.168.1.101 \
"sudo docker restart litellm"

# 적용 결과 확인
sshpass -p 'qwer1234!!' \
ssh ec2-user@192.168.1.101 \
"cat /opt/litellm/config.yaml" | yq
