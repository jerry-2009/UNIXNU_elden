# Wi-Fi当前主线 · 2026-11-21

最新OEM命令格式修补实机收到PEER_ASSOC确认（21ms），VDEV/auth/assoc与helper message2通过；
仍4个EAPOL RX／4TX提交、完成0／ACK0／keys0／port0。该轮快照TCL HP32/TP8、WBM0/0。
[最新实录](evidence/wifi-station-wire-hardware-20261121.json)。前一轮TCL消费全部3描述符的
[独立实录](evidence/wifi-station-tx-hardware-20261121.json)保持；不能混作本轮终态。
下一步核本机OEM数据TX路由／bank与VDEV响应物理MAC字段，不重复wire/wake/credit/BAR单项试验。
Mac本周整理已完成，旧产物仅入Trash，未清空。

Y700 TB322FC／SM8750／Peach HW2.0的真实扫描、VDEV启动、认证和关联已通过。
WPA2／DHCP／流量未通过：当前4个EAPOL RX／4个TCL TX提交、0发送完成、keys0、port0。
TCL消费不能当作无线发送完成；下一步核返回路由与描述符契约。

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
| EAPOL发送完成／密钥 | WBM无返回；keys0／port0；前一轮TCL消费3有独立实录 | [TX定位](evidence/wifi-station-tx-hardware-20261121.json)／wire |
| WPA2／DHCP／流量／重连／睡眠 | 未完成 | 下一次综合窗口 |
| 回程 | 独立BM-off/idle/MSI4/PERST-low、真实fastboot与完整stock恢复通过 | station协议drain超时仍保留 |

当前源码 `0573b38`；HIF修复 `0d8474f`；scan源 `fd52d2c`、实证 `fc33a8c`。
当前候选61f9066f/sessionfa7b794966c5f32c，floor1738713600／0／3。
设备已Android/root/green/原设置恢复并熄屏，所有设备任务terminal。
当前充电／内存／GPU分支不顺带改变，减少重复冒烟。

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
