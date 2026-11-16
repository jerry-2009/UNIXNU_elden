# Wi-Fi：固件已就绪，先修停机再接用户态服务

v170确认MODE_OFF入队成功，但未见MHI发送完成/接收应答，中断仍使能。下一步对接Linux平台
重启专用的PCI `shutdown` 回调，保留真实MHI复位、bus-master关闭、事务/IRQ排空和PERST检查。
不把卸载路径的MODE_OFF等待当作平台重启的必经步骤；也不伪造应答。设备已完整恢复Android。
[具体源代码依据与约束](WIFI-PLATFORM-SHUTDOWN.md)。

v169已定位到 `ath12k_qmi_firmware_stop()` 的MODE_OFF事务。前面的工作队列/PCI/核心清理均已返回，
调度循环在等待期间仍返回。QMI/MHI队列已经标记为IO完成类，不应重复改flag。下一步核对该请求
的TX完成、RX及MSI状态；不延长9秒回程掩盖问题。设备已完整恢复Android，仍未联网。
[本轮定位证据](../profiles/wifi-stop-trace/README.md)。

v168已修正建模确认的DMA清理生命周期，并实机记录`cleanup=0`；stage4保持。原QMI−12未再记录，
但没有QMI关闭成功或`nw_wifi_stop`返回证据，仍在9秒后兜底复位。完整Android恢复通过。
当前下一步是统一定位停止子调用，不能把本轮准入成功当作正常停机验收。详[v168](../profiles/wifi-drain-lifetime/README.md)。

v167已收到原厂 `FW_INIT_DONE`，Linux进入stage4/error0，MSI计数80；已完成真实
PCIe/SMMU/DMA/MHI/QRTR/QMI链路。QDSS文件名缺口已补，使用原厂6237B配置并核全SHA。
[当前实机与复现](../profiles/wifi-qdss-config/README.md)。

**联网仍未验收。** `nw_wifi_scan=0`只是把UI请求排队；BSS保持0。固定上游的
`nw_mainline.c`会通过控制socket把请求送给真实supplicant，而该服务尚未安装。
原厂MAC文件尚未接入，当前保留上游本地地址fallback，不能声称已采用本机原地址。

**下一步优先修停机。** stage4后mode-off QMI返回-12，WCN在9秒上限后未完成原生排空，
由已建立的平台复位兜底回fastboot。完整stock SHA、Android/root/green和原充电/无线/
后台扫描设置均恢复，但这一轮没有RESET/master-off/IRQ/PERST完成证据。v166较早状态的
reset1/1不能代替v167。源码显示DMA/FW停止过早，WLAN的platform/epoch也在排空前撤回；
要实现有界、同owner的清理期准入，保留故障/身份/撤映射保护，再验证真实排空。

之后接入已编译的上游arm64/iOS17 supplicant、实际IOKit网络桥及原厂MAC输入，验证
服务会话→真实扫描→关联→DHCP→双向流量和断线重连。不得用模拟成功回调替代。

v166修复真实控制socket漏注册，v163完成SMMU与触控共存，v158完成BAR/Peach身份，
v157完成Gen3×2根链路；各版本证据在相应profiles中。当前显式full-on预算仍非日用
电源策略；双口取电/完整保护周期/持久设置的充电验收缺口见[充电状态](CHARGING-STATUS.md)。

以下为前置组件的历史记录，不能覆盖上述最新实机边界。

## 已完成的前置项

原modem_a七件主要Peach固件的只读文件访问已有实现，尺寸/SHA按原厂备份固定。
路径与板级资源在`drivers/EldenWifi`、`EldenWifiResources.h`及工作台
`lab/records/wifi-elden-20261108/inputs.json`，不是PCIe/MHI已启动的证据。

官方Ath12kWifi已克隆到Windows和Mac各自Y700项目的`research/Ath12kWifi`。
当时正式参考清单为43仓（现65仓），包括后续所需的固定Linux7.0.14源。组件采用固定提交
`5f7f5a8a9f02f7ab45ed10a2f226e348c519a838`，不自动替换已有候选输入。
其README记录的实机范围是sheng/24A446上的开关、扫描、WPA2、DHCP及流量，
不能转记为本机或21H461已通过。

该版本默认用户态构建目标为arm64e/iOS27；新工具
`tools/build_elden_wifi_userspace.py`在独立输出目录取固定Git快照，改为arm64/iOS17。
只下载并验证4.25MB的wpa_supplicant2.12原版归档，未为用户态构建重复下载Linux/FreeBSD。
保留原sheng控制协议、原SME/WPA认证代码和已审核的注册/通知改动；另核899个原版文件逐字不变。
参考克隆未修改。重复输出拒绝覆盖，旧文件不删除。

已构建并本地签名的`unixnu-wpa_supplicant`：

- SHA256：`f54eb63475c7f3b3cb0d1d1ed78728a941fb8c07e363f88cf8c5095a69adecb7`
- CDHash：`b02572b5f0fd9e79790645ad33df708b24530295`
- 实际Mach-O为thin arm64、最低iOS17.0；仅链接libSystem.B.dylib，编译无警告/错误。
- 控制端点`org.unixnu.wifi.control`，原version1／40B头；尚未验证本机内核端点。

