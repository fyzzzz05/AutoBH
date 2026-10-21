# AutoBH

上课签到、TD、博雅、阳光打卡的统一 Python CLI 与本机 GUI。优先复用 AutoSign、AutoTD、AutoBoya 的接口、配置、会话、缓存、业务规则及后台循环。

## macOS App 与 DMG

可从 [Releases](https://github.com/fyzzzz05/AutoBH/releases) 下载 `AutoBH-0.1.10-macOS-arm64.dmg`，或使用本地 `dist/AutoBH-0.1.10-macOS-arm64.dmg`：打开后将 `AutoBH.app` 拖入“应用程序”。App 内置 Python、三个原工具及 GUI，不需要另外安装 Python 或 Node.js。当前构建为 Apple Silicon 版，使用本机签名，尚未经过 Apple Developer ID 签名和公证。

App 沿用 `~/.autobh`、`~/.autosign`、`~/.autoboya`、`~/.autoTD` 中的账号和缓存。安装包不包含个人账号。窗口使用独立本机端口，不占用 CLI GUI 的 8765；关闭窗口会结束其管理服务，已启动的后台继续运行。请先把 App 安装到固定位置，再启动后台。

支持 macOS 菜单栏 **AutoBH → 检查更新…**，通过 GitHub Releases 下载并校验更新，确认后安装并重新打开。默认自动检查，可在菜单关闭。发布仓库和 0.1.10 Release 已公开，无需 GitHub 登录即可读取更新源与下载更新包。旧版本需先安装一次带更新器的新版本。[更新签名与发布说明](docs/updates.md)。

在 macOS 上重新打包（推荐独立 Python 3.12 环境）：

```bash
python3.12 -m venv build/macos/venv
build/macos/venv/bin/python -m pip install -e '.[td,macos-build]'
build/macos/venv/bin/python scripts/build_macos.py
```

构建会生成 `.app`、`.dmg` 和 SHA256 文件，检查三个工具可从内置运行时加载，并验证 App 签名。前端需修改时默认重新构建；未修改前端可加 `--skip-gui`。有 Developer ID 证书时可使用 `--sign-identity`，Apple 公证需另行完成。

## GUI

```bash
autobh ui
```

自动打开本机管理页面，默认地址为 `http://127.0.0.1:8765`。左侧选择人员，右侧管理上课、TD、博雅、阳光，顶部查看和启停各项后台。支持搜索、添加人员、编辑姓名和分组、绑定账号、TD 图片导入、查看课表/进度/课程缓存、运行记录和删除人员。

页面直接使用 CLI 的人员档案与原工具配置。打开 GUI 只读取状态，不会自动启动打卡；关闭 GUI 服务不影响已经启动的打卡后台。博雅沿用原工具的请求、会话、选课条件和签到签退流程；AutoBH 后台额外按人员及类别检查达标情况，已达标类别不再自动选择新课，已选课程继续签到和签退。删除人员会先显示影响范围并等待确认。

博雅进度以学校 `queryStatisticByUserId` 统计为准：净有效次数读取 `validCount`，分类进度读取 `completeAssessmentCount / assessmentCount`，不再从分类通过数中扣减缺勤课程。考核指标按学校返回值展示；签到、签退记录与学校考核状态独立显示，缺少签退记录不会被推算成考核失败。官方统计缺失时显示待同步，刷新失败保留原缓存。

博雅详情中的“个人定制”可为每位同学独立设置停止条件：默认逐类达到官方考核指标后停选；也可改为官方净有效次数达到指定目标后停止所有新选课。总次数模式允许继续选择已达标类别的课程，直到总目标达标；已选课程仍继续签到、签退。设置不会改变学校统计、人员启用开关或其他同学的规则，可随时恢复默认。

```bash
autobh ui --port 8877       # 使用其他端口
autobh ui --no-browser     # 只启动本机服务
autobh ui --demo           # 隔离的示例数据，不修改真实账号或执行打卡
```

GUI 只监听本机回环地址，接口校验页面令牌和请求来源。安装包内附带构建后的前端，运行不需要 Node.js。修改 GUI 源码时执行：

```bash
cd gui
npm install
cd ..
python3 scripts/build_gui.py
```

前端源码位于 `gui/`，静态产物位于 `src/autobh/web/`，本机 HTTP 接口位于 `src/autobh/gui.py`。原始选定设计和视觉核对截图位于 `gui/qa/`。

## 阳光打卡

支持学期/本周/今日次数、分页运动记录和运动图片提交。绑定时可复用已有学校密码；阳光后台只做每 30 分钟的数据同步，新增打卡需核对实际运动信息后手动提交。[操作与实现说明](docs/sunshine.md)。

## 安装

需要 Python 3.11 或以上。在本仓库根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[td]'
autobh --help
```

项目名称为 **AutoBH**，命令为 `autobh`，也支持 `python -m autobh`。不需要 TD 时可用 `pip install -e .`。

如需安装到本机默认 Python 而不启用虚拟环境，在仓库根目录使用 `python3 -m pip install --user -e '.[td]'`。若用户脚本目录未在 PATH 中，可直接用 `python3 -m autobh`；安装命令也会提示脚本所在目录。

AutoSign 与 AutoBoya 直接从本仓库打包；本地 AutoTD 目录目前只有 README，因此 TD 通过可选依赖 `autotd-buaa>=0.1.15,<0.2` 复用已发布实现，适配验证版本为 0.1.15。

## 开始使用

```bash
autobh init
autobh doctor

# 已有的原工具账号会自动出现在列表中，无需迁移密码。
autobh user list

# 姓名/分组只是管理信息，功能账号分别绑定。
autobh user add 23370001 --name 张三 --group 同学
autobh account add class 23370001
autobh account add boya 23370001 --campus 北京

# TD 沿用原有图片、机位和次数设置，不需要统一认证密码。
autobh td init
autobh td image add ~/images/photo.jpg
autobh account add td 23370001 --quick 学院路

autobh user list --feature boya
autobh user list --group 同学 --json

# 删除人员档案和全部功能的本地账号绑定。
autobh user remove 23370001

# 四个功能分别运行；没有启用账号的功能会跳过。
autobh service start
autobh service status
autobh service stop
```

添加上课/博雅账号时使用隐藏输入；脚本可以使用 `--password-stdin`。上课仍使用原有权限为 `600` 的配置文件保存密码；博雅优先使用原系统钥匙串，只有显式指定 `--unsafe-store-password` 才允许使用原明文密码文件。AutoBH 人员档案中不保存密码。

`user remove` 复用原工具删除接口，移除本地账号绑定和姓名/分组，保留原日志、缓存及原工具留存的凭据/会话；不操作学校系统中的账号或已选课程。后台下一轮读取配置时生效，本轮已经发出的请求会继续完成。只想暂停某个功能时使用 `feature disable`。

**启用博雅自动化会复用原工具的选课、签到和签退流程**，包括自主签到课程及校区过滤。AutoBH 管理的后台在提交选课前会重新检查该人员的官方分类考核通过数和考核指标；达标的类别跳过新选课，官方统计缺失或刷新失败时暂停新选课，已选课程继续执行签到和签退。可以先运行 `autobh boya courses refresh`、`autobh boya courses auto-preview` 查看原策略。

## 按人员管理功能

```bash
autobh feature disable boya --user 23370001
autobh feature enable boya --user 23370001
autobh feature disable td --user 23370001

autobh service start --feature class
autobh service stop --feature class
autobh service status --json

# 执行单轮真实自动化，要求该人员已绑定并启用对应功能。
# 运行中的后台会阻止并发单轮执行；先停止对应后台即可。
autobh run --once --feature class --user 23370001
autobh run --once --user 23370001

autobh logs --feature class --lines 50
autobh logs --feature boya
autobh logs --feature td
autobh logs --feature class --worker
```

开关在下一轮读取配置时生效；本轮已发出的请求会继续完成。后台关闭终端后继续执行，停止时等待当前网络请求结束；超过短暂等待时间会显示停止请求仍在处理中。

上课与博雅的开关写入各自原配置；TD 的开关由适配器保存在 TD 数据目录中，仅作用于 **AutoBH 启动的 TD 调度器**。暂停 TD 不会删除原用户或其尚未完成的入口/出口进度。`autobh run --once --feature td` 执行原定时调度的一次扫描，遵守时间窗口并保存下一动作；它不会在前台等待完整的一天流程。

## 原工具功能继续使用

```bash
autobh class week --username 23370001
autobh class autostart status

autobh boya login 23370001
autobh boya courses list --only-selectable
autobh boya selected --user 23370001
autobh boya stats --user 23370001
autobh boya select 123 --user 23370001 --yes

autobh td user count 23370001 --refresh
autobh td user update --help
autobh td schedule show

autobh class --help
autobh boya --help
autobh td --help
```

`class`、`boya`、`td` 子命令原样转发参数并保留退出码。手动操作仍遵循原工具行为和确认要求；自动化人员开关不会阻止明确指定的手动操作。

后台统一使用 `service start/stop/status` 管理。检测到原 CLI 已启动后台时显示 `native-running`，应先使用 `autobh class stop`、`autobh boya stop` 或 `autobh td --stop` 停止原后台，再切换到 AutoBH。不要另外从原 CLI 启动相同功能的第二个后台。AutoBH 内部按原数据目录加进程锁，避免多个 AutoBH 实例或单轮任务重复运行。

TD 沿用原工具的校园网要求。机器关机或休眠期间无法运行；第一版尚未提供统一开机自启，原 `class autostart` 只负责原上课服务。

## 数据目录

| 内容 | 默认目录 | 覆盖环境变量 |
| --- | --- | --- |
| AutoBH 姓名和分组 | `~/.autobh` | `AUTOBH_HOME` 或全局参数 `--home` |
| 上课原数据 | `~/.autosign` | `AUTOSIGN_HOME` |
| 博雅原数据 | `~/.autoboya` | `AUTOBOYA_HOME` |
| TD 原数据 | `~/.autoTD` | `AUTOTD_HOME` |

`--home` 只控制人员档案，不会复制或改动原工具数据目录。若需要完全独立的配置，可同时指定四个变量：

```bash
export AUTOBH_HOME="$PWD/.autobh/people"
export AUTOSIGN_HOME="$PWD/.autobh/class"
export AUTOBOYA_HOME="$PWD/.autobh/boya"
export AUTOTD_HOME="$PWD/.autobh/td"
autobh init
```

每个功能的 `run/autobh/` 下保存 AutoBH 后台进程锁、状态和启动日志。业务日志沿用原工具位置。

## 实现与验证

```text
src/autobh/
  cli.py       统一命令与人员视图
  storage.py   人员备注、原子写入和跨进程锁
  backends.py  复用原工具的账号存储与 runner
  service.py   独立后台进程、单实例锁和协作停止
  td.py        原 TD 调度器的人员过滤与进度保留
```

对原源码的必要修改仅包括：AutoSign 识别账号 `enabled`、配置原子写入；AutoBoya 过滤已暂停用户的缓存任务；两个原后台循环接受可选停止事件。原有 CLI 调用方式继续兼容。

```bash
python -m pip install -e '.[td,dev]'
python -m pytest
python -m pytest AutoSign/CLI/tests AutoBoya/tests --import-mode=importlib
```

新增测试覆盖原账号发现、分功能暂停、单人员执行隔离、TD 进度保留、后台重复启动/停止/重启，以及无网络环境下的真实子进程生命周期。测试不会向学校系统提交打卡。

## 数据刷新、TD 重试与博雅退选

详情中的“刷新数据”只查询课表或博雅已选课程及统计；绑定新账号后会立即查询。数据更新时间独立于后台运行状态，查询失败保留原缓存。博雅按账号保存刷新时间。TD 的原生次数查询实际会提交打卡，因此“重新读取缓存”仅刷新本机数据，新的学校次数仍由真实打卡响应更新。TD 进度弹窗每 3 秒同步本机状态，紧凑展示今日轮次、阶段及请求/锻炼/重试动效；非打卡时段提示只能读取缓存并显示下个时段，异常详情按需展开。

TD 对确认未发送成功的连接失败，以及成功打卡后的照片上传失败，按 1、3、10 分钟间隔最多重试 3 次，实际执行仍受原工具窗口限制。完成轮次、入口／出口阶段和成功响应会保留；发送后的响应超时等结果不明情况暂停自动重试，详情显示原因和时间。

博雅课程在允许退选的时间内提供“退选”，提交前重新查询并核实课程及期限。退选课程会按人员持久排除，自动化不会重新选回；响应不明确时也保留排除，并提示刷新核实。`autobh boya drop ID --user 学号 --yes` 使用相同逻辑。`autobh boya run`、`run-once` 和 TD 的 `run`、`run --once` 统一走 AutoBH 的管理调度。直接运行独立的 `autoboya` / `autotd` 原工具仍使用原工具的规则。
