# Elden 当前状态 · 2026-11-23

56 字节 HTT 配置已在 `b0d308f0` 和 `dc553008` 实测通过第二轮扫描和关联。两份均有 TCL 消费 3 个 EAPOL message 2，WBM、密钥和端口开放均为 0。`b0d308f0` 读回 bank `0x0a04`；`dc553008` 读 bank 时 UMAC 超时。[index-bank 实录](evidence/wifi-station-index-bank-hardware-20261122.json)

充电断链恢复 profile 的完整 28 阶段空目录 clean build 也已通过。BaseCrypto 994 个固定输入逐件校验并以包路径复制到临时 EDK II workspace，signed boot 通过静态 AVB/rollback 审核。它没有刷入设备，不能视为充电功能验收。
Mac本周整理已完成，137项旧产物及18项临时内容仅入Trash，未清空。

Wi-Fi 已从长期首次WMI阻塞推进到真实扫描、认证与关联。尚未完成WPA2／DHCP／可用流量。
这份文档只列当前事实；逐轮旧记录已原样保存在[历史快照](archive/20261121/CURRENT-STATUS.md)，
源码／构建与实机日志各自保持原SHA。

| 项目 | 当前证据 | 仍缺验收 |
| --- | --- | --- |
| 根卷／GUI | 128GiB UFS根卷，launchd、SpringBoard、Settings、真实上滑与点击已有记录 | 持久应用Data、长时稳定与流畅度 |
| 触控／显示 | 独立Digitizer/HID、抬指链；CPU显示约60ms样本，实指反馈明显改善 | 长时鬼触排除、完整GPU显示 |
| CPU／RAM | 八核实际online/work/timers/ipis=ff；本轮诊断RAM6GiB，GUI8GiB有独立实录 | 全16GB、安全地址压力验证；不要强制全核满载 |
| UFS／Data | 多槽IRQ/DMA与自动空闲唤醒已有实机；2GiB sparse Data独立GUI路径通过 | 诊断仍用旧RAM Data；持久Data、完整应用容量与压力 |
| USB／回程 | 内核CDC日志、会话绑定RPC、panic定时SDAM返回fastboot，完整stock恢复 | 断线／异常供电长期恢复 |
| 电源 | 原厂ADSP/GLINK/PD与BMS、单短口供电及模式请求有实录；断链恢复版完整28阶段源码clean build和静态签名审查通过 | 双口净充、稳定旁路、80%与40–60%完整周期和持久化，候选未实机测试 |
| Wi-Fi | SM8750 成功供体的扫描、VDEV/auth/assoc 与 iOS 17 桥已接入。实测关联并提交 EAPOL message 2 | WBM 回执、message 3/keys、DHCP 和流量 |
| 蓝牙 | v138 实机有 349 条完整扩展广播交给系统 HCI socket。共享 WCN 候选用 `ewt=1` 选择 mode 4，已链接和刷机，两次均未获得 CDC 会话 | 与当前 station 合并后实测 Settings 列表、配对、双向数据、睡眠与 WLAN 共存 |
| 其他外设 | offline-peripheral-fixes有笔/触觉/运动/RTC/相机离线交付；GPU另在独立工作树 | 主线逐项评审及实机；RTC NVMEM/alarm provider未绑定，马达和喇叭未经实测校准保持禁用 |

最近到达 station 的实机会话为 `1e9b27c2e2a87b47`。保留已通过的扫描配置，继续核对发送完成路径。[Wi-Fi 状态](WIFI-STATUS.md)
扫描通过来自前一份[8ecacf44实录](evidence/wifi-portable-scan-hardware-20261120.json)，不是host模型。

北京时间 11 月 22 日 12:13:08，实测候选已返回物理 fastboot，完成 stock Android 整像回读及 root、green、原充电／无线／扫描设置恢复。监督进程已结束。

源码唯一入口是本仓main。新克隆在工作台research，研究笔记在lab/reference-reviews。
完整 Goal 仍在进行。下一次 Wi-Fi 窗口合并扫描、关联、发送完成、WPA2、DHCP 与流量验收。充电断链恢复和双口净充仍待实机。RTC 离线 owner 未合入主线，持久化与闹钟仍待硬件验收。
Mac Trash与文档整合已完成，恢复清单见[维护记录](MAINTENANCE.md)。后续真机测试合并功能点，不重复已通过探针。