工作台材料`edl_work/wifi-userland-20261112`；Mac为项目内
`lab/wifi-userspace-20261112/build`。已生成原sheng形式的job和空网络配置模板，
**没有安装、没有合并launchd缓存或更新trustcache，也没有运行服务或提供网络密码。**
静态目标和签名检查不等于iPadOS加载、控制通道或认证实机通过。
完整来源见[服务记录](evidence/wifi-userland-20261112.json)。

## Peach必须使用本机Linux配置

ArmadaOS的TB322FC原始DTS明确固定到h0cheung提交
`6f97250ead155fc3b980856323e99a4623dae73d`。该源码的`ath12k/wifi7`有独立
PEACH0x110e条目，不需要将整个QCC2072配置当作猜测起点。

| 项目 | 本机Linux Peach | QCC2072条目 |
| --- | --- | --- |
| 硬件版本 | Peach HW2.0；拒绝未知SoC major | QCC2072 HW1.0 |
| internal_sleep_clock | false | true |
| download_tme_lite | true | 未设置 |
| board_api1_only | true | 未设置 |
| QMI能力位 | WLAN_EN、AUX_UC | QDSS_CFG_MISS、PCIE_PERST_NO_PULL、AUX_UC |

数据通路使用QCC2072 ops/描述符/寄存器，CE/MHI等复用WCN7850，**这些复用不等于整份硬件配置可互换**。
Pagani的`peach.py`明确标有未验证推测，README最近实机仍停在S7I读取失败，未完成网络初始化。
可借鉴拆分方法，不能直接复制其七rail、低地址DMA池、跳过读回或整片QCC2072映射。
后续应逐项移植本机独立Peach配置及其QMI/固件依赖，再验证实际PCI身份、供电、DMA/MSI和启动。
来源与字段对照见[Peach记录](evidence/wifi-peach-profile-20261112.json)。

进一步追到原Y700补丁：QMI收到目标能力后，先应用固件OL-CPR电压请求，成功才可继续TME-Lite。
新[OL-CPR适配](../drivers/EldenWifi/OLCPR.md)已统一复用原WcnPower算法/DTS映射，去除上一轮重复计算。
20,128组Linux数值对照、4,096组新旧兼容及原12电源场景通过，两个ARM64对象绑定到同一提供者。
原C层发送器已有，仍受BT Ready/epoch/失败隔离限制；Wi-Fi的QMI→原生WLAN owner路由尚未接通。
适配器只产生计划，本轮没有调压。
不能把缺少的回调改成成功来绕过这个前置条件。

[Peach回移](../drivers/EldenWifi/peach/README.md)现已准备9个驱动文件和电源接口头，
6个变化C单元在ARM64/iOS17编译通过；171份实际输入核对通过，尚非整套125对象或内核链接。
加载顺序/失败传播的实际函数体测试通过。更正：原TME处理对特定0x53限制状态有非致命例外，
保留限制日志，不称为TME加载成功；其它错误及OL-CPR前置失败仍停止，现场行为尚待验证。
完整警告和范围见回移说明；真实WLAN电源提供者仍未接通。

后续[完整C运行时](../drivers/EldenWifi/RUNTIME.md)已按官方准备流程编译125对象，
456份实际编译输入和符号重命名检查通过；对当前内核缺失的外部符号为真实WLAN电源接口。
官方生命周期host测试通过（先修正其两处模拟回调缺少radio_idx参数的UBSan失败）。
板级PCIe/DMA/网络回调仍需接入，9334条编译警告保留并待完整审核，未链接新内核或进行联网实测。

警告审核已定位并修复[MHI下载状态读取](../drivers/EldenWifi/peach/MHI-STATUS-READ.md)：
原BHI在先读到pending、后读失败时会误报成功；现在独立保留并返回读取错误。
实际函数故障注入、完整125对象重建和比较通过；功能代码只改mhi_boot.o，其他编译输入455项保持。
两条tx_status警告消除后仍有9332条，后续审核继续。未在平板上复现该故障，也未据此宣称无线可用。

官方栈锁定Linux7.0.14，而上述Y700源码是7.2.8；独立Peach条目还涉及9个ath12k文件和电源序列接口。
新`research/linux-ath12k-7.0.14`固定在458c6079…供逐项回移，未更换官方栈的锁定版本。
Windows该克隆有8个netfilter头文件因大小写冲突显示修改，原样保留；消费源码应从Git对象核对，
不reset、不将这些路径的工作树视图冒称逐字原版。它们不是本次OL-CPR组件的输入。

## 复现与下一步

在macOS、Python3.12/Xcode环境运行，所有输出用新目录：

```sh
python3 tools/build_elden_wifi_userspace.py \
  --component-repository /path/to/research/Ath12kWifi \
  --supplicant-archive /path/to/wpa_supplicant-2.12.tar.gz \
  --output /path/to/new-wifi-userspace
python3 tools/analysis/audit_peach_profile.py \
  --repository /path/to/research/tb322fc-linux-kernel --output /path/to/new-evidence
```

归档URL/校验值取固定组件`tools/source-lock.json`。构建工具只修改隔离快照的目标/依赖准入和输出保护；
认证源由原组件准备器生成，未引入自制认证或假成功响应。还需原生网络/Apple80211的21H461精确ABI、
内核控制端点、用户态job/trust与固件载入的完整整合；持久凭据、Wi-Fi/蓝牙共用供电与睡眠也未完成。

充电主线仍保留双口仲裁与完整保护周期缺口；本轮参考同步无相关新提交，
ArmadaOS仍明列双口充电待完善。完整外围Goal未完成，GPU最后、扬声器先讨论保护。
