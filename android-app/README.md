# 立橙数据中心 · 安卓 WebView 壳 APP

用 Capacitor 把立橙数据中心看板打包成安卓 APP。**界面、动效、翻卡、神经星环全部复用现有网页**，
APP 只做一个带原生权限的 WebView 外壳；对话/模型/视频等算力在后端（现阶段阿里云 FC，后续可切本地 AI 主机）。

APP 启动后直接加载线上站点 `https://lcdc.pages.dev`（远程模式），同时具备 **APP 本体在线升级（OTA）** 能力。

## 一、两层更新模型（关键）

| 改动类型 | 举例 | 怎么更新 | 是否要重打 APK |
|---|---|---|---|
| **网页层** | 页面排版、文案、动效、看板数据、功能开关、接口地址、轮播速度 | 改线上 `config.json` / `data.json` / HTML，APP 下次打开即拉到最新 | **否**，免发版 |
| **原生壳层** | 换 APP 头像图标、加蓝牙/新系统权限、加原生插件、改底层壳 | 发新版 APK，APP 内检测到新版后下载覆盖安装（OTA） | **是**，需发新 APK |

### 远端文件（与站点同源，放仓库根目录，CF Pages 发布）

- `config.json`：网页业务配置
  - `apiBase`：后端接口基址，留空则回退页面内置默认地址；
  - `features`：功能开关（如 `aiPanel`、`voiceInput`）；
  - `carouselSpeed`：轮播速度等页面参数。
  - 页面头部内联脚本会在业务脚本执行前同步读取它，写入 `window.LCDC_API_BASE` / `window.__LCDC_FEATURES__`。
- `version.json`：OTA 升级清单
  - `versionCode`：整数版本号，**发新版必须递增**；
  - `versionName`：展示版本名（如 1.1）；
  - `changelog`：更新说明；
  - `apkUrl`：新 APK 下载直链；
  - `force`：是否强制更新（true 时不可跳过弹窗）。

## 二、目录结构

```
android-app/
├── web/                        # 看板静态资源（本地兜底快照，远程模式下不主用）
│   ├── index.html              # 星环开场页 → dashboard.html
│   ├── dashboard.html          # 自适应看板首页（fetch ./data.json）
│   ├── data.json               # 看板数据快照
│   ├── config.json             # 远端业务配置模板（部署到线上同源目录）
│   └── version.json            # OTA 升级清单模板（部署到线上同源目录）
├── android/                    # Capacitor 生成的原生安卓工程
│   └── app/src/main/java/com/licheng/datacenter/
│       ├── MainActivity.java   # 启动时触发升级检查
│       └── UpdateManager.java   # OTA：检查版本 → 下载 APK → 调系统安装器
├── app-icon-source.png         # 图标源图（立橙头像 512×512）
├── generate_icons.py           # 从源图生成各分辨率图标与启动屏
├── package.json
├── capacitor.config.json       # server.url 指向线上站点
└── secure/                     # 正式签名密钥与台账（已 gitignore，勿入库/外发）
```

## 三、OTA 在线升级机制

1. 每次启动，`MainActivity` 调 `UpdateManager.checkForUpdate()`；
2. 后台线程拉取 `https://lcdc.pages.dev/version.json`，与本机 `versionCode` 比对；
3. 远端 `versionCode` 更高 → 弹窗展示版本号与更新说明（可「稍后再说」，强制更新除外）；
4. 确认后下载 APK 到应用缓存目录，经 FileProvider 调系统安装器覆盖安装；
5. 网络不可达、清单解析失败均静默忽略，不阻断正常使用。

### 发一个新版本 APK 的步骤

1. 改完原生代码/图标/权限后，在 `android/app/build.gradle` 把 `versionCode` 加 1，`versionName` 同步更新；
2. 编译出 APK，把 APK 放到可直链下载的位置（CF Pages 的 `/apk/` 目录或 GitHub Releases）；
3. 上线 `version.json`：`versionCode`/`versionName` 与新包一致，`apkUrl` 指向新包直链，填 `changelog`；
4. 已装旧版的手机下次启动即弹出更新提示。

### OTA 约束（务必遵守）

- **覆盖安装新旧包必须同一签名**。已生成自有 release keystore（见下「签名密钥」），正式包用它签名；
  后续所有版本都必须沿用同一套 keystore，否则签名冲突只能卸载重装、无法覆盖升级。
