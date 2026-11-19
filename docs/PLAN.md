# Elden 基本可用实施计划

2026-11-20普通VDEV协议差异已修：原厂要求空MLO数组（tag18/len0/4B），
目前Linux发送省略。只修Peach非MLO创建；20个实际旧新/原厂helper模型与24资格反例、
整核/签包通过。候选c37cd59d，session7fde4cc64a53f234，未实机；联网未完成。
[复现及契约](../drivers/EldenWifi/peach/VDEV-MLO-ARRAY.md)／[证据](evidence/wifi-vdev-array-20261120.json)。
下一轮一次核VDEV与scan；停机须真实证明，不因物理回程成功而称排空成功。

2026-11-20原厂UMAC候选实机有推进：get0/held1、scratch2；CE3从2条到16条，
首次失败移至VDEV20488。扫描/BSS仍0，不能称联网成功。停机未记录put/drain/fence，
保留资源至有界物理复位；完整stock/root/green/原设置恢复通过。
[本轮实录](evidence/wifi-umac-wake-hardware-20261120.json)。下一步核普通VDEV必需空MLO
数组及停机等待，不重复纯唤醒测试；完整Goal继续active。

2026-11-20原厂模块确认独立UMAC握手：实际MHI引用后写0x3004，读取1e04040必须为2。
新显式候选37项helper模型、17资格反例、原生/整核/入口/签包通过；候选21b9231b，
sessionb86eb5d73f05fd7b，floor1738713600/0/3。未实机，下一轮一次核握手与CE3推进。
[机制与复现](../drivers/EldenWifi/UMAC-WAKE.md)／[证据](evidence/wifi-umac-wake-20261120.json)。
Wi-Fi未联网，完整Goal仍active。

2026-11-20唤醒引用实测：真实get0/held1与put1/held0通过，但仍30次WMI超时，CE3
依旧sw2/write4/hp16/tp8、BSS0。这个对照未消除阻塞，不重复或提升为默认；也不能据此
排除所有MHI电源问题。站点4发布、net drain0及完整真实DMA fence／MSI／PERST／stock/
root/green/原设置恢复通过。日志293029B/drop0/无重连，断开后计数未知。
[本轮](evidence/wifi-mhi-lease-hardware-20261120.json)。下一步保持普通无hold基线，核Peach
描述符／地址契约后再改硬件行为。完整Goal active，Wi-Fi仍未联网。

2026-11-20有界MHI唤醒引用对照已签：实际get_sync保持到PCI stop/power-down，失败
不补credit、不延时，编译选项显式启用。34实际helper模型场景、12资格反例与整核／签包通过；
PCI120既有警告／worker1shadow保留，原1023 boot参数与回程保持。候选1c0cac97，
sessionb442d7babe00bddf，floor1738713600／0／3；未实机，不能断言省电状态是WMI根因。
[机制与复现](../drivers/EldenWifi/MHI-WAKE-LEASE.md)／[证据](evidence/wifi-mhi-lease-20261120.json)。
下一步只做一次这个有价值的对照，完整Goal active，继续集中Wi-Fi。

2026-11-20合并修复实机：网络桥确实在station-stage4、真实站点MAC匹配后启动；
新WMI步长对象已运行，但仍30次超时、BSS0，不能认定它为原WMI原因。net drain0、真实
DMA fence／MSI4／PERST低／WLAN停止与完整stock/root/green/原设置恢复通过；恢复初期
2次radio错误保留、4次观察最终一致。日志285911B、drop最大14、无重连；缺失记录不视作成功。
[实机证据](evidence/wifi-station-stride-hardware-20261120.json)。保持两项有效修复，集中推进
WMI真实完成链；不再重复接口／发布顺序／主固件哈希测试。完整Goal仍active未完成。

2026-11-20合并修复候选：网络桥按Sheng实际stage4和真实站点快照启动，纠正先前stage2
提前发布；桥59项模型通过。四代Linux已有的MAC/PHY全结构体分配步长修复已移植，
70个实际旧新callback场景通过；尚未观测本机短TLV，不能断言它导致WMI阻塞。
一个WMI对象＋124保留、两原生组件、full kernel与签包通过，632／1既有警告保留。
候选c9c33f92、session5e076ea0aa1dd9cf、floor1738713600／0／3，未上机。
[证据与下一轮](evidence/wifi-station-stride-20261120.json)。完整Goal active，继续集中Wi-Fi。

