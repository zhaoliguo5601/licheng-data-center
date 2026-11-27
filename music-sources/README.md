# 立橙音乐 · 音源备份

本目录**只放经实测能用的音源**，供 LX Music / 立橙音乐服务调用，作为仓库级备份。

## 怎么来的

2026-11-27 从三个公开仓库抓取全部脚本，逐个在 LX 官方自定义源宿主机协议（`node:vm` + `lx.request` 契约）里跑一遍：

- `wangshiyulin/LXmusic-source`（19 个）
- `liuyunss/LX-source`（9 个）
- `Jasiav/lxmusic`（8 个）

合计 36 个，去重后按统一标准验收：**初始化成功 → 声明酷狗源 → 用固定样本（告白气球，hash `688857974673645…`）取链 → 直链 HEAD 必须 200**。

## 留下什么

见 `index.json`，当前 4 个：

| 文件 | 来源 | 结论 |
|---|---|---|
| 星海音乐源-v3.2.20-线上在用.js | pdone/lx-music-source | 生产在用，已上线验证 |
| K×H-v1.7.17.js | wangshiyulin/LXmusic-source | kg 取链 1.09s，HEAD 200 |
| 全豆要聚合音源-v9.3.js | wangshiyulin/LXmusic-source | kg 取链 2.0s，HEAD 200 |
| hy.js | Jasiav/lxmusic | 真酷狗 fsandroid 直链，0.9s |

## 剔掉了什么（36 → 4）

- **完全重复**：`聚合API接口.js` = `jh.js`；`野花音源.js` = `yh.js`；`野草音源.js` = `yc.js`
- **反篡改自毁**：六音 3 个版本（v1.2.0 / v1.2.1 / encrypt），跑起来直接报错并指向 sixyin.com
- **元数据不全，拒绝初始化**：`jh.js`（1KB 版）、`聚合API接口.js`
- **不声明酷狗源**：`ikun.js`、`yc.js`、`野草音源.js`
- **卡密/授权过期**：`HYWmusic-beta.js`（提示卡密过期，指向 103.79.184.97）
- **IP 被对方封**：`lx-music-source-v5.js`（`block ip`）
- **后端当时不可达**：星海 v2.3.15（503）、长青（haitangw 522）、墨澜/`st.js`（16 个后端全无数据）、`huibq.js`/`nya.js`/`lx-music.js`/`肥猫不肥.js`（unknow error）等

最后这一类是**服务端侧问题，不是脚本坏了**。对方恢复了仍可能可用，需要时再复测，别照着名单一概判死。

## 链式回退（生产落地版）

把音源脚本的取链逻辑**逐个复刻成直连 HTTP 解析器**，不跑 `node:vm`，所以能直接放进 Cloudflare Pages Function / Worker。两个文件：

- `resolvers.js` — 8 个后端按命中率排序，`resolveChain()` 逐路回退，`alive()` 用 Range 取 1KB 验活（要 200/206 且 `content-type` 是音频类）
- `pages-function.js` — Pages Function 主体，路由 `health` / `search` / `url|resolve` / `lyric` / `play` / `selftest` / `stream`

回退顺序（`resolvers.js` 里 `BACKENDS`）：

| # | 后端 | 端点 | 2026-11-27 |
|---|---|---|---|
| 0 | xinghai | `yy1.zddyr.top/lx/api/` + `token.php` | 可用 0.98s |
| 1 | nianxin | `mcp.nianxinxz.com/share/ceshi/kg.php` | 可用 1.06s |
| 2 | gdstudio | `music-api.gdstudio.xyz/api.php` | 503 上游超时 |
| 3 | haitangw | `music.haitangw.cc/kgqq/kg.php` | code=201 |
| 4 | xinghai-legacy | `yy.zddyr.top/lx/api/` | 503 |
| 5 | huibq | `api.huibq.com/api/url/kg/<hash>` | DNS 失败 |
| 6 | lingchuan | `api.lingchuan.com/v1/url` | DNS 失败 |
| 7 | hyw | `103.79.184.97/api/music/url`（key 内置） | 可用 1.67s |

后 6 个不是判死，是**服务端侧当时故障**；回退链会自动跳过，恢复了自动回归。整链调用返回 `{url, via, viaId, index, tried}`，`tried` 里带每一路成败，便于线上定位。

线上实测（`https://lcdc.pages.dev/api/music/`）：搜索「告白气球」480 条、取链走星海 0.9s、`/stream` 代理 206、歌词 51 行、`selftest` 状态码 200（=200+命中序号，599=全挂）。

## 用法

脚本是第三方作者的作品，只在自用场景调用，不转售、不公开分发；上游更新后请重新下载替换，不要长期用旧版。

一份可直接执行的验收命令（在装好 `music-service` 的机器上）：

```bash
node /path/to/tester.js /path/to/usable/xxx.js
```

输出里 `kg` 字段以 `OK` 开头即为通过。
