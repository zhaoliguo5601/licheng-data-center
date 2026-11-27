# 立橙 · 数据中心（LICHENG DATA CENTER）

立橙自研的数据大屏仓库：一块**神经星环**首页 + 一块**数据看板**大屏 + 一个**安卓 WebView 壳**（APK）。
页面为单文件自包含 HTML，不需要构建，浏览器直接打开就能跑。

线上：<https://lcdc.pages.dev/>（首页星环）· `/dashboard`（数据看板）· `/music`（独立音乐页）

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `index.html` | 首页神经星环（单文件，样式与脚本内联；含对话、音乐播放器、离线缓存注册） |
| `dashboard.html` | 数据看板大屏（宽屏设计：源码仓库 / 数据中枢 / 素材归档 / 模型通道 / 跨域延迟） |
| `sw.js` | 离线缓存（详见下文「离线缓存」） |
| `version.json` | APP 版本号、包体大小与 md5、更新说明、APK 地址 |
| `config.json` | 页面运行时配置（接口地址等） |
| `data.json`、`data/` | 台账快照（采集闭环生成，页面优先读快照） |
| `music-sources/` | 音乐聚合源镜像与说明（酷狗单平台） |
| `taofen8-fanli.html` | 返利说明页（独立，不参与大屏） |
| `tools/web-deploy.sh` | 网页线：一键上线（不打包） |
| `tools/release-app.sh` | 打包线：编译 APK + 发版 + 建 GitHub 发行版 |
| `docs/APP-RELEASES.md` | APK 发行台账（历史版本、大小、md5、commit） |
| `docs/运维汇总台账.md` | 脱敏汇总台账：电表、云盘、ECS 快照等 |
| `.env.example` | 环境变量占位模板，复制为 `.env` 后填真值，`.env` 不入库 |

## 两条链路：什么时候用哪条

| 链路 | 命令 | 产出 | 什么时候走 |
| --- | --- | --- | --- |
| **网页线** | `./tools/web-deploy.sh "改了什么"` | 只更新 Cloudflare Pages | 默认都走这条：改文案、改样式、调星环、调音乐、清数据 |
| **打包线** | `./tools/release-app.sh 1.9.9 "更新说明"` | APK + Pages + GitHub 发行版 | 动了**壳层**（Manifest、权限、图标、启动页、离线资源清单、WebView 配置），或到了对齐节点 |

打包节奏口径（按事件，不按功能点数量攒）：

- 动壳层 → 必打
- 距上次打包 ≥ 14 天，或期间网页改动 ≥ 6 次 → 提示对齐，打一版
- 功能里程碑 → 版本号 `+0.0.1`
- 纯样式 / 纯文案 / 纯数据 → 不打

## 网页线怎么跑

```bash
./tools/web-deploy.sh "本次改了什么"
```

脚本四步，任一步失败即非零退出，不会“看起来成功”：

1. 备份首页到 `.build/backups/`（部署目录之外，避免备份文件被一起上传到公网）
2. 语法自检：`node --check sw.js` + 首页内每一段 `<script>` 逐块检查
3. `wrangler pages deploy` 发到 Pages 项目 `lcdc`
4. 核对线上：`/sw.js` 状态码、首页下载体积、SW 注册位置，并打印“距上次打包 N 天 / M 次网页改动”

> Cloudflare 的账号接口偶发 503（`upstream connect error`），脚本会明确报「部署失败（CF API 出错）」，重跑即可，本地文件不会丢。

## 打包线怎么跑

```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64   # AGP 8.2.1 要求 JDK17，系统自带 java 11 跑不了
./tools/release-app.sh 1.9.9 "更新说明"
```

脚本四步：

1. 把 `pages-deploy` 的 Web 资源同步进安卓工程 `web/` 与 `assets/public/`
2. `./gradlew assembleRelease` 编译，并用 `apksigner` 校验证书 SHA-256，指纹不符直接中止
3. 写 `version.json`（版本号、包体大小、md5、更新说明、APK 地址）并发 Pages
4. 在 GitHub 建同名发行版（tag `v<版本号>`）并上传 APK

注意：

