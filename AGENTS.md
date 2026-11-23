# UniXNU Elden 工作规则

本仓 `D:\Desktop\Git\UniXNU_elden` main 为唯一有效源码；配套工作台为Patch/Y700-Elden。
主线通过 Devin CLI worker 协作的固定规则见[DEVIN-WORKER-WORKFLOW](docs/DEVIN-WORKER-WORKFLOW.md)。不派 Codex subagent 不影响按用户指定流程派发 Devin-worker-agent-Y700。
简版交接含 CiscoMac 和工作区入口。[basic-agents.md](basic-agents.md)
最新实况见[CURRENT-STATUS](docs/CURRENT-STATUS.md)、[PLAN](docs/PLAN.md)、[WIFI-STATUS](docs/WIFI-STATUS.md)。
全部旧AGENTS流水记录已原样归档到docs/archive/20261121/AGENTS-source-20261121.md，历史SHA保持。

## 当前事实

- Wi-Fi portable扫描实机通过：32BSS（cap32）、113管理帧、HTT6环、CE24/24/drop0。
- 最新 Wi-Fi 实机 `3f8f74e1` 首轮被动扫描启动，第二轮未启动，UMAC `-110`。八字节 HTT 基线通过 PMK/VDEV/auth/assoc，TCL 消费 1 个 EAPOL message 2，WBM/keys/port 为 0。成功 donor 在 legacy WPA2 使用 TID 0，收到 message 3/4 并通过 DHCP。
- 最新候选已返回真实 fastboot，整像读回核对通过，stock Android、root、green 及原充电／无线／扫描设置已恢复。
- 断链恢复充电 profile 已在空输出目录完成28阶段clean build并通过静态签名审查，未刷机。双口净充、物理旁路和保护阈值周期仍待实机验收。
- Mac本周清理／文档整合已完成（137旧产物+18临时内容进原生Trash，未清空）。
  Wi-Fi 从八字节 HTT 基线继续，优先对照本机 OEM 与成功 donor 的 TX/WBM 完成路径。离线 RTC owner 仍缺真实持久 NVMEM 与 alarm provider。

## 执行边界

- 用户长期授权无人值守设备迭代；合并必要功能验收，减少重复探针和无谓冒烟。
- 唯一Y700 HA2A1PT2/TB322FC；勿操作Sony BH905ND69G。长边电脑、短边PD按实际日志记录。
- 仅boot_a；floor1738713600/footer0/parent3永不抬升。写前fresh电压>=3500mV/soc-ok、
  候选/GPT/AVB审查，全像读回SHA，会话绑定日志与真实回程，恢复stock/root/green/原设置。
  使用tools/device/flash_verified_boot.py。stock SHA8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890。
- 不unlock/relock/OTA/RPMB/fuse/身份写；不猜寄存器/credit/超时延长，不强写FET/OTG或绕温控。
- 基础驱动优先Sheng已实机规范；SM8750 donor须审核实机成功。板级优先ArmadaOS TB322FC/
  SM8750四代固定源，TB321FU/SM8650三代只作比较。本机双口/旁路/保护以OEM/HAL/实证为准。
- 保持GPU codex/elden-gpu-offline与offline-peripheral-fixes工作树独立，勿改/切分支/清理。
  GPU最后；马达未经校准gain/boost/连续波形及喇叭保持关闭，声音先讨论衰减保护。
- 不派 Codex 子代理，不跑QEMU。Devin CLI worker 按[协作流程](docs/DEVIN-WORKER-WORKFLOW.md)受限派发，并由主线 agent 审查及提交。保留QRTR草稿、AnyRouter暂存及其他用户改动，显式路径提交。
- 临时一次性工具放Windows TEMP/Mac /private/tmp；research只独立Git克隆，笔记放lab。
  旧artifact Windows/WSL进Windows回收站，Mac原生Trash；不永久删除/清空Trash。
- 配套工作台maintenance/IN_PROGRESS.json存在时先完成该事务；引用同步应自动让开。
- 所有有效修补/工具/配置进入本仓commit＋push后刷。不得发布FW/OS执行件/签名密钥/
  私有凭据/设备备份/二进制派生payload头；外部来源/hash记录，按源码再生。
- 基础clean build与当前Wi-Fi增量复现分别报告，不把编译/host模型算实机或宣称未跑的从零整链。