2026-11-19网络桥实机通过：en0发布、IONetworkStack被系统打开、Apple80211请求到达；
回程net drain0及真实DMA fence／MSI4／PERST低／WLAN停止通过，完整恢复stock Android/root/
green/原充电／无线／扫描设置并熄屏。捕获282598B、64状态样本、drop最大0、无重连，断开
后计数未知。仍30次WMI16387超时、扫描准入未开、BSS0，关联/DHCP/流量未通过。
原厂启动路径与六份主固件SHA也已实读：与候选全同，没有证据换bdwlan/regdb或m3。
[本轮实证](evidence/wifi-network17-hardware-20261119.json)。下一步只推进首次WMI完成链，
不再重复接口／回程-only测试。充电候选暂存，Wi-Fi优先，完整Goal仍active未完成。

2026-11-19按用户要求集中Wi-Fi：补齐此前缺少的真实BSD／IOKit网络桥，优先复用Sheng
同21H461已实机WPA2／DHCP／流量版本08cde20e。54项实际生成代码ASan/UBSan模型检查通过；
网络桥／原生线程／完整内核／签名boot通过，编译0／1旧shadow警告。停止后关闭请求并有界
等待已接纳回调，原有DMA fence与物理回程保留。候选7fae1095、sessionedf7cfeebe4b2c89，
floor1738713600／0／3；6GiB不变。CE/WMI及固件保持，首次超时仍未解决，不能宣称扫描联网。
[源码及复现](../drivers/EldenWifi/net/README.md)／[证据](evidence/wifi-network17-20261119.json)。
下一步一次联合接口／扫描／回程实测；充电候选已签但暂不实测，主目标active未完成。

2026-11-19充电断链修复：旧v140在SET28=0已排队、但旁路完成前断链时会漏清手动禁止充电。
新独立策略保存“可能已禁止”的事实，只有有效SET28=1成功ACK才清除；已知未入队发送失败则
回退。实际旧24／新30重连场景、18窗口场景、146检查和ASan/UBSan通过；固件行为仍是模型。
两件原生对象均绑定同一新增状态头、完整内核通过；8项打包资格测试及实际导入／导出／30个
Apple执行区／入口7124／菜单ADT信任审查通过，编译0警告、原有链接10警告保留。
[复现入口](../profiles/charge-link-recovery/README.md)及[证据](evidence/charge-link-recovery-20261119.json)。
这轮未打包、刷写或实机验证，新空输出完整boot命令未跑；双口净充／真实旁路／完整阈值周期／
睡眠和持久设置仍未完成，完整Goal保持active。下一步独立充电候选资格与一次有判定价值的验收。

2026-11-19充电证据复核：四份既有日志及stock恢复摘要一致。低背光短窗口
中位+190mA与默认GUI尾样本−177.5mA均保留；完整双口供电／保护周期／旁路／睡眠／
持久设置仍未验收。[当前验收表](CHARGING-ACCEPTANCE-REVIEW-20261119.md)列明范围。
这轮只整理历史证据，未新增设备操作或驱动修改，完整Goal仍未完成。

2026-11-19：主线已核对离线外设与GPU交付，四个归档的1004项内容摘要一致；
笔／RTC／触感broker已有离线链接证据，双击／运动／相机仍缺真实原生链路与硬件验收。
这轮只整理交付和接入条件，未合并、编译或访问平板；触感校准及目录仍为空，输出关闭，
GPU继续最后。参考清单补齐两个已有Apple克隆，68仓与清单一一对应，冻结输入保留。
[接入清单与证据](PERIPHERAL-DELIVERY-REVIEW-20261119.md)。完整外设Goal仍未完成。
此前受内容过滤限制的操作没有重试。

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

**v173已完成平台回程实机验证**：BM实读关闭、事务已采样为空闲、MSI停止、PERST低和WLAN停机均通过，
随后完整恢复Android。MHI暖复位仍未验证，不能混称。下一步接入真实supplicant/launchd/trust、IOKit网络桥
及本机MAC输入，推进实际扫描和连接；不再重复仅验证回程的冒烟。充电与完整外设Goal仍未完成。
[当前基线](../profiles/wifi-platform-fence/README.md)。下方为各历史版本记录。

