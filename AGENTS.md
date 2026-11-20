# UniXNU Elden 工作规则

本仓 `D:\Desktop\Git\UniXNU_elden` main 为唯一有效源码；配套工作台为Patch/Y700-Elden。
最新实况见[CURRENT-STATUS](docs/CURRENT-STATUS.md)、[PLAN](docs/PLAN.md)、[WIFI-STATUS](docs/WIFI-STATUS.md)。
全部旧AGENTS流水记录已原样归档到docs/archive/20261121/AGENTS-source-20261121.md，历史SHA保持。

## 当前事实

- Wi-Fi portable扫描实机通过：32BSS（cap32）、113管理帧、HTT6环、CE24/24/drop0。
- 完整station87d1c43c/session2661d591ea5855d4实机VDEV/auth/assoc通过，iOS17桥start0；
  3EAPOL RX／3TX提交，0TX完成，keys0/port0，WPA2/DHCP/流量未通过。
- 协议stop超时；独立BM-off/transaction-idle/MSI4/PERST/真实fastboot与完整stock/root/
  green/原充电无线扫描设置恢复通过。全部设备任务结束。完整Goal active/incomplete。
- 下一步先执行用户要求的Mac可恢复清理／文档整合，再核成功donor的数据发送路径。

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
- 不派子代理，不跑QEMU。保留QRTR草稿、AnyRouter暂存及其他用户改动，显式路径提交。
- 临时一次性工具放Windows TEMP/Mac /private/tmp；research只独立Git克隆，笔记放lab。
  旧artifact Windows/WSL进Windows回收站，Mac原生Trash；不永久删除/清空Trash。
- 配套工作台maintenance/IN_PROGRESS.json存在时先完成该事务；引用同步应自动让开。
- 所有有效修补/工具/配置进入本仓commit＋push后刷。不得发布FW/OS执行件/签名密钥/
  私有凭据/设备备份/二进制派生payload头；外部来源/hash记录，按源码再生。
- 基础clean build与当前Wi-Fi增量复现分别报告，不把编译/host模型算实机或宣称未跑的从零整链。
