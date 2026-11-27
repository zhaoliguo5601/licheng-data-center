// 立橙音乐 · 多源取链解析器（无 vm 版，可在 Pages Function / Worker / Node 通用运行）
// 设计：每个后端是一个 resolve(ctx) → 直链；resolveChain 依次尝试，HEAD 验活后才算命中。
// ctx: { hash, hq, sq, albumId, name, singer, duration, quality, album }
// 返回：{ url, via, index, quality, tried:[{id,ok,ms,msg}] }

const UA_PC = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
const UA_APP = 'LX-Music-Mobile'

const Q = {
  '128k': '320kmp3', '320k': '320kmp3', 'flac': 'flac',
  'hires': 'flac', 'atmos': 'flac', 'master': 'flac',
}
const brOf = (q) => (q === '128k' ? '128' : q === 'flac' ? '2000' : '320')

async function jget(url, opts = {}) {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), opts.timeout || 6500)
  try {
    const r = await fetch(url, { headers: opts.headers || { 'User-Agent': UA_APP }, signal: ctl.signal })
    const txt = await r.text()
    let j = null
    try { j = JSON.parse(txt) } catch {}
    return { status: r.status, json: j, text: txt }
  } finally { clearTimeout(t) }
}

/* ---------- 星海（服务端签令牌，xh3 前缀） ---------- */
const XH = { base: 'https://yy1.zddyr.top/lx/api/', tokenUrl: 'https://yy1.zddyr.top/lx/api/token.php', backup: 'https://yy.zddyr.top/lx/api/' }
let xhTok = { tk: '', at: 0, dev: '' }

function xhDevice() {
  if (!xhTok.dev) xhTok.dev = 'lcdc-' + Array.from(crypto.getRandomValues(new Uint8Array(8)))
    .map((b) => b.toString(16).padStart(2, '0')).join('')
  return xhTok.dev
}
async function xhToken(force) {
  if (!force && xhTok.tk && Date.now() - xhTok.at < 240000) return xhTok.tk
  const j = await jget(`${XH.tokenUrl}?device_id=${encodeURIComponent(xhDevice())}`, { timeout: 6000 })
  const tk = j.json && j.json.data && j.json.data.token
  if (typeof tk !== 'string' || !tk) throw new Error('令牌签发失败 HTTP ' + j.status)
  xhTok = { ...xhTok, tk, at: Date.now() }
  return tk
}

