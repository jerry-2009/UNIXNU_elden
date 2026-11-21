# 文档入口

| 需要查什么 | 当前入口 |
| --- | --- |
| 当前实机状态与下一步 | [CURRENT-STATUS](CURRENT-STATUS.md)、[PLAN](PLAN.md) |
| Wi-Fi | [WIFI-STATUS](WIFI-STATUS.md)、[成功SM8750审核](SM8750-WIFI-REUSE-AUDIT-20261120.md)、[本机OEM适配](../drivers/EldenWifi/portable/station/OEM-WIRE.md)、[全组织复用审核](UNIXNU-ORG-REUSE-AUDIT-20261115.md) |
| 充电／双口／保护 | [CHARGING-STATUS](CHARGING-STATUS.md)、[验收范围](CHARGING-ACCEPTANCE-REVIEW-20261119.md)、[双口接口契约](DUAL-INPUT-CONTRACT.md) |
| 用户态容量／卡顿 | [USER-GUI-STORAGE](USER-GUI-STORAGE.md)、[Data所有权](DATA-SEED-OWNERSHIP.md)、[INPUT-STATUS](INPUT-STATUS.md)、[显示拷贝](FRAMEBUFFER-WC.md)、[MEMORY-EXPANSION](MEMORY-EXPANSION.md) |
| 触控／用户态初始化来源 | [触控参考核对](TOUCH-REFERENCE-CHECK.md)、[About网络服务初始化](NETWORK-INITIALIZATION.md) |
| 蓝牙／共享无线电源来源 | [BlueTool生命周期](BLUETOOL-LIFECYCLE.md)、[WCN共享供电](WCN-SHARED-POWER.md)、[WLAN原生接入](WLAN-POWER-NATIVE.md)、[父时钟](WCN-PARENT-CLOCK.md) |
| 无人值守／真实回程来源 | [WCN停止](WCN-SHUTDOWN.md)、[PCI平台shutdown和物理fence](WIFI-PLATFORM-SHUTDOWN.md)、当前[Wi-Fi回程结果](WIFI-STATUS.md) |
| 从零复现／外部输入 | [CLEAN-BUILD](CLEAN-BUILD.md)、[CLEAN-INPUTS](CLEAN-INPUTS.md)、[REPRODUCIBILITY](REPRODUCIBILITY.md) |
| 目录／回收／恢复 | [MAINTENANCE](MAINTENANCE.md) |
| 其他分支交接 | [PERIPHERAL-DELIVERY-REVIEW](PERIPHERAL-DELIVERY-REVIEW-20261119.md)、[笔输入可行性](AP501U-PENCIL-FEASIBILITY-20261114.md)、[双马达可行性](HAPTICS-IPADOS-FEASIBILITY-20261114.md)；最新交付按各独立工作树STATUS/GPU-MERGE |
| 旧逐轮状态／handover | [20261121原样历史](archive/20261121/README.md) |
| 实证JSON | evidence/各轮记录，区分hardware_tested与host/model |

当前入口不按日期逐段累加。新实证改写当前结论，旧材料留在对应历史文件或evidence；
不改历史JSON的原始路径／SHA，用维护迁移表解析。

本索引覆盖docs根目录全部29份主题文档。CURRENT-STATUS、WIFI-STATUS和PLAN给出当前
主线结论；带日期的审核、驱动设计和逐轮证据描述其对应提交时点。它们仍提供来源、
恢复方法或ABI依据，因此保留，不能把旧标题里的“尚未上机”扩大为当前整个驱动状态。
冻结profiles与历史文档的字节/路径不改；新的实机结果只更新当前入口并新增独立evidence。
