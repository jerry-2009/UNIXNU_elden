# Elden 快速交接

开工先读本仓 AGENTS.md、当前状态和本任务对应的状态文档。[AGENTS.md](AGENTS.md) · [当前状态](docs/CURRENT-STATUS.md) · [Wi-Fi](docs/WIFI-STATUS.md) · [充电](docs/CHARGING-STATUS.md) · [路线](docs/PLAN.md)

- 主线源码在 Windows `D:\Desktop\Git\UniXNU_elden` 的 `main`。提交前核对路径、分支和暂存清单，保留现有用户改动。
- Apple ARM64 构建用现有 CiscoMac。SSH 入口见交接记录的 macOS 小节。仓库在 `/Users/ciscohe/Desktop/UniXNU_elden`，已配 Xcode 和 `/Users/ciscohe/toolchains/llvm-20/bin`。按构建报告复用冻结输入和现有解释器。[CiscoMac 交接](docs/archive/20261121/HANDOVER-20261118.md)
- clean firmware build 使用 Microsoft Project Mu `CryptoBin v1.1.3` 外部预编译包。清单和校验见 [`CLEAN-INPUTS.md`](docs/CLEAN-INPUTS.md)，用 `tools/fetch_basecrypto.py` 验证官方发布。它不是本仓源码，也不需要手工从旧构建中抽取。构建器把锁定文件复制进本轮临时 EDK II package path 再调用 BaseTools。
- 工作台在 `D:\Desktop\Git\Patch\Y700-Elden`。`research` 放独立 Git 克隆，证据放 `lab`。临时文件放 Windows TEMP 或 Mac `/private/tmp`，按各平台回收站规则清理。
- 优先复用 Sheng 的实机成功实现。SM8750 供体先核查实机证据。板级参考选 ArmadaOS-Freedom 的 TB322FC／SM8750 四代。双口供电、旁路和保护对照本机原厂 HAL 与实测。
- 实机只用 Y700 TB322FC，按 AGENTS.md 核对序列号、供电、`boot_a`、回滚索引和回程。把必要功能合并进一个测试窗口。
- GPU 和 `offline-peripheral-fixes` 各有工作树。集成时从 `main` 评审具体提交，GPU 排最后。音频、马达的启用按 AGENTS.md 的保护约束。
