# Wi-Fi当前主线 · 2026-11-21

最新实机确认 PMK 就绪、PEER_ASSOC 21ms、收到并提交各 1 个 EAPOL。TCL 快照 HP=TP=8 words，WBM HP=TP=0，密钥与受控端口仍为零。原厂 Android、root、green、原充电与无线设置已恢复。[本轮实录](evidence/wifi-station-tx-priority-hardware-20261121.json)

本轮关联采用 legacy PHY，实际描述符 TID 为 0。WMM 模式下才会采用候选的 EAPOL TID 7 分支。固定成功供体的 10f-c 在 legacy 模式完成 WPA2，两个 EAPOL 完成项由固件返回，随后 10g 验证 DHCP 与网关。当前沿该成功组合核查本机 OEM 发送分类与固件完成返回路径。[小米 Pad 8 Pro 实录](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/drivers/wifi.md#88-the-join-and-the-data-path)

成功参考是[小米Pad8Pro lenzhang](https://github.com/lenzhang/UniXNU-xiaomipad8pro)，
固定2438556c，其记录有WPA2／DHCP／公网、睡眠及固件崩溃恢复实证。
[官方11机型／23仓审核](SM8750-WIFI-REUSE-AUDIT-20261120.md)列出未成功、404及API403边界。
只导入portable协议，保留本机原厂固件／板级接线、IRQ/DMA owner和Sheng iPadOS17桥。
macOS27系统ABI与Y700固件不整包覆盖。

| 验收 | 结果 | 实录 |
| --- | --- | --- |
| PCIe／DMA／原厂FW／QMI | 已实际进入Mission Mode与FW_INIT_DONE | [v166](evidence/wifi-control-v166-20261116.json) |
| portable扫描 | 两轮，32保留BSS（上限32）、113管理帧、HTT6环、CE24/24/drop0 | [scan](evidence/wifi-portable-scan-hardware-20261120.json) |
| station与iOS桥 | VDEV/auth/assoc，stage714；iOS桥start0；helper精确签名准入 | [station](evidence/wifi-portable-station-hardware-20261121.json) |
| 本机OEM命令格式 | station peer确认21ms；helper生成4次message2 | [wire](evidence/wifi-station-wire-hardware-20261121.json) |
| EAPOL发送完成／密钥 | 当前 TCL 消费 1，WBM 完成 0，keys0／port0 | [本轮](evidence/wifi-station-tx-priority-hardware-20261121.json) · [早期独立轮次](evidence/wifi-station-tx-hardware-20261121.json) |
| WPA2／DHCP／流量／重连／睡眠 | 未完成 | 下一次综合窗口 |
| 回程 | 独立BM-off/idle/MSI4/PERST-low、真实fastboot与完整stock恢复通过 | station协议drain超时仍保留 |

当前候选 `9c9fc5d3`，源码 `c62a26e`，session `80ad897d6443755d`，floor 1738713600／0／3。CiscoMac 的 ARM64 对象、整核、20 项拒绝用例及签名包静态审查通过。增量入口为 `tools/build_wifi_station_tx_priority.py`，沿用原 PMK 就绪 runtime2。四份旧构建输入逐字恢复了冻结的 CRLF，Git 保留原字节。

实际OEM模块排除隐式RBM：相关helper为ret，TCL0→WBM0/RBM5与donor一致。
单设备vdev-ID检查和物理MAC选择有差异，尚未证明是TX原因；没有因此猜写bank。
命令格式的新增字段与尾部数组来自已加载模块的尺寸/指令，原donor blob保持。
本轮受控退出仍协议drain超时，晚期UMAC refusal和真实物理fence通过分开记录。

复现源码及准确依赖：[portable scan](../drivers/EldenWifi/portable/README.md)、
[完整station](../drivers/EldenWifi/portable/station/README.md)。基础从零build已单独验收；
这些Wi-Fi增量命令有明确前置对象路径，尚未集成到新克隆一条命令，不能宣称已从零重验当前Wi-Fi。
网络凭据只保留在私有构建输入，SSIDs/BSSIDs/keys不进入Git与日志。

过去反复的WMI／CE3／wake／OEM wire诊断见[原样历史](archive/20261121/WIFI-STATUS.md)。
原源码／结果SHA不重写；当时失败不能被新的扫描通过倒写成成功。