v172的上游平台回调已返回，解绑和配置结果为0；但MHI RESET仍置位、状态ff04，现有协议复位
检查拒绝通过。下一步使用独立的主机DMA停稳与PERST物理复位证明，保留MHI异常，绝不把ff04当READY。
需要实读BM关闭/事务排空/MSI停稳/PERST低后才能释放电源；平板本轮已完整恢复Android。
[当前证据](../profiles/wifi-platform-budget/README.md)。

v170确认MODE_OFF入队成功，但未见MHI发送完成/接收应答，中断仍使能。下一步对接Linux平台
重启专用的PCI `shutdown` 回调，保留真实MHI复位、bus-master关闭、事务/IRQ排空和PERST检查。
不把卸载路径的MODE_OFF等待当作平台重启的必经步骤；也不伪造应答。设备已完整恢复Android。
[具体源代码依据与约束](WIFI-PLATFORM-SHUTDOWN.md)。

v169已定位到 `ath12k_qmi_firmware_stop()` 的MODE_OFF事务。前面的工作队列/PCI/核心清理均已返回，
调度循环在等待期间仍返回。QMI/MHI队列已经标记为IO完成类，不应重复改flag。下一步核对该请求
的TX完成、RX及MSI状态；不延长9秒回程掩盖问题。设备已完整恢复Android，仍未联网。
[本轮定位证据](../profiles/wifi-stop-trace/README.md)。

**v168更新**：有界清理准入已实机通过，stage4保持，原QMI−12未再记录；但不能据此说关闭成功。
`nw_wifi_stop`仍未在9秒窗口内返回，继续通过平台复位恢复Android。下一轮统一标记停止子调用并
采样现成`nw_wifi_where`，定位具体等待，不延长超时；之后再接supplicant。下方v167为历史。

**v167当前优先级**：QDSS已修，实机FW_INIT_DONE/stage4通过；但停机QMI mode-off=-12，
9秒WCN等待到期后靠平台复位恢复Android。先修复同owner停机期的DMA/电源准入和真实排空，
再安装现成supplicant服务/网络接口。scan=0只是入队，BSS0；不得说已扫描联网。
[实机记录与限制](../profiles/wifi-qdss-config/README.md)。下方均为对应版本历史。

**v166实机进展**：控制socket修复生效，DMA/MSI/MHI/QRTR/QMI已实际工作，原厂AUX_UC成功。
当前精确阻塞为未映射QDSS配置；下一轮补原厂6237B文件映射及摘要核验，不再重复初始化探针。
真MHI复位与全SHA恢复Android已通过，尚未扫描/联网。下方v165/v164保留历史。

当前 v165 已定位：未安装控制socket transport，导致实际 `nl80211_init` 返回-16。
真实Sheng控制通道已完成组件/整核，下一步一次完整签包和实机验证，观察MHI真实进展。
[控制通道方案与复现](../profiles/wifi-control-transport/README.md)。下方v164记录为历史基线。

[v164完整运行栈首轮实机](../profiles/wifi-mhi-runtime/README.md)已通过控制路径及原厂固件校验，
但Linux初始化stage0返回-16，未启master/上传固件。已完整恢复Android；下一步定位具体初始化调用，不重测已通过项。

目标仍是如官方 Sheng 一样基本可用的 iPadOS 平板：基本外设、正常交互、可靠供电与
恢复均需实机验收。GPU 最后；音频启用前先讨论衰减与保护。完整 Goal 尚未完成。
本计划依据[组织复用审核](UNIXNU-ORG-REUSE-AUDIT-20261115.md)更新，历史逐轮记录已
[原样归档](archive/plan-before-org-reuse-20261115.md)，当前状态以本页和各子系统证据为准。

## 当前主线：先补电源验收，再接通 Wi-Fi

