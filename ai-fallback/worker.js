/* 立橙数据中心 · AI 备用通道（Cloudflare Worker）
 * 主链路是阿里云 FC（火山方舟），火山账户欠费时会 403；
 * 这里用阿里百炼顶上：对话 qwen-plus、识别 qwen3-asr-flash、朗读 qwen3-tts-flash。
 * 接口与原 FC 保持同形：/api/chat、/api/asr/recognize、/api/tts、/api/models
 */
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};
const json = (d, s = 200) => new Response(JSON.stringify(d), { status: s, headers: { "Content-Type": "application/json; charset=utf-8", ...CORS } });
const BL_BASE = "https://dashscope.aliyuncs.com";
const BL_COMPAT = "https://ws-ndz6stl9aimz7sek.cn-beijing.maas.aliyuncs.com/compatible-mode/v1";
const ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3";
const SYSTEM_PROMPT = "你是立橙数据中心（站立的立、橙子的橙）的智能助手，用简体中文、口语化、清楚友好地回答问题。先给结论，再补充必要理由；能一句话说清就不啰嗦，复杂问题可分点简述。";
const MODELS = {
  lite: "doubao-seed-2-1-lite-260915", turbo: "doubao-seed-2-1-turbo-260628", pro: "doubao-seed-2-1-pro-260915",
  "d2-lite": "doubao-seed-2-0-lite-260428", "d2-mini": "doubao-seed-2-0-mini-260428", char: "doubao-seed-character-260628",
  glm: "glm-5-3-flash-260828", "glm-2": "glm-5-2-260617", kimi: "kimi-k3-1-pro-261024",
  ds: "deepseek-v4-1-flash-261017", "ds-econ": "deepseek-v4-1-flash-economy-261017",
  "ds-flash": "deepseek-v4-flash-ga-260731", "ds-pro": "deepseek-v4-pro-ga-260813",
};
async function bailianChat(env, messages) {
  const r = await fetch(BL_COMPAT + "/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.BAILIAN_KEY}` },
    body: JSON.stringify({ model: env.BAILIAN_MODEL || "qwen-plus", messages, temperature: 0.7, max_tokens: 800 }),
  });
  const d = await r.json().catch(() => ({}));
  const txt = d?.choices?.[0]?.message?.content || "";
  return { ok: r.ok && !!txt, txt, status: r.status, raw: d };
}
async function handleChat(req, env) {
  const body = await req.json().catch(() => ({}));
  const key = body.model === "auto" ? "d2-mini" : (MODELS[body.model] ? body.model : "lite");
  const messages = [{ role: "system", content: SYSTEM_PROMPT }, ...(Array.isArray(body.messages) ? body.messages.slice(-10) : [])];
  /* 先用火山方舟（充值后自动回到主力），失败立刻转百炼 */
  let arkErr = null;
  if (env.ARK_API_KEY) {
    try {
      const r = await fetch(ARK_BASE + "/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.ARK_API_KEY}` },
        body: JSON.stringify({ model: MODELS[key], messages, temperature: 0.7, max_tokens: 800 }),
      });
      if (r.ok) {
        const d = await r.json();
        const txt = d?.choices?.[0]?.message?.content || "";
        if (txt) return json({ reply: txt, key, channel: "ark", color: null });
      }
      arkErr = r.status;
    } catch (e) { arkErr = "net"; }
  }
  const bl = await bailianChat(env, messages);
  if (!bl.ok) return json({ error: "bailian_" + (bl.status || "fail"), reply: "我现在连不上模型，稍后再试一次。", ark: arkErr }, 502);
  return json({ reply: bl.txt, key, channel: "bailian", color: null });
}
async function handleAsr(req, env) {
  const body = await req.json().catch(() => ({}));
  const data = typeof body.data === "string" ? body.data : "";
  const url = typeof body.url === "string" ? body.url : "";
  if (!data && !url) return json({ error: "empty_audio" }, 400);
  const audio = url ? url : "data:audio/" + (body.format || "wav") + ";base64," + data;
  const r = await fetch(BL_BASE + "/api/v1/services/aigc/multimodal-generation/generation", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.BAILIAN_KEY}` },
    body: JSON.stringify({ model: "qwen3-asr-flash", input: { messages: [{ role: "user", content: [{ audio }] }] } }),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return json({ error: "asr_" + r.status, reply: "识别服务暂时不可用，请稍后再试。" }, 502);
  const parts = d?.output?.choices?.[0]?.message?.content || [];
  let text = "";
  if (Array.isArray(parts)) { for (const p of parts) if (typeof p === "string") text += p; else if (p && p.text) text += p.text; }
  else if (typeof parts === "string") text = parts;
  return json({ ok: true, text: text.trim(), channel: "bailian" });
}
async function handleTts(req, env) {
  const body = await req.json().catch(() => ({}));
  const text = (body.text || "").toString().slice(0, 600);
  if (!text) return json({ error: "empty_text" }, 400);
  const r = await fetch(BL_BASE + "/api/v1/services/aigc/multimodal-generation/generation", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.BAILIAN_KEY}` },
    body: JSON.stringify({ model: "qwen3-tts-flash", input: { text, voice: env.TTS_VOICE || "Cherry" } }),
  });
  const d = await r.json().catch(() => ({}));
  const u = d?.output?.audio?.url || "";
  if (!r.ok || !u) return json({ error: "tts_" + (r.status || "no_url"), reply: "语音合成暂时不可用。" }, 502);
  const a = await fetch(u);
  if (!a.ok) return json({ error: "tts_fetch", reply: "语音合成暂时不可用。" }, 502);
  const buf = new Uint8Array(await a.arrayBuffer());
  let b64 = "";
  const chunk = 0x8000;
  for (let i = 0; i < buf.length; i += chunk) b64 += String.fromCharCode.apply(null, buf.subarray(i, i + chunk));
  b64 = btoa(b64);
  return json({ format: "wav", audio: b64, text });
}
export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    try {
      if (req.method === "GET" && u.pathname === "/api/health") return json({ ok: true, ark: !!env.ARK_API_KEY, bailian: !!env.BAILIAN_KEY });
      if (req.method === "GET" && u.pathname === "/api/models") return json({ models: [{ key: "auto", name: "自动分派（母AI调度）", color: "#45e6f5", available: true }] });
      if (req.method === "POST" && u.pathname === "/api/chat") return handleChat(req, env);
      if (req.method === "POST" && u.pathname === "/api/asr/recognize") return handleAsr(req, env);
      if (req.method === "POST" && u.pathname === "/api/tts") return handleTts(req, env);
      return json({ error: "not_found" }, 404);
    } catch (e) { return json({ error: "worker_error", detail: String(e) }, 500); }
  },
};
