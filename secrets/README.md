# 备用 AI 通道密钥（加密留档）

`bailian.env.enc` 是阿里百炼（DashScope / MaaS 业务空间）备用通道的密钥文件，用项目每日备份的同一把密钥加密，**明文不入库**。

解密（在能拿到 `ops_backup.key` 的机器上）：

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/path/to/ops_backup.key \
  -in secrets/bailian.env.enc -base64 > bailian.env
```

文件内容：

- `BAILIAN_BASE`：业务空间 OpenAI 兼容 base（`https://ws-ndz6stl9aimz7sek.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`）
- `BAILIAN_KEY`：`sk-ws-` 开头的业务空间 API Key

用途：方舟欠费/故障时作为对话（qwen-plus）、识别（qwen3-asr-flash）、朗读（qwen3-tts-flash）的兜底通道。2026-11-28 已下线备用逻辑，仅留档备用。
