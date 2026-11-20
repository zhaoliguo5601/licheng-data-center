#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
立橙数据中心 · LLM 模型网关（零第三方依赖，Python 3 标准库）

作用：
  前端页面只调用本站 /api/llm，由本网关保管上游密钥并转发到
  腾讯混元（WorkBuddy 底层）/ DeepSeek 的 OpenAI 兼容接口。

启动：
  1. 配置环境变量（见文件末尾 / 页面上的示例）
  2. python3 llm_gateway.py
  3. 前端把 /api/llm、/api/health 指向本服务（默认 8788 端口）

上游协议：OpenAI Chat Completions
  POST {base}/chat/completions
  Authorization: Bearer {key}
"""

import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------- 上游配置（环境变量注入，勿把 Key 写进代码） ----------------
UPSTREAMS = {
    "hunyuan": {
        "base": os.environ.get("HUNYUAN_BASE", "https://tokenhub.tencentmaas.com/v1"),
        "model": os.environ.get("HUNYUAN_MODEL", "hy4-flash"),
        "key": os.environ.get("HUNYUAN_KEY", ""),
    },
    "deepseek": {
        "base": os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com"),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "key": os.environ.get("DEEPSEEK_KEY", ""),
    },
}

PORT = int(os.environ.get("GATEWAY_PORT", "8788"))
TIMEOUT = 60


def call_upstream(provider, messages):
    """转发到上游 OpenAI 兼容接口，返回纯文本回复。"""
    cfg = UPSTREAMS.get(provider)
    if not cfg:
        raise ValueError(f"未知模型渠道：{provider}")
    if not cfg["key"]:
        raise RuntimeError(f"{provider} 未配置 API Key（环境变量缺失）")

    url = cfg["base"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['key']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("上游返回为空")
    return choices[0].get("message", {}).get("content", "").strip()


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path in ("/api/health", "/health"):
            ready = {k: bool(v["key"]) for k, v in UPSTREAMS.items()}
            self._json(200, {"ok": True, "upstreams": ready})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path not in ("/api/llm", "/api/chat"):
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            provider = body.get("provider", "hunyuan")
            messages = body.get("messages") or []
            if not messages:
                raise ValueError("messages 为空")

            reply = call_upstream(provider, messages)
            self._json(200, {"ok": True, "provider": provider, "reply": reply})
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")[:300]
            self._json(502, {"ok": False, "error": f"上游错误 {e.code}", "detail": detail})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def log_message(self, fmt, *args):
        print("[llm-gateway]", fmt % args)


if __name__ == "__main__":
    print(f"立橙 LLM 网关启动于 :{PORT}  | 渠道: {', '.join(UPSTREAMS.keys())}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
