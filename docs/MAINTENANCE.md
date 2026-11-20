# 目录维护和归档规则

源码唯一入口为本仓。配套工作台目录为 `Patch/Y700-Elden`，设备备份与资产不提交。

常用设备工具实现位于 `tools/device/`。旧 `edl_work` 下的七个入口已改为转发，
由 `tools/maintenance/install_workbench_launchers.py --workbench <路径>` 校验并安装。
它只接受已归档原文件或完全相同的现有转发文件，拒绝覆盖未知修改。
刷写器要求显式工作台；监听器要求显式日志目录。19 项离线模型测试与端口归属/就绪断言通过，
维护标记存在时 `--write` 在读取候选或访问设备前被拒绝。

`tools/device/watch_icon_trial.py` 为维护中的 CRC 帧观察器，要求显式 `--workbench`、
`--run`、`--session` 和 `--desktop-reference`，只创建会话绑定的结构化控制请求。
它保存操作后的画面供人工/图像审核，不把图标匹配或输入返回0当作应用功能通过。

| 工作台目录 | 内容 |
| --- | --- |
| `research/` | 经 Git 顶层核验的直接参考克隆；不放笔记、截图、输出 |
| `lab/records/` | 历史实验、只读记录及冻结输入 |
| `lab/reference-reviews/` | 每轮上游更新的证据和结论 |
| `archive/research-notes/` | 旧 handover、探索文档 |
| `archive/session-logs/` | 原 AGENTS 历史；包含私有现场信息，不公开提交 |
| `archive/legacy-workbench-source-20261112/` | 已逐字匹配正式仓的447份旧顶层源码副本 |
| `maintenance/` | 整理事务、路径迁移表、回收凭据、同步报告 |
| `edl_work/` | 冻结产物、历史运行记录和七个兼容入口；不要新建独立源码 |
| `Backup/`, `signing/`, `vendor-pack/` | 备份、恢复和外部输入；不得按废件清理 |

一次性工具放 Windows TEMP。Windows 退役文件只进回收站；WSL 退役文件先移至
Windows 并核对内容，再进回收站；macOS 文件进用户 Trash。不要清空垃圾桶或永久删除。
回收站仍占磁盘空间，不能报告为“已释放”。

历史路径通过 `maintenance/cleanup-20261111/research-moves.json` 查原位置和新位置。
Mac 有自己的对应表。不要盲目全局替换历史 JSON，否则会破坏证据的哈希关系。

新增 `legacy-source-moves.json` 记录447份源码副本的归档路径；现行实现和修补只在正式仓维护。
`retire-superseded-boot-packages.receipts.jsonl` 记录328份过时 boot/FAT 包的回收路径和完整摘要，
约17.5GiB，仍占回收站空间。v89–v92、内核/日志、备份与恢复资产保留。

每六小时的引用同步使用：

```powershell
py -3.12 tools/maintenance/sync_reference_repos.py --workbench D:\Desktop\Git\Patch\Y700-Elden --apply
```

脚本在 `maintenance/IN_PROGRESS.json` 存在时直接跳过；`--inventory-only` 只做目录核验。
只快进干净未分叉的跟踪分支；有本地修改或未跟踪文件的仓只 fetch，固定检出不换版本。
报告写入 `maintenance/reference-sync`，不操作设备。

2026-11-19补充：每仓开始、fetch前后及快进前检查整理标记；标记出现即以
`deferred-maintenance`结束该仓。快进前重新核对分支、HEAD、跟踪分支和工作树，
变化以`changed-during-sync`保留。快进使用已解析的完整commit，随后远端引用变化
不会另选提交。11个实际本地Git场景覆盖正常快进、固定检出、脏树、分叉、切换分支、
跟踪分支变化、fetch后修改和整理标记，以及目标引用再次变化。
[修复前后证据](evidence/reference-sync-guards-20261119.json)。

这些检查保护了已复现的变更窗口；最后一次核对与Git命令仍非跨进程原子事务。
整理线程应先写标记并等待既有同步任务结束，不与同一参考仓同时checkout或修改。
测试仓保留在Windows Temp，未重刷候选、更新子模块或改动冻结输入。

## macOS 编译端的源码与产物

macOS 主源码仓是 `~/Desktop/UniXNU_elden`。`lab/clean-build-20261114/isolated/UniXNU_elden`
是另一个独立 Git 克隆；它有自己的 HEAD，不能把向其中复制几个脚本视为已经同步主仓。
2026-11-15整理时，主仓还停在33b55083，隔离克隆停在cc7714d；两者均已在保存本地
差异后快进到已发布v146源码8ceeb5f。449份旧文件来自三个Mac仓库的差异/同名未跟踪
输入，保存于原生Trash快照中并按SHA核对；包含配套Lilac仓库，不把它们混进新源码提交。
用户随后确认自行检查并清空了第一批Trash，故这批旧文件快照现已不可从Trash恢复。
现行源码仍在已发布的Git提交中；回收时的验证记录与当前恢复可用性分开记载。

Windows每六小时的任务只更新工作台 `research/` 引用仓，不会同步Mac的项目主仓。
每轮编译先核对Mac HEAD与拟使用的完整源码提交；从Git固定对象或带完整源指纹的
显式输入构建。同步只做 `git fetch` 和 `git merge --ff-only <已核完整提交>`。
遇到本地差异先保留内容及哈希、记录来源，不用强制reset把它们丢掉。历史构建和
已有候选的源码/产物指纹不随主仓更新而改写；旧HEAD也不能单独证明此前某个内核
没有使用已传送的修补，要看那一轮的实际编译输入记录。

本轮Mac回收记录在工作台 `maintenance/cleanup-20261115-macos`，包括用户提供的两份
结构分析报告、原路径、原生Trash返回路径、镜像SHA及目录文件身份清单。
过时整包移走前另存其顶层结果和日志；原包仍可从Trash恢复。
当前v146/PD/GUI构建依赖、原始OS/触控/WCN/Crypto、签名模板、恢复输入和实验原始
记录保留。macOS Trash仍占磁盘；回收不等于已增加可用空间。

## 2026-11-21 本周整理

当前文档入口为[INDEX](INDEX.md)。CURRENT-STATUS/PLAN/WIFI-STATUS和AGENTS已
精简为当前事实及执行规则；原逐轮内容与11月18交接原样保存于
[docs/archive/20261121](archive/20261121/README.md)，不改历史指纹。

Mac原生Trash回收137项旧产物（21.25GiB allocated）及18项小型一次性文件／源码快照。
所有目录和文件SHA/inode核验通过；原结果/日志另留，22658项当前传递依赖保留。
垃圾桶未清空，回收不等于释放空间；剩余约62.5GiB。
[摘要证据](evidence/maintenance-macos-20261121.json)；完整恢复清单在工作台
maintenance/cleanup-20261121/mac-evidence/{verified-receipts,finish-receipts}.json。
当前候选、回退、原OS/固件/Crypto/签名、GUI/电源/Data及其他工作树保留。