- 在线安装 APK 需要 `REQUEST_INSTALL_PACKAGES` 权限（已配），且首次仍需在系统「安装未知应用」里授权；
  普通应用无法完全静默安装，最后一步系统安装器仍需用户点确认。
- `versionCode` 每次发版必须递增，否则检测不到更新。
- 下载的 APK 走 FileProvider 共享（`res/xml/file_paths.xml` 已配 cache-path）。

### 签名密钥（secure/，已加入 .gitignore，勿上传 Git、勿外发）

| 文件 | 说明 |
|---|---|
| `secure/licheng-data-center.keystore` | 正式签名库，RSA 2048，有效期至 2054 年 |
| `secure/keystore-credentials.txt` | 台账：别名 `licheng-lcdc`、store/key 密码、备份提醒 |
| `secure/signing.properties` | gradle 读的密码与别名（不入版本库） |

- 证书 DN：`CN=licheng, O=licheng, OU=datacenter, L=Jinan, ST=Shandong, C=CN`；
  SHA-256 指纹 `5f767073787f9330f14e000abb1b760a410b9ae86f573c49ebd6ad24ddf0de45`。
- **密钥与密码一旦丢失，后续新版 APP 无法覆盖安装，只能卸载重装**；请离线备份 keystore 与台账到安全位置。
- release 签名已在 `android/app/build.gradle` 的 `signingConfigs.release` 配置，密码从 `secure/signing.properties` 读取，不明文写进 gradle。

## 四、编译环境与命令（本机已就绪）

- JDK 17：`/usr/lib/jvm/java-17-openjdk-amd64`；
- Android SDK：`~/android-sdk`（platform-34、build-tools 34.0.0、platform-tools）；
- 编译前必须 `unset` 空代理变量（空值会导致 `MalformedURLException`）。

```bash
cd android-app
npm install
npx cap copy android
cd android
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 ANDROID_HOME=~/android-sdk ./gradlew assembleDebug
# 调试产物：android/app/build/outputs/apk/debug/app-debug.apk（Debug 签名，仅自测）

# 正式发版用 release（自有 keystore 签名，可 OTA 覆盖安装）：
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 ANDROID_HOME=~/android-sdk ./gradlew assembleRelease
# 正式产物：android/app/build/outputs/apk/release/app-release.apk
```

## 五、原生权限（AndroidManifest）

| 权限 | 用途 |
|---|---|
| `INTERNET` | 联网访问线上看板与后端接口 |
| `RECORD_AUDIO` / `MODIFY_AUDIO_SETTINGS` | 网页麦克风语音输入（首次使用弹授权） |
| `READ/WRITE_EXTERNAL_STORAGE`（≤Android 12） | 保存看板数据、生成的文件 |
| `REQUEST_INSTALL_PACKAGES` | OTA 在线安装更新包 |

## 五之二、双指捏合缩放

- `capacitor.config.json` 的 `android.zoomEnabled: true` 开启 WebView 内置捏合缩放（系统缩放按钮已隐藏，仅保留双指手势）；
- 首页与看板页视口均放开 `maximum-scale=5`、`user-scalable=yes`：两指展开放大、捏合缩小；
- 首页 3D 星环画布上另有一套相机视角捏合缩放（`cam.zoom`），与整页缩放并存。

## 六、应用图标

已用 `app-icon-source.png`（立橙头像）通过 `generate_icons.py` 生成全部分辨率图标和启动屏 splash
（橙底 `#EB6F27` + 居中圆形头像）。换源图后重新生成：`python3 generate_icons.py`。

> 注意：换 APP 图标属于原生壳层改动，需要重打 APK 走 OTA 上线；网页里的头像/素材改动走远端更新即可。

## 七、安全与边界

- 中转服务必须加登录鉴权，不要把模型/Ollama 端口直接裸暴露到公网；
- WebView 壳能拿到麦克风、存储、安装未知应用等常规权限，但拿不到深度系统级权限；复杂后台能力需原生插件；
- 本工程**不含**后端大模型、ASR/TTS、ComfyUI 视频生成，这些在本地 AI 主机方案（见 `../local-ai/`）里落地；
- 远程模式代价：离线打不开看板；本地 `web/` 快照仅作兜底资源随包携带。
