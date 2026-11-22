# Elden 主线计划 · 2026-11-21

按已证明的阻塞推进，成功参考优先，合并相关功能到一次有明确验收标准的真机窗口。
完整基本外设Goal active，GPU最后。旧逐轮计划保存在[历史快照](archive/20261121/PLAN.md)。

1. 本周Mac整理已完成：137项旧产物、18项临时内容移入原生Trash，原路径／新路径／SHA
   清单和当前依赖保留；垃圾桶未清空，GPU和其他工作树未改。文档入口为INDEX。
2. Wi-Fi先稳定第二轮扫描。八字节 HTT 的 `60ca685d` 已关联并由 TCL 消费 3 个 EAPOL，
   WBM 回执仍为 0。单 PDEV bank 候选在关联前发生 UMAC `-110`，尚未写 bank。
   成功供体 Piano2438556c 的 legacy WPA2 使用 TID 0，EAPOL 完成来自固件。
   下一次将扫描、关联、WBM、WPA2、BSD 收发、DHCP、流量和完整回程放入同一窗口。
3. 系统Wi-Fi接口：复用Sheng同21H461桥；Mac27 donor ABI只作方法参考。
   要求系统扫描/选择SSID/加入/退出/重新加入与实际网络一致，不能靠虚假ready／credit。
4. 电源剩余：双口仲裁和真实净充、旁路、80%／40–60%完整阈值、拔插／睡眠恢复／持久设置。
   以本机原厂代码/HAL/实际仪表为准，失败不强写FET／OTG或绕温控。
5. Data／性能：持久Data优先于全16GB；保留8GiB GUI独立基线，诊断6GiB不变。
   测实际page-in／IO／CPU等待再优化；不把verbose速度当UFS吞吐，也不全核拉满。
6. 蓝牙配对／双向数据／休眠；与Wi-Fi共享owner和电源恢复一并验证。
7. 评审offline-peripheral-fixes（笔、RTC、传感器、摄像头、马达）具体commit与集成说明，
   只合当前主线可验证组件。马达gain／boost／连续输出与喇叭保持关闭，先讨论保护衰减。
8. GPU按codex/elden-gpu-offline的GPU-MERGE独立衔接，不能整份旧树覆盖。

每份有效源修补在 `D:\Desktop\Git\UniXNU_elden` main commit＋push之后才刷。
唯一设备HA2A1PT2；仅boot_a；floor1738713600/footer0/parent3；fresh>=3500mV/soc-ok、
签包与GPT检查、全像读回、会话日志、真实fastboot/full stock/root/green/原设置恢复。
供电不足则回Android充电或离线。无需重复向已授权无人值守用户请求确认。

关键入口：[当前状态](CURRENT-STATUS.md)、[Wi-Fi](WIFI-STATUS.md)、[充电](CHARGING-STATUS.md)、
[目录维护](MAINTENANCE.md)、[复现范围](REPRODUCIBILITY.md)、[从零基础构建](CLEAN-BUILD.md)。
