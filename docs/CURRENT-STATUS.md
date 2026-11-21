# Elden 当前状态 · 2026-11-21

最新 Wi-Fi 源码候选 `3f8f74e1` 已在 CiscoMac clean build 环境签名并通过静态审查，设备离线，尚未实机测试。上一轮 `9c9fc5d3` 在 PMK 就绪后提交 1 个 EAPOL message 2，TCL 已消费，WBM/keys/port 均为 0，设备已完整恢复 Android。[候选实现与构建步骤](../drivers/EldenWifi/portable/station/OEM-TX-METADATA.md) · [最近实机记录](evidence/wifi-station-tx-priority-hardware-20261121.json)

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
| Wi-Fi | SM8750成功donor移植：扫描、VDEV/auth/assoc与iOS17桥；原TID0候选有PMK准入、peer确认、EAPOL message2提交 | 最新本机OEM HTT/TCL候选待实机验收；WBM回执、message3/keys、DHCP和流量 |
| 蓝牙 | 原厂HCI／用户态与扫描链已有阶段性记录，Settings选项可见 | 配对、双向数据、持续使用／睡眠 |
| 其他外设 | offline-peripheral-fixes有笔/触觉/运动/RTC/相机离线交付；GPU另在独立工作树 | 主线逐项评审及实机；RTC NVMEM/alarm provider未绑定，马达和喇叭未经实测校准保持禁用 |

上一轮实机源码提交 `c62a26e`，session `80ad897d6443755d`。本轮 build-only 源码为 `0a72509`。message 3、密钥、端口授权和网络流量仍未通过。按成功供体的 legacy 模式及本机原厂 HTC/WMI/DMA 完成契约继续核对。[Wi-Fi 状态](WIFI-STATUS.md)
扫描通过来自前一份[8ecacf44实录](evidence/wifi-portable-scan-hardware-20261120.json)，不是host模型。

平板已由用户带走；离开前完整恢复stock Android、root、green及原充电／无线／扫描设置，并请求熄屏。
协议teardown超时，独立BM-off／transaction idle／MSI4／PERST-low和物理fastboot通过；
暖 MHI 复位待验证。最新日志 441810 B，观测掉字计数最高 87，无重连。设备已由用户带走，进入离线阶段。

源码唯一入口是本仓main。新克隆在工作台research，研究笔记在lab/reference-reviews。
完整 Goal active，Y700 目前离线。接回后优先测试新 OEM HTT/TCL 候选及 WPA2→DHCP/流量，再按有效窗口验收充电断链恢复与双口净充。RTC离线owner未合入主线，且没有硬件持久化/闹钟验收。
Mac Trash与文档整合已完成，恢复清单见[维护记录](MAINTENANCE.md)。后续真机测试合并功能点，不重复已通过探针。
