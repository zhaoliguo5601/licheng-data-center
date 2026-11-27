# APP 发行版台账

每次「立橙数据中心」APP 升级，GitHub 仓库都会留一个 **Releases** 条目，附 APK 原件和更新说明。作用有三个：

- **回退**：某一版出问题，直接回 Releases 下旧 APK 装上，不用重新打包
- **抽取**：要拿某一版的界面/页面做参考，直接下那个版本，不用翻提交历史
- **对账**：版本号、大小、MD5、签名一目了然，线上 `/version.json` 与这里始终一致

## 发新版的固定动作

```bash
cd .build/git-work/repo
./tools/release-app.sh 1.9 "首页植入立橙音乐，8 路音源自动回退，歌词默认隐藏"
```

脚本按顺序做四件事，任何一步失败都会停：

1. 把线上 Web 资源（`index.html` / `dashboard.html` / `config.json` / `data.json` / `music.html`）同步进 `android-app/web` 和 `assets/public`
2. `versionCode` 自增一位、`versionName` 换成新号，`./gradlew assembleRelease` 编译并校验签名（必须是 `5f767073…de45`，否则直接中断）
3. 把 APK 拷进 `pages-deploy/apk/`，写 `version.json`（版本号/大小/MD5/changelog/下载地址），发 CF Pages，再回填本版快照地址做备用线路
4. 调 GitHub API 建 `vX.Y` 发行版，把 APK 挂成附件，正文写更新说明与校验信息

依赖：`openjdk-17`（AGP 8.2.1 要求）、`/home/user/android-sdk`、`~/.git-credentials` 里的 GitHub 令牌、CF 令牌在 `archive/worker-legacy-cf-20261123/.cf-token`。

## 版本表

| 发行版 | versionCode | 大小 | MD5 | 要点 |
|---|---|---|---|---|
| [v1.9.7](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9.7) | 17 | 5.60MB | `3751c50f…50ad6` | 输入条改豆包式按住说话：波形+辉光、上滑取消、键盘切换 |
| [v1.9.6](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9.6) | 16 | 5.60MB | `b4c7cf74…f47c` | 音乐加封面：列表缩略图 + 正在播放大封面，图片走同域代理 |
| [v1.9.5](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9.5) | 15 | 5.60MB | `6856e080…2174` | 面板回左侧原位并压到 26% 透明，按钮留驻 AI 窗口 |
| [v1.9.4](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9.4) | 14 | 5.60MB | `29355980…b0dd` | 音乐按钮并入「自动分派」胶囊旁，面板跟随对话面板定位 |
| [v1.9.3](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9.3) | 13 | 5.60MB | `760f5bf0…e1cf` | 音乐面板改半透明毛玻璃、标题转粉色；离线包同步 |
| [v1.9.2](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9.2) | 12 | 5.60MB | `5d5f0d49…849a` | AI 对话一句话点歌/暂停/切歌/开关歌词；离线包同步本版 |
| [v1.9.1](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9.1) | 11 | 5.60MB | `a8f16d25…5439` | 断网兜底：主框架加载失败自动切包里离线版，不再白屏 |
| [v1.9](https://github.com/zhaoliguo5601/licheng-data-center/releases/tag/v1.9) | 10 | 5.60MB | `53dbd1be…05fe` | 首页植入立橙音乐、8 路音源自动回退、歌词默认隐藏 |
| v1.8 | 9 | 5.59MB | `636a9e15…22f2` | 回答标注模型、星团撞击动效、视角按钮下移、断网兜底页 |

> v1.8 及更早没有在 Releases 里建档（发行版机制从 v1.9 开始），线上仍可从 `apkUrlBackup` 快照取到旧包。

## 装包与升级

- 主地址 `https://lcdc.pages.dev/apk/licheng-datacenter.apk`，备用是当次部署快照 `https://<部署ID>.lcdc.pages.dev/apk/licheng-datacenter.apk`
- 必须沿用同一 keystore，否则无法覆盖升级；`versionCode` 每次递增，装包末步仍需手动确认
- 首次安装要开「安装未知应用」权限

## 已知环境坑

- 系统默认 java 是 11，跑 gradle 会失败，脚本里已固定 `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`
- gradle 已缓存 8.2.1，编译用 `--offline` 避免拉网
- `android-app/` 与 `.build/` 同级，脚本里的相对路径按这个结构写死

## 两条链路（自 v1.9.7 起）

**网页线（默认，随时走）**

`./tools/web-deploy.sh "改动说明"` —— 备份首页到 `.build/backups/`（不再放部署目录，避免被当公网文件传上去）、语法自检、发 CF Pages、核对 `sw.js` 与首页，末尾打印「自上次打包 N 天 / M 次网页改动」。不碰 APK。

适用：样式、文案、颜色、位置、接口参数、交互逻辑等一切网页侧改动；AB 联网时 WebView 加载的就是这份最新页面。

**打包线（按触发条件走，别按“功能点”数）**

| 触发条件 | 是否打包 |
| --- | --- |
| 动了 `MainActivity.java`、权限、Capacitor 配置、图标、包名、签名、原生插件 | 必须打，网页侧改不了 |
| 距上次打包 ≥14 天，或中间网页改动 ≥6 次 | 建议对齐一次离线快照 |
| 一个完整功能块收尾（如音乐模块、按住说话） | 里程碑留档，版本号 +0.0.1 |
| 纯样式微调 | 不打 |

`./tools/release-app.sh <版本号> "说明"` 走完四步（同步 Web → 编译签名 → 发 Pages + version.json → 建 GitHub 发行版挂 APK），并把计数器归零。

`sw.js` 负责断网兜底（同源导航 network-first、4.5s 超时回缓存；首次无缓存不做超时），所以断网不再依赖包内快照，这也是打包频率能降下来的原因。