用户更新Goal后，电源优先级保持在无线之前，GPU由隔壁独立离线构建、主线最后集成。
UFS本轮收尾后，先用已有记录区分高SOC停充/滞回、真实输入预算及稳定净供电，不能把
99%时的−36mA直接当充电驱动故障或省电收益。下一个电源窗口应一次回答原厂模式下
实际净电流、保护阈值跨越/续充与恢复；重复高SOC停充、已否定的DC写口和无支持协议的
选口命令不再试。完整周期必须等真实SOC跨阈值，设置持久化依赖持久Data，不能伪造完成。
受这些前置条件限制时继续有用的离线接口工作，不用重复探针填时间，也不擅自改Goal状态。

v157已完成[PCIe根链路实机验收](../profiles/pcie-root-trial/HARDWARE.md)：Gen3 ×2、
root17cb:011c/endpoint17cb:110e、127项PHY写入、GCC释放通过。端点IO/MEM/BM保持关闭。
WLAN/NoC原生提供者与worker已实跑，128对象QMI链接仍属离线结果，未加载Wi-Fi完整运行栈。
同步回程/完整stock SHA/Android/root/green及原充电/无线/扫描设置恢复通过。
显式full-on是诊断预算，不是日用省电策略。历史步骤见各组件文档和Git记录。

接下来的顺序固定为：

1. 已完成：v158按本机窗口实测BAR/映射、Peach major2及原生epoch确认，完整恢复Android。
2. 确立SMMU/DMA内存所有权和MSI路由，补真实排空与停止，再允许端点bus-master。
3. 接入已编译的MHI/Peach/QMI栈和真实WLAN consumer，验证固件/扫描/关联/联网。

第一项的[完整v158证据](../profiles/pcie-endpoint-trial/README.md)包括原生worker30场景、
整核/签包和真实40210200/major2、BAR0/2、禁BM、同步回程。采用stock更窄61MiB窗口。
下一步执行第二项，MHI启动前必须有真实DMA所有权和排空；不重复已通过的身份诊断。

第二项的[SMMU映射已在v163实机通过](../profiles/smmu-prefault-memory/README.md)：
专有128MiB NC映射、66页表/32768叶、bank7/slot8/ASID1、真实context/故障IRQ及触控DMA共存通过。
前几轮确认IOPL段边界、IOKit静态映射重用和缺少prefault，修复保留所有逐页物理/cache检查。
ATOSNS明确不支持硬件ATOS；当前通过的是实际寄存器回读和完整物理页表遍历。
端点command2仍禁bus-master，尚无Wi-Fi设备DMA。下一步接自有arena/运行回调、MSI所有权和
真实排空，再允许MHI/Peach/QMI使用；不重复选择/映射-only诊断。完整stock Android及设置已恢复。

不重复v157/v158诊断，也不复制其它设备未保留的低地址DMA内存。power_ready/CPR/QMI仍必须
核对当前确认代际，不能沿用历史实机结果。更详细的边界见[原生worker](../drivers/EldenPcie/NATIVE.md)。

v156已经补齐一项可执行电源缺口：[UFS自动Hibern8](../profiles/ufs-idle-trial/README.md)。
32次真实空闲进入/退出、数据验证与配置恢复通过，并恢复Android；5000µs取自本机原厂。
这不能替代整机净充/完整窗口循环，且有约0.8–1.0ms唤醒读取成本。下一步继续按真实SOC/
输入条件关闭充电验收缺口，后续候选去掉该诊断循环，不重复同项功能冒烟。

v148已完成有界调速的整核/签包/实机闭环：90秒、191次调频确认、一次原档位恢复，
SCMI和控制错误为0；随后全SHA恢复Android。显示拷贝中位约134ms，与v146相当。
但当前电流样本仍净放电，负载阶段不同，未证明省电收益，不提升为日用省电默认配置。
实指交互、活动调速中的RPC停止、高档位及持续运行仍需后续证据，不能由这一轮代替。

v149已完成17版介质属性闭环：RAM与两个UFS窗口属性读回成功，BSD单元0/2/4全部从
isssd0变为1，随后正常恢复Android。吞吐/尾延迟和省电收益尚未测得，单槽轮询未改变。
当时提出的UFS差量已在v152/v155/v156推进，详见下文。不重复介质属性/CPU查询，
不继续盲调频率参数。按下节检查同负载吞吐、尾延迟和CPU占用，把充电改善作为实测目标。

