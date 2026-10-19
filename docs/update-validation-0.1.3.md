# 0.1.3 更新验证（2026-10-16）

平台：macOS arm64；Sparkle 2.10.0；打包运行时 Python 3.12.14。

- Python 回归：110 项通过，包含后台交接、失败恢复、签名发布配置和缓存不可变检查。
- 原生 UI 完整安装：独立 App 标识、隔离数据目录、临时 Ed25519 密钥与 loopback 更新源，0.1.2 → 0.1.4 下载、验证、安装、重启成功。原后台 PID 69656 退出，新版恢复后台 PID 69732；交接标记删除。
- 空账号恢复：安装成功，不启动没有启用账号的后台。
- 签名拒绝：签名后篡改 ZIP，原生界面显示 “The update is improperly signed and could not be validated”；App 保留 0.1.2，原后台 PID 69796 继续运行。
- 最终 App 与 DMG：代码签名、独立运行时、无个人账号文件、更新源与公钥、GUI 退出和后台独立运行检查全部通过。
- Release：官方工具生成并验证 ZIP 与 appcast 签名，SHA256 清单位于 `dist/releases/v0.1.3/arm64/release.json`。
- 本机安装：`/Applications/AutoBH.app` 为 0.1.3，CLI 为 0.1.3；上课后台 PID 34966 保持，博雅/TD 经正常交接后分别恢复为 PID 70101/70105。旧 App 备份在 `build/macos/installed-backups/`。未发布任何远程 Release。

限制：尚未用真实 GitHub Release 验证线上发现（仓库/首次发布待完成）。完整安装使用本机提供的签名更新源验证；尚未进行 Developer ID 签名与 Apple 公证。
