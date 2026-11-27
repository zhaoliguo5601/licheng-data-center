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