/* ---------- 后端清单（按命中率排序，逐个回退） ---------- */
export const BACKENDS = [
  {
    id: 'xinghai', label: '星海(令牌)',
    async resolve(c) {
      const q = Q[c.quality] || '320kmp3'
      const p = new URLSearchParams({
        source: 'kg', quality: q, songmid: c.hash, albumId: c.albumId || '',
        mainHash: c.hash, hash: c.hash,
      })
      let last = ''
      for (let i = 0; i < 2; i++) {
        const tk = await xhToken(i > 0)
        const j = await jget(XH.base + '?' + p.toString(), { headers: { 'User-Agent': UA_APP, 'X-Token': tk, 'X-Client': UA_APP }, timeout: 7000 })
        if (j.json && j.json.code === 200 && j.json.url) return j.json.url
        last = (j.json && j.json.msg) || ('HTTP ' + j.status)
      }
      throw new Error(last)
    },
  },
  {
    id: 'nianxin', label: '念心',
    async resolve(c) {
      const lv = Q[c.quality] || '320kmp3'
      const j = await jget(`https://mcp.nianxinxz.com/share/ceshi/kg.php?id=${c.hash}&level=${lv}`, { headers: { 'User-Agent': UA_PC } })
      if (j.json && j.json.code === 200 && j.json.url) return j.json.url
      throw new Error('code=' + (j.json && j.json.code) + ' ' + (j.json && j.json.msg || ''))
    },
  },
  {
    id: 'gdstudio', label: 'GD Studio',
    async resolve(c) {
      const u = 'https://music-api.gdstudio.xyz/api.php?use_xbridge3=true&loader_name=forest&need_sec_link=1' +
        `&sec_link_scene=im&theme=light&types=url&source=kugou&id=${c.hash}&br=${brOf(c.quality)}`
      const j = await jget(u, { headers: { 'User-Agent': UA_PC } })
      const url = j.json && (j.json.url || (Array.isArray(j.json) && j.json[0] && j.json[0].url))
      if (url) return url
      throw new Error('无 url HTTP ' + j.status)
    },
  },
  {
    id: 'haitangw', label: '海棠',
    async resolve(c) {
      const lv = c.quality === 'flac' ? 'flac' : 'exhigh'
      const j = await jget(`https://music.haitangw.cc/kgqq/kg.php?type=mp3&id=${c.hash}&level=${lv}`, { headers: { 'User-Agent': UA_PC } })
      if (j.json && j.json.url) return j.json.url
      throw new Error('code=' + (j.json && j.json.code) + ' ' + (j.json && j.json.msg || ''))
    },
  },
  {
    id: 'xinghai-legacy', label: '星海(旧接口)',
    async resolve(c) {
      const name = (c.name || '') + (c.singer ? ' ' + c.singer : '')
      const q = Q[c.quality] || '320kmp3'
      const j = await jget(`${XH.backup}?source=kg&name=${encodeURIComponent(name)}&songmid=${c.hash}&quality=${q}`, { headers: { 'User-Agent': UA_APP } })
      if (j.json && j.json.code === 200 && j.json.url) return j.json.url
      throw new Error('code=' + (j.json && j.json.code) + ' HTTP ' + j.status)
    },
  },
  {
    id: 'huibq', label: 'Huibq',
    async resolve(c) {
      const j = await jget(`https://api.huibq.com/api/url/kg/${c.hash}/${c.quality}`, { headers: { 'User-Agent': UA_PC } })
      const url = j.json && (j.json.url || (j.json.data && j.json.data.url))
      if (url) return url
      throw new Error('无 url HTTP ' + j.status)
    },
  },
  {
    id: 'lingchuan', label: '灵川',
    async resolve(c) {
      const j = await jget(`https://api.lingchuan.com/v1/url?source=kg&songId=${c.hash}&quality=${c.quality}`, { headers: { 'User-Agent': UA_PC } })
      const url = j.json && (j.json.url || (j.json.data && j.json.data.url))
      if (url) return url
      throw new Error('无 url HTTP ' + j.status)
    },
  },
  {
    id: 'hyw', label: 'HYW 公益版',
    async resolve(c) {
      const q2 = new URLSearchParams({
        platform: 'kg', source: 'kg', songmid: c.hash, hash: c.hash,
        name: c.name || '', singer: c.singer || '', albumId: c.albumId || '',
        quality: c.quality || '320k', key: '6C1F-53W0-GRKI-EVFG',
      })
      const j = await jget(`http://103.79.184.97/api/music/url?${q2.toString()}`, { headers: { 'User-Agent': UA_APP }, timeout: 8000 })
      if (j.json && j.json.code === 200 && j.json.url) return j.json.url
      throw new Error('code=' + (j.json && j.json.code) + ' ' + (j.json && j.json.msg || ''))
    },
  },
]

/* ---------- 验活：能取到音频头才算数 ---------- */
async function alive(url) {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), 4500)
  try {
    const r = await fetch(url, {
      method: 'GET',
      headers: { Range: 'bytes=0-1023', 'User-Agent': UA_PC },
      signal: ctl.signal,
    })
    const ct = r.headers.get('content-type') || ''
    const len = Number(r.headers.get('content-range') || '').toString()
    const okStatus = r.status === 200 || r.status === 206
    const audioLike = /audio|octet-stream|mpegurl|mp4|m4a/i.test(ct) || !ct
    if (!okStatus) return { ok: false, msg: 'HTTP ' + r.status }
    if (!audioLike) return { ok: false, msg: 'ct=' + ct.slice(0, 24) }
    if (r.body) { try { r.body.cancel() } catch {} }
    return { ok: true, msg: 'HTTP ' + r.status + ' ' + ct.slice(0, 18) + (len ? ' bytes=' + len : '') }
  } catch (e) {
    return { ok: false, msg: '取流失败: ' + (e.message || '') }
  } finally { clearTimeout(t) }
}

export async function resolveChain(ctx, opts = {}) {
  const tried = []
  const limit = opts.limit || BACKENDS.length
  for (let i = 0; i < Math.min(limit, BACKENDS.length); i++) {
    const b = BACKENDS[i]
    const t0 = Date.now()
    try {
      const url = await b.resolve(ctx)
      if (!/^https?:\/\//.test(url)) throw new Error('返回非直链')
      const live = opts.skipVerify ? { ok: true, msg: 'skip' } : await alive(url)
      if (!live.ok) throw new Error(live.msg)
      tried.push({ id: b.id, ok: true, ms: Date.now() - t0, msg: live.msg })
      return { url, via: b.label, viaId: b.id, index: i, quality: ctx.quality || '320k', tried }
    } catch (e) {
      tried.push({ id: b.id, ok: false, ms: Date.now() - t0, msg: String((e && e.message) || e).slice(0, 70) })
    }
  }
  const err = new Error('全部音源均失败：' + tried.map((t) => t.id + '(' + t.msg + ')').join(' / '))
  err.tried = tried
  throw err
}

export function backendIds() {
  return BACKENDS.map((b) => b.id)
}
