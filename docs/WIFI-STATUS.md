# Wi-Fi：固件与服务已接通，WMI完成仍待修复

v190实机获得37条完整顺序：固件公布模式0/5和物理pdev1/2；实际请求DBS1，
随后收到0x4010模式响应事件。其状态字段尚未解析，不能宣称模式转换成功。源代码明确
在single-pdev分支把逻辑编号设为0，不能只凭1/2与0不同就改编号。两条PDEV请求仍未
回收，Wi-Fi尚未联网。下一步核准确响应状态及实际CE/DMA状态。
[本轮证据](evidence/wifi-mode-v190-hardware-20261119.json)。完整回程和stock/root/原设置
恢复通过。打包入口现生成与原生文件哈希绑定的身份清单，并继续逐项核加载内容；本轮
已经实际通过这条自动路径。源仓与工作台同步记录保留完整Goal及所有硬件验收边界。

v189实机捕获21条完整WMI/CE3顺序：初始化命令1/0x401e的slot0/1已回收，随后
PMF_QOS(0x22)、DYNAMIC_BW(0x0a)以pdev0入队slot2/3，首次失败前未见新回收；
ARP_AC_OVERRIDE(0x23)因credit0返回−11。后两缓冲位于较高IOVA，但仍在已声明128MiB内，
不能据地址断言DMA故障；pdev编号正确性也仍待核。下一步核实际映射/生命周期和固件cap。
[实机顺序与回程证据](evidence/wifi-ce3-flow-v189-hardware-20261118.json)。

本轮保留90秒运行回程，完整捕获DMA fence/MSI排空/PERST/WCN停机并恢复stock Android/
root/green/原充电与无线扫描设置；新恢复器两次观察即核对一致。Wi-Fi仍未扫描联网。
日志296154字节、64次status/drop最大0，无重连；断开后计数不可读，不扩大完整性结论。
GPU与笔输入已具离线构建成果，均未集成或实机验收；继续按Wi-Fi主线、GPU最后推进。

2026-11-18 v188：真实PCI窗口与唤醒核对通过，动态窗口0x37、0x3278回读0x40000037；
Peach原厂分支明确采用此动态路径。CE3直接HP/TP仍0/0，coherent DMA TP8、通知HP16，
这些差异的寄存器语义及完成路径仍须查证，不能直接归咎固件或改成static映射。
本轮完整捕获DMA fence/MSI排空/PERST/WCN停机及stock Android/root/green/原设置恢复。
暖MHI reset未证明，扫描/关联/DHCP/流量均未验收。下一步优先核shadow驱动环的直接CSR
读取语义与设备完成链。[本轮证据](evidence/wifi-pci-window-v188-hardware-20261118.json)。

**v179与用户操作窗口已收尾。** Wi-Fi已确定 WMI 走CE3，实际收到过2个credit，随后发送环
HP16/TP8未推进；下一步审计通知路径。用户操作另证实512MiB Data发生大量ENOSPC，
SpringBoard重载和PPT已记录，实际RAM仍6GiB、八核onlineff。先补可用Data空间再复测，
不将它当作Wi-Fi WMI故障的既定原因。两轮均完整恢复Android。
[GUI/Data证据](USER-GUI-STORAGE.md) · [Wi-Fi证据](../profiles/wifi-credit-trace/README.md)。

**v178：首次 WMI 超时时，采样的硬件/软件待处理中断均为0，MSI仍启用且无错误。**
尚不能确定第一笔 credit/completion 丢在哪；不再将旧 CE sw_index 直接视作积压。上游随后
会请求固件 RAM dump，后续失败受此影响，应以首次失败前的数据为准。HTC/实际 wifi7 CE 与
Armada固定源码一致，没有可直接照搬的协议差异。完整恢复 Android 通过。
[快照与限制](../profiles/wifi-wmi-snapshot/README.md)。

**v177：扫描准入保持关闭，暴露了 MAC 启动中的 WMI 命令超时。** INFO 返回 DRIVER_FAILED9，
WMI_PDEV_SET_PARAM 超时、credits0；v175有同样错误，v176只是一次成功。下一步定位 MSI/CE 完成
处理链路，不把 stage4 当作接口已启动，也不把固件 DDR 比较差异当成 RAM 损坏。
完整自动回程与 Android 恢复通过。[本轮证据](../profiles/wifi-service-scan/README.md)。

**v176：第二次 INFO 已返回成功，服务初始化继续完成，保留到自动回程。** 首次未就绪的连接
已经收走诊断扫描事件，现有一次性测试标记没有给新连接重发；本轮没有观察到真正 SCAN 命令，BSS0。
下一步按当前会话的成功 INFO 应答安排诊断扫描，不修改认证或硬件逻辑。完整恢复 Android 已通过。
[实机时序](../profiles/wifi-service-control-trace/README.md)。

**v175：真实 supplicant 已获精确启动准入并连接控制接口，但随后反复断开。**
本轮记录31次连接/30次断开，BSS0；不能宣称扫描或联网完成。下一步收集原客户端初始化
和控制请求的真实错误码。自动回程/完整恢复 Android 通过，串口报告丢40字节。
[当前证据](../profiles/wifi-service-owner/README.md)。

**v174：服务资产和原厂 MAC 已实机接入，固件仍到 stage4。** 当前明确卡在 supplicant 的
AMFI 启动约束 c[8]p[1]m[1]e[6]，没有控制连接或真实扫描结果。下一步复用既有、限定路径与
精确 CDHash 的 RAM overlay 启动规则，再接网络桥；不为此改硬件时钟。完整自动回程和 Android
恢复已通过，所有任务结束。[本轮证据](../profiles/wifi-service/README.md)。

v167起已经进入真实固件 `FW_INIT_DONE`/Linux stage4，PCIe/SMMU/DMA/MHI/QRTR/QMI
均实际运行。v173又完成平台回程：真实回调返回/解绑0/配置0，bus-master实读关闭，事务
已采样为空闲，MSI停止且无在途处理，PERST低确认，WLAN停机成功，完整恢复stock Android。
[当前回程基线](../profiles/wifi-platform-fence/README.md)。这不代表MHI暖复位成功：2/ff04仍保留。

**联网还未验收。** 真实arm64/iOS17 supplicant、launchd任务、签名/信任、原厂MAC及控制
socket已经接入并有实机握手；这不等于MAC启动或网络桥通过。当前WMI初始化命令超时、
credit耗尽，诊断扫描保持准入关闭，BSS仍为0。先修实际完成链，再验扫描、关联、DHCP、
双向流量和重连；`nw_wifi_scan=0`仍只能证明请求入队。

不再重复只测回程的镜像；后续真实功能候选沿用同一已验回程链。充电双口取电、持续净充、
完整保护周期和持久设置仍欠验，见[充电状态](CHARGING-STATUS.md)。蓝牙配对和睡眠也未完整完成。

以下为前置组件的历史记录，不能覆盖上述最新范围。

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
