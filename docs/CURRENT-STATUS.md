# Elden 当前状态 · 2026-11-21

最新OEM命令格式修补实机收到PEER_ASSOC确认（21ms），VDEV/auth/assoc与helper message2通过；
仍4个EAPOL RX／4TX提交、完成0／ACK0／keys0／port0。该轮快照TCL HP32/TP8、WBM0/0。
[最新实录](evidence/wifi-station-wire-hardware-20261121.json)。前一轮TCL消费全部3描述符的
[独立实录](evidence/wifi-station-tx-hardware-20261121.json)保持；不能混作本轮终态。
下一步核本机OEM数据TX路由／bank与VDEV响应物理MAC字段，不重复wire/wake/credit/BAR单项试验。
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
| 电源 | 本机原厂ADSP/GLINK/PD与BMS、单短口供电及模式请求已有实录 | 双口净充、稳定旁路、80%与40–60%完整周期和持久化 |
| Wi-Fi | SM8750成功donor移植：32个BSS、真实VDEV/auth/assoc、iOS17桥；OEM命令格式收到peer确认21ms | EAPOL message2已生成，WBM完成0，keys0/port0；WPA2、DHCP、流量、重连／睡眠 |
| 蓝牙 | 原厂HCI／用户态与扫描链已有阶段性记录，Settings选项可见 | 配对、双向数据、持续使用／睡眠 |
| 其他外设 | offline-peripheral-fixes独立成果，GPU独立工作树 | 主线评审／集成／实机；马达和喇叭未经校准保持禁用 |

最新Wi-Fi源提交 `0573b38`，候选SHA
`61f9066fa6cb26c102528454ce5426072635acef3f4e8ceecd06d40f9e134a53`，
session `fa7b794966c5f32c`。EAPOL4RX／4TX提交，无message3／密钥／端口授权；提交不等于RF发送或ACK。
[当前实机证据](evidence/wifi-station-wire-hardware-20261121.json)／[实现](../drivers/EldenWifi/portable/station/OEM-WIRE.md)。
扫描通过来自前一份[8ecacf44实录](evidence/wifi-portable-scan-hardware-20261120.json)，不是host模型。

平板已完整恢复stock Android、root、green、原充电／无线／扫描设置并请求熄屏。所有设备任务已结束。
协议teardown超时，独立BM-off／transaction idle／MSI4／PERST-low和物理fastboot通过；
不把这些混称为暖MHI复位成功。最新日志354403B/drop最大2、无重连；USB断开后计数未知。
受控退出时另有UMAC timeout；它不能反推为首个TX失败原因。

源码唯一入口是本仓main。新克隆在工作台research，研究笔记在lab/reference-reviews。
完整Goal active，当前重点为数据发送完成→WPA2→DHCP／流量；之后回到电源剩余验收。
Mac Trash与文档整合已完成，恢复清单见[维护记录](MAINTENANCE.md)。后续真机测试合并功能点，不重复已通过探针。
