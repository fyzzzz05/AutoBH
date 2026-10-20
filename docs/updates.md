# macOS 应用内更新

AutoBH 使用 Sparkle 2，现有实现通过无需登录的 GitHub Releases 地址下载更新。当前发布仓库 `fyzzzz05/AutoBH` 按用户要求设为私有，代码与 Release 文件仅对获授权的 GitHub 用户可见。**目前 App 未接入 GitHub 授权，因此私有仓库中的 Release 尚不能通过应用内更新直接下载。** 不得为打通更新而擅自公开仓库或把 GitHub token 打包进 App；后续需单独实现私有更新授权。

Apple Silicon 更新源配置仍为：

`https://github.com/fyzzzz05/AutoBH/releases/latest/download/appcast-arm64.xml`

首次安装支持更新的版本后，使用 macOS 菜单栏 **AutoBH → 检查更新…**。默认自动检查，有更新时由用户确认下载、安装并重新打开。可在同一菜单关闭自动检查。首次安装仍使用 DMG；旧版 0.1.0–0.1.2 没有更新器，需要先安装一次新版本。

仓库及首个 Release 尚未发布时，线上检查会失败；这是更新源尚不存在。公开的正式 Release 必须同时包含已签名 ZIP 和对应 appcast。草稿、预发布或私有仓库不适合当前无需登录的更新通道。

## 数据和后台

更新只替换 `.app`，账号与缓存继续保存在原有用户目录。安装前会等待由该 App 启动的 AutoBH 后台结束当前操作并保存状态；重启后恢复原来运行且仍有启用账号的功能。外部 Python CLI 启动的后台不受影响。后台未能安全退出时暂缓更新；下次打开会继续恢复未完成的交接。

普通退出 App 仍保留后台。请勿在更新交接期间从另一窗口重新启动后台。如果旧 App 直接启动了原工具后台，需先通过管理后台停止后再更新。

## 签名密钥

`packaging/macos/updates.json` 仅包含仓库、公钥和钥匙串账号，可提交到代码库。当前私钥由 Sparkle 官方 `generate_keys` 工具保存在本机登录钥匙串的 `app.autobh.desktop` 账号中，不写入源码、App 或 Release。

后续版本必须沿用同一私钥；发布前应按 Sparkle 官方流程备份到安全位置，勿提交或上传私钥。macOS 可能要求允许官方签名工具读取钥匙串。换电脑时先恢复同一密钥，避免生成新密钥导致已安装用户无法验证更新。更换仓库也需要先通过旧地址发布迁移版本。

首次为其他仓库配置（现有配置无需重复执行）：

```bash
build/macos/venv/bin/python scripts/configure_updates.py --repository owner/AutoBH
```

## 发布新版本

1. 同步修改 `pyproject.toml` 和 `src/autobh/__init__.py` 的版本，使用递增的 `major.minor.patch`；准备 Markdown 更新说明。
2. 构建并检查 App，再生成签名更新文件：

```bash
build/macos/venv/bin/python -m pip install -e '.[td,macos-build]'
build/macos/venv/bin/python scripts/build_macos.py
build/macos/venv/bin/python scripts/prepare_release.py --notes docs/release-notes-0.1.3.md
```

生成目录为 `dist/releases/v0.1.3/arm64/`，包含 ZIP、`appcast-arm64.xml`、说明和校验清单。脚本校验 App 公钥、更新地址、版本、代码签名，以及 ZIP 和更新源的 EdDSA 签名。签名后的文件不能再修改；修改后必须重新生成。

3. 将项目源码推送到公开 GitHub 仓库，并创建对应源码标签（如 `v0.1.3`）。确认发布内容后运行：

```bash
# 默认创建草稿，供最后检查；不会替换现有 Release。
build/macos/venv/bin/python scripts/publish_release.py dist/releases/v0.1.3/arm64

# 也可在 GitHub 检查草稿后手动发布，并设为 latest 正式版。
# 首次创建时就要公开发布，可使用：
# build/macos/venv/bin/python scripts/publish_release.py dist/releases/v0.1.3/arm64 --publish
```

可另外把构建生成的 DMG 上传到同一 Release 供首次安装；在线更新使用 ZIP。当前脚本一次发布一个架构，构建平台为 Apple Silicon；添加 Intel 通道时需要相应 Mac 构建并将两个架构的 feed 与 ZIP 放入同一个 latest Release。

本机签名用于当前构建，尚未完成 Developer ID 签名和 Apple 公证。面向其他用户公开分发前，需完成这些步骤并对最终 App 重新生成更新文件；Sparkle 的 EdDSA 签名用于更新真实性校验，不能代替 Apple 公证。

## 隔离验证

`scripts/check_macos.py dist/AutoBH.app` 验证包内运行时、签名、更新配置、独立后台生命周期和不包含账号文件。`scripts/check_macos_update.py` 构建独立标识的旧版/新版测试 App，在 loopback 提供临时密钥签名的更新源；测试配置使用无密码的虚拟账号，原工具会在网络登录前跳过。用原生 UI 完成检查、安装、重新打开，并比较测试目录的版本与后台 PID。`--tamper` 会在签名后修改 ZIP，用于验证拒绝安装。关闭测试 App 后对测试服务发出 Ctrl-C，清理其后台；此流程不读取真实账号。

Sparkle 官方文档：<https://sparkle-project.org/documentation/>。

## 本机安装与产物保留

本机测试安装先生成签名 Release，再退出 GUI、运行 `build/macos/venv/bin/python scripts/install_macos.py`，随后重新打开 `/Applications/AutoBH.app`，检查原有后台恢复。安装器复用后台交接逻辑，只在安装事务期间暂存旧 App，以便安装失败时恢复；安装成功即清除，不保留旧 `.app` 或压缩回滚包。源码回退依赖实际存在的 Git 提交历史，使用前须先核实。

安装并验证运行后，运行 `python3 scripts/cleanup_macos.py` 查看清理清单，或加 `--apply` 将已停用的构建/测试副本及旧安装包移入系统废纸篓。清理器保留当前安装和当前版本 DMG/签名 Release，并清理遗留的回滚压缩包；跳过运行中的程序，不清空废纸篓、不触碰账号目录。DMG 暂存 App 随打包完成自动删除。