- `versionCode` 由脚本从 `android/app/build.gradle` 自动 +1，**版本号只增不减**
- 签名必须用同一 keystore（别名 `licheng-lcdc`），换签名会导致老用户无法覆盖安装
- JDK17 在这台机器上会被环境重置丢掉，打包前先确认 `ls $JAVA_HOME/bin/java` 存在，缺就重装 `openjdk-17-jdk-headless`
- 发版完成后脚本会把 `.build/.pack-stamp` 归零，重新开始计“距上次打包的天数/次数”

## 离线缓存（sw.js）

目标：联网时永远拿最新，断网时回最近一次成功打开的那一页。

- 同源导航：network-first，**按页面地址各自缓存**；有同页缓存时 4.5s 超时回缓存，首次访问没有兜底则等到 25s（避免慢网被误判离线）
- 只有访问的确实是 `/` 时，才更新首页兜底快照；子页（如 `/dashboard`）的响应**绝不覆盖** `/` 的缓存
- `/api/*`、`/apk/*`、`sw.js`、`version.json` 一律放行不缓存
- 静态资源 cache-first + 后台更新；`install` 时 `skipWaiting`，`activate` 清旧版本缓存并 `clients.claim`
- 缓存版本号在 `sw.js` 里（当前 `v2`），改策略时一并 +1

## 首页星环

- 六条通道：视频 / 图文 / 官网 / 私域 / 广告（展示为「立橙音乐」）/ 知识，目前**只保留通道名**，通道下的工作流与任务已清空，等接入真实工作流
- 粉色那条通道显示「立橙音乐 · N/M源」，N/M 来自 `/api/music/sources` 探活（8 路并行、3s 超时、边缘缓存 300s）
- 音乐播放时朝粉色通道打一束光，播放期间每 5 秒一束 + 弧线低频呼吸；暂停即停
- 标题「立橙数据中心」点一下进 `/dashboard`；语音/文字说「打开数据中心 / 进入大屏 / 打开看板」同样可进
- 主题：只保留神经星环这一套，主题选择器与其余九套皮肤已删除

## 音乐接口（Pages Function）

前缀 `/api/music/`，八个音源按命中率排序并发竞速（最多 3 路同时跑，先成功者胜）：

| 路由 | 作用 |
| --- | --- |
| `health` | 列出音源与状态 |
| `search` | 关键词搜歌（写死 `source=kg`，只走酷狗） |
| `url` / `resolve` | 取播放直链（240s 缓存） |
| `lyric` | 歌词 |
| `play` | 一条龙：搜索 + 取链 |
| `selftest` | 自检（固定返回 200，`index` 在 body 里） |
| `stream` | 同域代理播放（绕跨域） |
| `img` | 封面代理（仅白名单 `kugou.com`，缓存 1 天） |
| `sources` | 8 路探活，返回 `{total,alive,up,down,detail}` |

## 数据口径

- 电表：国网两户台账（余额、日电量、6 日均、年度电量电费），同日同户号只更新不重复追加
- 云盘：百度 / 联通 / 阿里 / 123 云盘清单扫描快照（容量、文件数）
- 手机卡：联通套餐流量、短信与在网状态快照，号码中间四位打码，完整号以本地台账为准
- 商标：国家知识产权局开放数据 + 代理 App 截图核对，非实时法律状态，最终以中国商标网为准

## 安全说明

- 上游 API Key 与账号密码只通过环境变量注入，不写进代码、不下发浏览器、不入库
- 仓库为私有；页面中的手机号、运单号，以及台账里的户号、公网 IP、实例 ID 均已打码
- 全量文件清单、个人文件名、闲鱼经营数据、运行日志，以及网盘令牌 / Cookie 配置文件**不进入本仓库**
- Cloudflare 令牌、keystore、JDK 与 Android SDK 只存在于本机 `.build` 与用户目录，不进仓库

## 当前版本

- APP：`v1.9.8` / `versionCode 18`，5,873,817B，md5 `f6c6ebe322b0434a5469e3dc726ad4fd`
- 发行版：<https://github.com/zhaoliguo5601/licheng-data-center/releases>
- 版本历史见 `docs/APP-RELEASES.md`
