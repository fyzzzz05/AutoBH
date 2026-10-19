# 原工具源码来源

AutoBH 的主仓库记录下列源码的当前工作副本，包含整合所需的本地修改，不使用只记录提交指针的 gitlink。这样主仓库的提交可以恢复完整源码。原工具各自的本地 `.git` 历史不纳入 AutoBH 提交，也不改动。

| 目录 | 上游 | 导入时提交 |
| --- | --- | --- |
| AutoSign | git@github.com:DeNeRATe-cool/AutoSign.git | be58a1a |
| AutoBoya | git@github.com:DeNeRATe-cool/AutoBoya.git | c8fc785 |
| AutoTD | git@github.com:DeNeRATe-cool/AutoTD.git | a4c6e9b |

导入时已有修改：AutoSign 的配置管理与调度器、AutoBoya 的调度器。以上工作副本随 AutoBH 首次提交保存。

阳光接口移植来源和许可证见 `docs/sunshine.md` 及 `src/autobh/third_party/UBAA-LICENSE.txt`。

账号、密码、学校会话、运行缓存、Python/Node 依赖目录、构建与安装包不纳入版本控制。macOS 更新签名私钥仅存于系统钥匙串，`packaging/macos/updates.json` 只含公开更新配置与公钥。