v150已补齐内核UFS入口保护：正常路径提前ARM、就绪后由原SMP线程ADOPT；受控停在UFS前、
屏蔽IRQ/FIQ并停止喂狗后，在软件120秒后备之前返回可响应fastboot。两轮均恢复Android。
它不覆盖UEFI或更早入核，也不替代DMA/写入/哈希安全检查。后续UFS改动可基于这份正常候选。

v152已完成[IRQ/等待实机闭环](../profiles/ufs-wait-trial/README.md)：完整原像哈希通过，
128条对照/64对数据哈希一致，实际128次IRQ/5次睡眠唤醒；全会话2114次IRQ唤醒/零等待超时。
root/SMP/同步回程和stock Android恢复通过。单槽暖读时延相近，未证明性能改善；下一步
直接接上游多槽、独立request list和DMA，不重复IRQ探针或盲调200us阈值。当前pinned-root
整表已在受保护RAM中，表页缓存没有可消除的表读取，暂不追加。CPU占用和QD8/32仍未测。

v153的[多槽/PRDT核心](../drivers/EldenUfsQueue/README.md)已完成实际函数host验证及
ARM64/iPadOS17编译：复用固定上游布局与PRDT合并，位图/FIFO加入租约代际、取消、停止和隔离。
v155已完成[真实接入及实机](../profiles/ufs-queue-trial/README.md)：32槽/独立NC请求表、
prepared快照直接DMA、每槽判定和每请求快照均启用；48批/1536条命令/16组等数据哈希通过，
实际未完成门铃峰值27。固定QD1→8→32顺序的128KiB读数约2430–2837MiB/s，未控制设备缓存，
不当作孤立因果倍率或GUI性能。同步回程/stock恢复通过；v154因缺分配缓存参数回退16槽后
主动拒绝QD32的失败与恢复另存。后续候选保留驱动、移除诊断批读；按上述电源优先级收口后接Wi-Fi真实WLAN接口。
后续压力/Busy状态策略、CPU占用及UI时延需适时验证，不重复这次已通过的基本队列测试。

macOS维护已收尾，标记由整理任务归档移除，构建输入重新核对后才运行了v148。以后若
维护标记重新出现，仍遵守停用对应构建/刷机/同步的规则，不擅自清除其他任务的标记。
首轮调速上限未超过启动档位，固件限频和回程保护保留；更高档位/PSCI idle仍未准入。

## 随后的顺序与验收

| 顺序 | 工作 | 复用方式与必须取得的证据 |
| --- | --- | --- |
| 1 | UFS/RamBlock 固态属性（v149已验） | 17版 IOStorage → DKIOCISSOLIDSTATE 的实际消费及三介质读回已通过，保留该差量；不重复查询，也不把属性通过当吞吐提升 |
| 2 | UFS 传输优化 | 按下节分解队列、完成等待、DMA与认证缓存，保留本机接管/IRQ/SMMU/写门。以同数据集完整哈希、吞吐、尾延迟和CPU占用判断收益 |
| 3 | Wi-Fi 硬件接口 | 接已构建的 Ath12kWifi/Peach：WLAN owner、电源、PCIe/BAR/MSI/DMA/MHI/QRTR。证明固件ready、接口、扫描、关联、DHCP、双向流量与重连；不重写MAC/WPA |
| 4 | 蓝牙原生使用闭环 | 沿已通17版 native/HCI/BLE路径，完成可识别设备、配对和重连；稳定身份/持久Data满足后验掉电保持 |
| 5 | RTC、USB、输入与电源生命周期 | 按真实症状接时钟/唤醒/插拔；触控中断、抬指、熄屏双击唤醒、USB恢复分别验收，保留现有交付修补 |
| 6 | 内存与持久Data | 核 EFI保留区、页表、DMA范围和装载资产所有权，再逐段扩大内存；当前候选6GiB，独立8GiB分支不等于16GiB。持久Data不靠自动格式化或随意改分区实现 |
| 7 | GPU | 按A830合法上电/映射/命令完成，再资源、shader、fence、系统UI。A740寄存器和27版ABI不能整包覆盖17；声音仍需先讨论保护 |

