# Devin Worker 协同工作流

本文供没有本线程上下文的主线 agent 使用。Devin 是通过工作台 relay 调用的本机 CLI worker。它负责限定范围内的实现和复现，主线 agent 负责目标分解、设备操作、证据核验、集成、commit、push 和 merge 决策。

## 固定入口

- 唯一主线源码仓为 `D:\Desktop\Git\UniXNU_elden`，默认分支 `main`。
- Y700 工作台为 `D:\Desktop\Git\Patch\Y700-Elden`。
- Devin relay 为 `D:\Desktop\Git\Patch\Y700-Elden\_relay`，派发入口是 `_relay\dispatch.py`。
- worker 名称为 `Devin-worker-agent-Y700`。通过 Devin PowerShell CLI console 使用当前 worker PID，先从进程发现工具取得 PID，不能从旧 relay 文档猜 PID。
- Windows/WSL 用于源码核对、适用的 host tests 和输入准备。需要 Xcode、macOS SDK、Apple linker、签名工具或已配置 Mac toolchain 的完整构建，在 `ciscomac` 上指定的 CiscoMac checkout 执行。
- `research/` 只放独立 Git 克隆。证据写入 `lab/records/`，外部原始构建输入按主线维护规范存放。一次性 relay 交付写在 `_relay/<round>/`。

## 每轮派发

1. 查看主线 Git 状态、目标分支和相关 `AGENTS.md`，同时检查 workbench 的 `maintenance/IN_PROGRESS.json`。列明当前源提交、目标集成分支、CiscoMac 使用的 checkout 和已有用户改动。不可重置、stash 或覆盖用户改动。
2. 一次只派发一个需要写入同一工作树的任务。任务目录用描述性唯一名称，例如 `wifi-tx-trace-002`。创建 `_relay/<round>/task.md`，说明准确的工作树、基线 SHA、可编辑路径、预期差异、依赖、复现命令、成功标准、禁止操作和硬件/host 证据边界。
3. task 文件要求 Devin 先检查工作树状态，保留预存改动，只修改授权文件；不 commit、不 push、不 merge、不访问设备，除非主线目标和设备授权明确要求真机步骤。若目录已有改动，应标明归属，不可清除。
4. 确认 relay 中没有该轮的 `dispatch.json` 后，通过 `dispatch.py` 派发。PowerShell 示例：

   ```powershell
   py -3.12 D:\Desktop\Git\Patch\Y700-Elden\_relay\dispatch.py --pid <当前worker-pid> <round>
   ```

5. 派发后等待三分钟，再检查该轮目录和 worker console。未收到最终 handover 就继续等待三分钟，除非用户新指令或真实阻塞改变了下一步。不要同时向同一 worker console 注入第二项写任务。
6. Devin 完成时必须提供 `_relay/<round>/handover-to-codex.md`，末行精确为 `(handover to codex now)`。交接应记录基线、修改文件、逐文件源 SHA、命令和退出码、测试/编译日志位置、CiscoMac 路径、未解决差异和硬件缺口。
7. 主线 agent 独立阅读 task、handover 和完整 diff。对源哈希、生成物、构建回执和测试结果复核，运行 `git diff --check` 与必要的针对性测试。不得把 Devin 的总结或 JSON 的 `passed:true` 单独当作验证。
8. 只 stage 审核通过的目标文件，保留同一工作区其他已有 staged/unstaged 改动。commit message 描述实际改动。主线 agent 执行 commit/push 到指定源码分支。跨分支合并前按目标分支现状重建并重新验收，不能复制旧整包或静默合并。

## 任务边界

- relay 文件不是源码权威位置。所有源码修补只写在 task 指定的正确仓库和分支。主线默认集成目标为 `D:\Desktop\Git\UniXNU_elden` 的 `main`，离线外设、GPU 和工作台各有独立边界，不能相互误写。
- GPU 的 Windows checkout 为 `C:\Users\Cisco He\.codex\worktrees\elden-gpu-offline\UniXNU_elden`，分支 `codex/elden-gpu-offline`。CiscoMac 上 `/Users/ciscohe/Desktop/UniXNU_elden-gpu-offline` 是 GPU 源码 worktree，`/Users/ciscohe/Desktop/UniXNU_elden-gpu-baseline` 是固定 `a13e5087` 的 clean baseline worktree。运行时先检查最新状态和活动作业，不清理二者。GPU 构建只在 CiscoMac 执行。详见 GPU 分支 `docs/GPU-OPTIMIZATION-HANDOFF.md`。
- Wi-Fi/PCIe/WCN/QRTR 由主线 owner 管理。外设 owner 合入前先审查 shared SMMU、SPMI、RPMh、时钟、触控和 UFS 的当前接口。
- 旧 reference/research 仓按主线同步脚本安全更新，不让 worker 任意切换 pin 或改子模块。
- 真机步骤由主线 agent 明确控制。安全边界、floor、回程、日志准备和 component acceptance 以主线规则与硬件 runbook 为准。host/model 测试不得写成真机通过。
- 清理构建产物只按可恢复维护流程做。CiscoMac 用原生 Trash，Windows/WSL 用 Windows Recycle Bin；保留 build receipt、当前基线和后续复现所需输入，绝不永久删除或清空 Trash。

## handover 模板

```text
Round / task:
Target repository, branch and checkout:
Base commit:
Changed paths and source SHA-256:
Commands, exit codes and log paths:
Tests and exact outcomes:
CiscoMac checkout and toolchain, when applicable:
Existing workspace changes preserved:
Remaining risks or hardware evidence gaps:
(handover to codex now)
```

后续 agent 接手时，从当前 `AGENTS.md`、本文件、`docs/INDEX.md` 和当前组件状态文档重新确认状态。不要假设旧的 Codex 会话、worker PID、relay 内容或进程仍存在。
