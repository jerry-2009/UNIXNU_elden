# Elden 当前状态 · 2026-11-21

HIF生命周期已在实机生效，但EAPOL仍3次提交、0完成，keys0/port0；完整stock恢复通过。
[实录](evidence/wifi-station-hif-hardware-20261121.json)。下一份1a7a7133候选集中一次读TX指针／
TCL/WBM配置／描述符metadata／真实模式响应，不改寄存器、时间或credit，不记录帧与凭据。
[候选](evidence/wifi-station-tx-20261121.json)。Mac本周整理已完成，旧产物仅入Trash。

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
| 电源 | 本机原厂ADSP/GLINK/PD与BMS、单短口供电及模式请求已有实录 | 双口净充、稳定旁路、80%与40–60%完整周期和持久化 |
| Wi-Fi | SM8750成功donor移植：32个BSS、真实VDEV/auth/assoc、iOS17桥 | EAPOL3发出后无TX完成，keys0/port0；DHCP、流量、重连／睡眠 |
| 蓝牙 | 原厂HCI／用户态与扫描链已有阶段性记录，Settings选项可见 | 配对、双向数据、持续使用／睡眠 |
| 其他外设 | offline-peripheral-fixes独立成果，GPU独立工作树 | 主线评审／集成／实机；马达和喇叭未经校准保持禁用 |

最新Wi-Fi源提交 `876de4c`，候选SHA
`87d1c43cce7d15a45794a8388948e59094209d95c924a746cfcb4410aeb4b915`，
session `2661d591ea5855d4`。真实认证／关联通过，但EAPOL只有3RX／3TX提交、0TX完成。
[当前实机证据](evidence/wifi-portable-station-hardware-20261121.json)／[实现](../drivers/EldenWifi/portable/station/README.md)。
扫描通过来自前一份[8ecacf44实录](evidence/wifi-portable-scan-hardware-20261120.json)，不是host模型。

平板已完整恢复stock Android、root、green、原充电／无线／扫描设置并请求熄屏。所有设备任务已结束。
协议teardown超时，独立BM-off／transaction idle／MSI4／PERST-low和物理fastboot通过；
不把这些混称为暖MHI复位成功。最新日志396713B/drop最大14、无重连；USB断开后计数未知。

源码唯一入口是本仓main。新克隆在工作台research，研究笔记在lab/reference-reviews。
完整Goal active，当前重点为数据发送完成→WPA2→DHCP／流量；之后回到电源剩余验收。
当前这轮后先执行用户要求的Mac Trash与文档整合。后续真机测试合并功能点，不重复已通过探针。
