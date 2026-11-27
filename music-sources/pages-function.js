// 立橙音乐服务 · Pages Function（同域 /api/music/*）
// 搜索/歌词走酷狗公开接口；取播放链接走多源回退链（resolvers.js），一路失败自动换下一个。
import { resolveChain, BACKENDS } from './resolvers.js'

const UA_PC = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'
const SEARCH_URL = 'https://songsearch.kugou.com/song_search_v2'
const KRCS = 'https://krcs.kugou.com/search'
const LRC_DL = 'https://lyrics.kugou.com/download'

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Allow-Methods': 'GET,OPTIONS',
}

// URL 缓存：同一首歌 4 分钟内不重复取链
const cache = new Map()
const CACHE_TTL = 240000

function json(code, obj) {
  return new Response(JSON.stringify(obj), {
    status: code,
    headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }, CORS),
  })
}

const mb = (n) => (n ? (n / 1048576).toFixed(1) + 'MB' : '')

function mapKg(raw) {
  const hashes = {}, sizes = {}
  if (raw.FileHash && raw.FileSize) { hashes['128k'] = raw.FileHash; sizes['128k'] = mb(raw.FileSize) }
  if (raw.HQFileHash && raw.HQFileSize) { hashes['320k'] = raw.HQFileHash; sizes['320k'] = mb(raw.HQFileSize) }
  if (raw.SQFileHash && raw.SQFileSize) { hashes['flac'] = raw.SQFileHash; sizes['flac'] = mb(raw.SQFileSize) }
  return {
    source: 'kg', id: raw.FileHash, songmid: raw.FileHash, hash: raw.FileHash,
    name: raw.SongName || '', singer: raw.SingerName || '', album: raw.AlbumName || '',
    albumId: raw.AlbumID || '', duration: raw.Duration || 0,
    hashes, sizes, qualitys: Object.keys(hashes),
  }
}

async function search(q, page, limit) {
  const url = `${SEARCH_URL}?platform=AndroidFilter&iscorrection=1&keyword=${encodeURIComponent(q)}` +
    `&hifiquality=0&pagesize=${limit}&PrivilegeFilter=0&page=${page}`
  const r = await fetch(url, { headers: { 'User-Agent': UA_PC } })
  const b = await r.json().catch(() => null)
  if (!b || b.status !== 1 || !b.data) throw new Error('酷狗搜索异常 HTTP ' + r.status)
  return {
    total: b.data.total || 0, page: b.data.page || page, pageSize: b.data.pagesize || limit,
    items: (b.data.lists || []).map(mapKg).filter((i) => i.id),
  }
}

function parseLrc(text) {
  const out = []
  for (const raw of String(text || '').split(/\r?\n/)) {
    const tags = raw.match(/\[[0-9]{1,2}:[0-9]{1,2}(?:[.:][0-9]{1,3})?\]/g)
    if (!tags) continue
    const body = raw.replace(/\[[^\]]*\]/g, '').trim()
    if (!body) continue
    for (const tag of tags) {
      const m = tag.match(/\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]/)
      if (!m) continue
      const t = Number(m[1]) * 60 + Number(m[2]) + (m[3] ? Number('0.' + m[3]) : 0)
      out.push({ t: +t.toFixed(2), s: body })
    }
  }
  out.sort((a, b) => a.t - b.t)
  return out
}

async function lyric(sp) {
  const hash = sp.get('hash') || ''
  if (!hash) throw new Error('缺少 hash')
  const qs = new URLSearchParams({
    ver: '1', man: 'yes', client: 'mobi',
    keyword: sp.get('name') ? sp.get('name') + ' ' + (sp.get('singer') || '') : '',
    duration: String(Number(sp.get('duration') || 0)), hash,
    album_id: sp.get('albumId') || '', lrcx: '1',
  })
  const r = await fetch(KRCS + '?' + qs.toString(), { headers: { 'User-Agent': UA_PC } })
  const b = await r.json().catch(() => null)
  const cand = b && b.candidates && b.candidates[0]
  if (!cand || !cand.id || !cand.accesskey) return { lines: [], note: '无歌词候选' }
  const dl = await fetch(`${LRC_DL}?ver=1&client=pc&id=${cand.id}&accesskey=${cand.accesskey}&fmt=lrc&charset=utf8`, {
    headers: { 'User-Agent': UA_PC },
  })
  const d = await dl.json().catch(() => null)
  if (!d || !d.content) return { lines: [], note: '歌词下载失败' }
  let txt = ''
  try {
    const bytes = Uint8Array.from(atob(d.content), (c) => c.charCodeAt(0))
    txt = new TextDecoder('utf-8').decode(bytes)
  } catch (e) { throw new Error('歌词解码失败') }
  const lines = parseLrc(txt)
  return { lines, count: lines.length, song: cand.song, singer: cand.singer }
}