充电验收贯穿此顺序。v144低背光短窗口净充电和v145/v146默认亮度净放电是不同条件，
不能混称已修好。降CPU/存储空耗是可用性的一部分；双口选电、持续净充电、80%及
40–60%完整阈值循环、设置持久化仍须分别证明。若获得明确可实现的原厂双口接口证据，
优先处理；不为重复确认旧事实打断主线。保留 SDP预算、反灌、温控和过压保护。

## UFS 按有用差量验收

审核已按实际 provider/SHA确认当前 NativeUfs/RootQueue/RootCommands 为单槽轮询。
这证明存在代码差距，尚不能把所有卡顿或 CPU1负载归因于UFS。上游完整当前树与撤回
证明见审核证据，不采用已撤回的中间 container 布局。

1. 固定数据集与基线：已知只读块完整哈希、4K/大块、QD1/8/32、p50/p95、CPU占用。
   说明串行实现中哪些队列深度只是上层并发，保留同一根卷、亮度和缓存冷热条件。
2. 核 OS17/调度/IRQ契约，再移植完成等待与多槽队列。IRQ取本机SM8750来源；中断屏蔽、
   禁抢占、早期和panic路径不直接复制睡眠等待。不能把 IODelay 换成 WFE 就算完成。
   改接管/中断前先核这个早期窗口的实际看门狗覆盖；新增Sheng SEC→DXE→EARLY_BOOT
   交接已有70.503秒回程记录，可作为方法参考，但必须匹配本机SDAM/固件/内核。Elden写
   boot_a，不能直接沿用Sheng临时fastboot boot失败后回原安装镜像的假设。
3. 直接 PRDT/DMA 与缓存方向一起核验：地址宽度、非一致性缓存行、request list独立
   映射、bounce回退、并发槽生命周期。设备写回才失效目标数据，不破坏写源缓存。
4. 核当前认证表是否整体驻留，再决定采用页缓存。逐页认证和哈希验证保留，无收益的
   重复缓存不加入。RamBlock seed回收另有loader/XNU所有权前置，不搭车启用。
5. 先完整哈希/故障/超时/恢复，再同负载比较吞吐、尾延迟和CPU。把相关差量合成一次
   有判据的硬件窗口，不同时混入不同功能或未核输入。

## 执行方法与维护

- 每轮只保留一个正在修改的硬件候选，区分上游实现、上游实测、本机消费、本机验收。
  优先成功方法；板级事实优先 ArmadaOS TB322FC → 固定 h0cheung SM8750，其次mainline。
  TB321FU/SM8650不作寄存器或固件来源。
- 复用框架，只改有证据的差量。保留错误返回、超时和停止；测试真实函数/构建输入。
  编译和host测试不代替实机；不以另一份仿写实现自证，也不因同条件重测制造进展。
- 维护目标现为65个独立参考仓；补录已有AdrenoFirmware-a830、linux-firmware-sm8750和
  metal2vulkan-development，原清单指纹不改。最近全量同步65仓：44最新、4快进、12固定fetch、
  3脏树fetch、2既有远端错误。新增主要为文档/更新器整理，无新的本机充电寄存器实现。维护标记解除后
  沿正式脚本自动发现/核Git根，仅快进干净未分叉分支。删除tracking分支的错误单独记录
  并核默认分支，不reset、stash或自动更换冻结候选输入。
- 真机仍须精确 HA2A1PT2/TB322FC、fresh ≥3500mV/soc-ok、stock/reference与GPT身份、
  1738713600/footer0/父链3、boot_a完整回读、session日志和自动回程。不操作Sony，不改
  身份、RPMB/fuse、OTA、分区或根卷内容来绕过驱动问题。
- 生效代码/配置/工具进正式仓并commit/push；原始证据进工作台lab/edl_work，评审进
  lab/reference-reviews，research仅Git克隆。一次性脚本用Windows Temp；退役内容仅回收站。

当前证据和限制见 [CHARGING-STATUS](CHARGING-STATUS.md)、
[CPU调速组件](../drivers/EldenCpuPower/GOVERNOR.md)、[Wi-Fi](WIFI-STATUS.md) 和
[完整组织审核](UNIXNU-ORG-REUSE-AUDIT-20261115.md)。
