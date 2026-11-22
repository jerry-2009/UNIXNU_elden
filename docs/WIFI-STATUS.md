# Wi-Fi当前主线 · 2026-11-22

原厂 56 字节 HTT 环配置候选 `b0d308f0` 已跑完第二轮扫描和关联，保留 32 个 BSS、
收到 136 个管理帧，CE 提交与完成均为 59。这是一次实机通过，尚需确认重复启动稳定性。
关联后确认 bank 为 `0x0a04`，TCL 消费 3 个 EAPOL message 2，WBM 指针仍为 0，
密钥和受控端口尚未开启。原厂 Android、root、green、原充电和无线设置已恢复。
[56 字节配置实录](evidence/wifi-station-oem-srng-hardware-20261122.json)

候选 `44bf406e` 实测未发出第二轮扫描。第一轮结束后，六个 HTT 环的描述符已提交，
但 HTT 端点的 CE 源环未在原期限内被消费，状态从 628 进入 612，返回传输错误 `-4`。
当时 CE 总计提交 22／完成 18。UMAC `-110` 在后续停机时才出现。下一步追查
HTT 环建立阶段设备为什么停止消费。此次未进入关联后的 bank 设置。已完整恢复原厂 Android。
[实机记录](evidence/wifi-station-htt-drain-hardware-20261122.json)

CiscoMac 的状态机测试覆盖了源环等待、消费后提交扫描及到期返回传输错误。整核链接、
21 项错误组合检查、签名审查和 Windows 整像摘要核对均通过。
[增量构建入口](../drivers/EldenWifi/portable/station/OEM-TX-METADATA.md)

上一份单 PDEV bank 候选 `c9427d2f` 在第二轮扫描前遇到 UMAC `-110`。
该版保留八字节 HTT。原厂 bit 14 对照只在关联后写 bank，本轮未进入该路径，
因此 bank 对 WBM 的影响仍未实测。单字 HTT 的历史失败不能解释这一轮。
候选已完整恢复原厂 Android。下一步先追第二轮扫描前的 UMAC 生命周期，
等链路稳定后再验证 bank 与 WBM。[单 PDEV bank 实录](evidence/wifi-station-bank-hardware-20261122.json)

最近一次到达关联的候选 `60ca685d` 恢复第二轮扫描，保留 32 BSS、收到 142 管理帧，随后认证和关联成功。TCL 消费 3 个 EAPOL message 2 描述符，实际记录了 critical 字段，WBM 完成、ACK、密钥与端口开放仍为 0。已回真实 fastboot 并完成原厂镜像整像读回、root、green、原充电与无线设置恢复。[关联实录](evidence/wifi-station-critical-hardware-20261122.json)

上一份单字 HTT 候选 `3f8f74e1` 的第二轮扫描未启动，UMAC 访问 `0x1b86400` 超时（`-110`），最终停在 `state=612 error=-8`。[单字 HTT 实录](evidence/wifi-station-oem-metadata-hardware-20261122.json)

八字节 HTT 请求的上一轮已通过第二轮扫描、PMK 准入及 21 ms 的 PEER_ASSOC，收到并提交各 1 个 EAPOL。TCL 快照 HP=TP=8 words，WBM HP=TP=0，密钥与受控端口仍为零。[八字节 HTT 基线实录](evidence/wifi-station-tx-priority-hardware-20261121.json)

八字节基线采用 legacy PHY，实际描述符 TID 为 0。成功供体的 10f-c 在该模式完成 WPA2，随后 10g 验证 DHCP 与网关。[小米 Pad 8 Pro 实录](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/drivers/wifi.md#88-the-batched-tablet-test-list)

候选 `60ca685d` 在八字节 HTT 基线上为站点队列中的 EAPOL 增加 critical flow override 和 semi-hard notify，保持原 TCL 元数据及 legacy TID 0。本轮明确该字段组合未带来发送完成。后续优先核对原厂 station bank 与完成路由在相同 VDEV/peer 状态下的实际配置。[派生与范围](../drivers/EldenWifi/portable/station/OEM-TX-METADATA.md)

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
| EAPOL发送完成／密钥 | 最新 TCL 消费 3，WBM 完成 0，keys0／port0 | [最新实录](evidence/wifi-station-critical-hardware-20261122.json) · [基线](evidence/wifi-station-tx-priority-hardware-20261121.json) |
| WPA2／DHCP／流量／重连／睡眠 | 未完成 | 下一次综合窗口 |
| 回程 | 独立BM-off/idle/MSI4/PERST-low、真实fastboot与完整stock恢复通过 | station协议drain超时仍保留 |

八字节基线候选 `9c9fc5d3`，源码 `c62a26e`，session `80ad897d6443755d`，floor 1738713600／0／3。CiscoMac 的 ARM64 对象、整核、20 项拒绝用例及签名包静态审查通过。增量入口为 `tools/build_wifi_station_tx_priority.py`，沿用原 PMK 就绪 runtime2。四份旧构建输入逐字恢复了冻结的 CRLF，Git 保留原字节。

最新实测源码 `7f7bb65`，session `bf1555e8dd6c5c07`，候选与恢复镜像均通过整像读回，回滚索引为 1738713600／0／3。保留八字节 HTT 版本请求及 56 字节环配置，继续核对关联后的发送路径。

实际OEM模块排除隐式RBM：相关helper为ret，TCL0→WBM0/RBM5与donor一致。
单设备vdev-ID检查和物理MAC选择有差异，尚未证明是TX原因；没有因此猜写bank。
命令格式的新增字段与尾部数组来自已加载模块的尺寸/指令，原donor blob保持。
八字节基线受控退出有协议 drain 超时。最新 OEM 候选记录了物理 fastboot 和完整原厂恢复。

复现源码及准确依赖：[portable scan](../drivers/EldenWifi/portable/README.md)、
[完整station](../drivers/EldenWifi/portable/station/README.md)。基础从零build已单独验收；
这些Wi-Fi增量命令有明确前置对象路径，尚未集成到新克隆一条命令，不能宣称已从零重验当前Wi-Fi。
网络凭据只保留在私有构建输入，SSIDs/BSSIDs/keys不进入Git与日志。

过去反复的WMI／CE3／wake／OEM wire诊断见[原样历史](archive/20261121/WIFI-STATUS.md)。
原源码／结果SHA不重写；当时失败不能被新的扫描通过倒写成成功。