function ctxOf(sp, quality) {
  const hash = sp.get('hash') || ''
  if (!hash) throw new Error('缺少 hash')
  return {
    hash, hq: sp.get('hq') || '', sq: sp.get('sq') || '',
    albumId: sp.get('albumId') || '', name: sp.get('name') || '', singer: sp.get('singer') || '',
    duration: Number(sp.get('duration') || 0), quality: quality || sp.get('quality') || '320k',
  }
}

async function urlOf(sp, quality) {
  const c = ctxOf(sp, quality)
  const key = [c.hash, c.hq, c.sq, c.quality].join('|')
  const hit = cache.get(key)
  if (hit && Date.now() - hit.at < CACHE_TTL) return Object.assign({ cached: true }, hit.v)
  const r = await resolveChain(c)
  const v = { url: r.url, via: r.via, viaId: r.viaId, quality: r.quality, tried: r.tried }
  cache.set(key, { v, at: Date.now() })
  if (cache.size > 300) cache.delete(cache.keys().next().value)
  return Object.assign({ cached: false }, v)
}

async function stream(request, target) {
  const r = await fetch(target, {
    headers: Object.assign(
      { 'User-Agent': UA_PC },
      request.headers.get('range') ? { Range: request.headers.get('range') } : {},
    ),
  })
  const h = new Headers(CORS)
  h.set('Content-Type', r.headers.get('content-type') || 'audio/mpeg')
  h.set('Accept-Ranges', 'bytes')
  h.set('Cache-Control', 'public, max-age=3600')
  for (const k of ['content-length', 'content-range']) {
    const v = r.headers.get(k)
    if (v) h.set(k, v)
  }
  return new Response(r.body, { status: r.status, headers: h })
}

export async function onRequest(context) {
  const { request } = context
  const u = new URL(request.url)
  const act = u.pathname.replace(/^\/api\/music\/?/, '').replace(/\/$/, '')
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS })

  try {
    if (act === 'health') {
      return json(200, {
        ok: true, service: 'lcdc-music', sources: BACKENDS.map((b) => b.id), count: BACKENDS.length,
      })
    }
    if (act === 'search') {
      const kw = (u.searchParams.get('kw') || '').trim()
      if (!kw) return json(400, { ok: false, msg: '缺少 kw' })
      const page = Math.max(1, Number(u.searchParams.get('page') || 1))
      const limit = Math.min(Number(u.searchParams.get('limit') || 20), 40)
      return json(200, Object.assign({ ok: true }, await search(kw, page, limit)))
    }
    if (act === 'url' || act === 'resolve') {
      return json(200, Object.assign({ ok: true }, await urlOf(u.searchParams, u.searchParams.get('quality'))))
    }
    if (act === 'lyric') {
      return json(200, Object.assign({ ok: true }, await lyric(u.searchParams)))
    }
    if (act === 'play') {
      const rr = await urlOf(u.searchParams, '320k')
      const res = await stream(new Request(rr.url, { headers: { Range: 'bytes=0-65535' } }), rr.url)
      return json(200, { ok: true, via: rr.via, status: res.status, ct: (res.headers.get('content-type') || '').slice(0, 30) })
    }
    // 自检：状态码 = 200 + 命中源序号（0 星海 / 1 念心 …），599 = 全挂。外部探针只看状态码即可判断
    if (act === 'selftest') {
      try {
        const r = await resolveChain({
          hash: '688857974673645CE89EDA26A36DB19D', hq: '646035C6C56D18A4C7785F6008BD4820',
          sq: '3206E5C3880F5E0E47FCD8671449A9D2', albumId: '1645030',
          name: '告白气球', singer: '周杰伦', quality: '320k',
        })
        return json(200 + r.index, { ok: true, via: r.via, index: r.index, url: r.url.slice(0, 70), tried: r.tried })
      } catch (e) {
        return json(599, { ok: false, msg: e.message, tried: e.tried || [] })
      }
    }
    if (act === 'stream') {
      const t = u.searchParams.get('u') || ''
      if (!/^https?:\/\//.test(t)) return json(400, { ok: false, msg: 'u 非法' })
      return await stream(request, t)
    }
    return json(404, { ok: false, msg: 'not found', act })
  } catch (e) {
    return json(502, { ok: false, msg: e.message || String(e), tried: e.tried || [] })
  }
}
