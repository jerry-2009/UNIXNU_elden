# 下一阶段顺序

当前v133/134同样停在旧式scan0x200b被拒绝。停止行为猜修，先读取native Supported
Commands byte37、上层cache0x10093e8b0、HCI0x10093c32d/vendor0x10093c32e的实际值，
必要时对照真实0x1002回复。不能凭未打印的后续page rule断言补丁没执行（日志仅前16次）。
读到实值后区分缺能力/缓存覆盖/路由未到，保留v132初始化基线，不全局关闭LC。
新QcomDwc3的MiPPS数据角色交换不等于Y700双口输入选择，须先核原厂拓扑与适用条件。

当前v132已实测原生HCI completion0并发布On，但daemon之后退出；先按准确17版
新栈定位post-On失败，不重测已通过的上电/固件/BlueTool回复。推断slide0x480000
得到0x100107bd4/0x100520250/0x100058904，尚须确认具体错误条件；禁止全局关LC。
下一修订同时保留原stack_ready的failed_starts清零语义，仅真实completion接受时清。
v132原像/日志和v131失败结果已保留；两轮均同步回程、全SHA恢复Android。
充电双口净供电/完整保护周期、Wi-Fi和休眠仍未完成，GPU最后、声音先讨论。

v130已修复跨syscall持有proc_find引用造成的内核panic；真实H4 out26/up25、串口
持续和同步回程恢复。下一步原daemon完成25轮交互后的新退出栈/host-flow初始化；
扫描、配对仍欠，保留真实错误，不关闭全局LC掩盖后续重启拒绝。

11月15日v129已确认助手boot/init的完整回复流程返回0，H4 connect回调也真实返回0。
下步分析connect之后的kernel-control/termios/首包路径；命令流量与配对仍欠。
不再重复助手Ready、缓存、设备树或固件上电测试，不添加未证实需要的睡眠成功绕过。

v128配对的DT/platform-service已实机发布，但停顿未解。marconi警告已定位为正常
名字回退的一部分，不再为消除此警告修改设备身份。下步明确自有BlueTool正在处理
的脚本、决定的结果和XPC回复完成边界；不能仅凭内核bootstrap返回0判断回复成功。
已有等待栈采样默认120s太晚，不能原样启用后再空等一轮。

v127的BlueTool缓存挂载已实机通过，后续停顿仍在；同像纯接收对照排除周期状态
查询为必要条件。下一步回到准确17版XPC完成/传输启动静态路径；先校核已有观察
接口，不继续向内核盲加探针，也不调整已验证的WCN固件/电源。

当前转向BlueTool完整运行配置：v126未在USB中断前得到socket记录；原job确认仍缺
sheng四项lifecycle覆盖。先将已签缓存/签名/新信任项整合进合格RAM只读union和
从零构建链，参见BLUETOOL-LIFECYCLE.md。之后再判断是否需要更细syscall探针。

v125已完成bootstrap两次Ready/result0证据；下步沿原21H461的socket→CTLIOCGINFO→
connect检查进入/返回，H4回调在USB断点前未观察到。保留自动复位和完整stock恢复；
不将v124/v125诊断件升级为可用无线基线。

v124更新：已捕获准确BlueTool的e6例外接受，随后USB写超时，自动恢复Android完成。
下一发只定位bootstrap sysctl与native connect/send的进入/返回，不更改固件、电源
或时钟。H4连接仍未观察到；v123与v124均不是无线完成结论，不把日志中断当内核死锁。

当前下一步（v123）：已用官方软件AppleKeyStore越过原21H461 readRootKeys首退，
daemon进入消息循环，但真实UART.SK H4仍client0。先核对准确17版的服务发现、
BlueTool后续状态及control socket打开条件；不重测密钥包装已成功的事实，不跳过
传输错误。Wi-Fi开关仍不可用，随后接实际WLAN电源/PCIe/DMA/MSI/网络回调。
本轮已恢复Android，下一轮重新fresh准入。新功能仍接入build_clean的从零源码链。

11月14日Jerry反馈的从零构建缺口已处理并实际验证：新入口tools/build_clean.py，
GUI/蓝牙两分支均从空输出通过完整签名boot审核，旧目录读取限制抓到的汇编漏点也已修。
文档docs/CLEAN-BUILD.md和profiles/current-build/validation为现行入口/证据；
新像尚未实机回归。下一轮回到蓝牙首次exit1的实际条件诊断，保持现有充电保护与GUI基线。

## 0. 整理和复现归仓已完成

源码到 v91 签名候选已完成独立重建和静态核验；完整外围 Goal 仍未完成。
维护标记若仍存在，先完成提交/回收凭据收尾，期间不刷平板。
参考仓只同步引用，冻结候选不自动换料。旧证据不改写，失效路径通过迁移表解释。

11月13日已恢复无人值守真机授权。官方
[步骤](https://github.com/UniXNU/UniXNU/blob/7d85ede80092050f4d87f72ac7229bb605ce07fb/docs/zh/porting/steps.md)
以平台/存储/显示/输入为依赖起点；本项目按用户要求将充电及基本外设优先、GPU最后，
不直接套用其把GPU排在无线前面的顺序。新官方独立克隆加入清单，现44仓；
逐项审核在工作台lab/reference-reviews。最新ShengUfs最终树与更新前完全相同，
容器布局改动已撤回，不为其构建新的“提速”候选。

## 1. 稳定无 GPU 的实际操作

v109已实测8GiB和软件Settings，保留该候选作为下一阶段基线。剩余内存先评估KVA
压力/加载器可用段与保留区，再选择更大连续窗口或回移上游分散页收编。Home过渡
异常、About耗时、持久Data和完整内存压力仍未验完；不要重复当前三轮已通过的容量/回程。

11月14日v107/v108已定位并补齐原IONetworkStack，完整注册树保持busy0。下一步
保留该组件，择有判定价值的About耗时验证；当前继续内存窗口/页表/保留区审计。
不重复刷写来重证六次已经确认的provider事实，Wi-Fi联网另行接入。

11月13日晚：v106真实手指已打开Settings/General，About延迟后可见。v95 paired-store
已测61.52ms，v104映射缓存/按需诊断与v100触控合成v105后，用户认为滑动明显改善，
但backboardd出现DC ZVA异常；v106只改managed RT DRAM页表属性后重载未再观察到。
最新证据及边界在profiles/v106-rt-memory。先定位IOKit quiescence初始化等待，再扩RAM Data
并推进可用物理内存扩展；无需等所有外设完工，也不把16GiB直接当连续可分配窗口。

以 v91 软件 Settings 成功为控制组。下一轮合并有依据的显示/输入修复，
先对照 sheng 成功实现和现有日志，再选择一轮能改变决策的功能测试：
稳定画面、正确触点、点击 Settings、上滑/退出编辑，以及可用的串口回程。
v92原稿保留。其后续v93/v94已完成映射与软件Settings验证，整屏拷贝中位数
716.65→134.14ms；见FRAMEBUFFER-WC.md。v94继续保留为已验显示/软件输入基线，
不能把采样截图一致或copy提速直接当作实际手势、60fps或长期稳定性验收。
离线输入审计见[INPUT-STATUS.md](INPUT-STATUS.md)：v94软件短按的UIKit组间隔约100ms，
没有重现旧版数秒拉长；坐标/ID暂不改。实指窗口关闭自动注入watcher，
一次完成上滑、Settings短按与滚动释放。v95保留为单独的未验性能候选。
离线故障注入另确认了失败抬指丢失与并发快照覆盖，已完成两组件修复和原生对象核验，
见[EldenHidDelivery](../drivers/EldenHidDelivery/README.md)。[v100](../profiles/v100-hid-delivery/README.md)
已完成独立完整候选签核，仅替换两个触控对象；静态通过不等于实指通过。
实指窗口用v100做一次上述功能验证；若需回归对照再用v94，不默认重复两轮。

v100软件上滑/Settings与同步RPC回程已于11月13日通过。抓帧工具上限已跟随内核改为12，
并保留逐行/CRC/会话/断点保护；不再为同一软件基线重复刷写。实指仍待人在场。

CPU 同时记录实际上线、调度/IRQ 与负载，UFS 记录真实 I/O 延迟和吞吐。
吐日志慢不直接等同存储慢；开启所有核也不能替代阻塞定位。
优先复用 sheng 已验证的 UFS 方法，板级参数按 TB322FC 的 ArmadaOS/Linux 对版。

## 2. 完成基本外设

v118/v119已经完成原身份页面规则整合和自动真机回程：HCI保持ready，旧空对象fault
未再记录。首个bluetoothd主动exit1，后续LC拒绝，尚无client。下一步准确诊断其
listeners/daemon startup失败的实际状态/文本，再选最小修复；不要先全局跳过LC。
用户分享触控清单已对照，无新修改依据，保持v106/v109已验交互链路。

最新17用户态工作已到[离线路由组件](../drivers/EldenBluetooth/userland/NATIVE17.md)：
124指令场景/两ASLR和保留127entitlement的签名过，但尚未集成运行。
已按用户线索补全sheng历史：17旧版可供对应外设参考，公开蓝牙适配首次即27。
下一步将精确17改动接入原身份页面保护/运行时包，保留真实HCI和现有回程，
验证daemon连接与标准命令；能力、可选命令、key与扫描配对分阶段实证。

v117已实机跨过完整HCI初始化并发布H4 host，下一项是准确21H461 bluetoothd用户态。
目前12次fault均为file offset0x2f2fc0、FAR0x2a8：单例机型对象未构造，尚无client连接。
先核原厂二进制的factory/constructor与标准HCI注册，再依sheng的已成功type0方法适配，
保持真实BlueTool、原状态/能力报告；不能用空返回或假能力跳过初始化。
本阶段无需再做相同固件下载冒烟。见profiles/v115-ibs-wake至v117-hci-debug。
8GiB GUI分支独立保留；触控已实指打开设置，不因蓝牙推进而重置已有验收。

最新v111已完成SPMI共用锁整核与真机：54次ADC读取、温控武装与WCN电源通过。
v112的GIC地址笔误已撤回，v113按DTS修正并启用GENI FIFO路由，外围固件/激活完成一次。
已捕获真正HCI版本包，v114修正长度字节12被误拒绝；host通过但本轮又停最初IBS唤醒。
下一步查同板Linux qca_port_reopen/原厂冷启动同步和接收状态，不能把一次成功当稳定，
不重复同像碰运气。蓝牙独立6GiB分支保持，v1098GiB可用GUI基线仍在。

11月14日：先整合EldenSpmi共用bus0/EE0事务锁，替换PMIC Spmi.o、BT BtPmic.o/
WcnPowerNative.o并只链接一份TransactionGate。真实函数并发/错误测试及ARM64组件
完成，整核与实机未做。两轮v110都在SPMI0x9和ADC失败处停住，不能继续重复FIFO测试
或跳过温控。保留已验证的v1098GiB GUI候选；蓝牙分支稳定后再合并。

充电继续保留已验电池、UCSI、温控和回程，剩余 500mA/双口问题使用有明确结论的功能对照，
不再反复扫描已否定的 GLINK 写路径。旁路、80% 上限和保护窗不能因基本充电通过而省略。
现行电源验收和v96电池界面候选见[CHARGING-STATUS.md](CHARGING-STATUS.md)。
v96只恢复既有UI发布器，已实测真实96%状态栏及净放电标志；双口输入仲裁仍需原厂证据，不把它当快充修复。

Wi-Fi、蓝牙以 sheng 成功驱动规范为先，具体接线、时钟、复位、寄存器采用本机源码与实测。
Wi-Fi现状和下一步见[WIFI-STATUS.md](WIFI-STATUS.md)：原认证服务已适配arm64/iOS17并离线签名，
未安装/联网；本机Linux已有独立Peach配置，不能照搬未实测的整片QCC2072映射。
Peach要求固件OL-CPR处理先于TME-Lite；已将新适配统一到已有WcnPower规划/发送代码，
但发送器当前只有BT owner资格，Wi-Fi QMI→原生WLAN owner路由仍缺，不得用假成功或BT上电流程替代。
9文件Peach差异已回移到官方锁定的Linux7.0.14，6个变化C单元及输入/流程检查通过，
见[回移说明](../drivers/EldenWifi/peach/README.md)。完整OS适配和125对象构建已通过，
见[运行时说明](../drivers/EldenWifi/RUNTIME.md)；下一步审核保留警告并接入真实WLAN owner、
PCIe/DMA/MHI与网络回调，再做整核集成。对象/host通过或0x53非致命例外均不能当作已联网。
MHI错误读取误报下载成功已修复并完成125对象重建，见[MHI记录](../drivers/EldenWifi/peach/MHI-STATUS-READ.md)。
其余类型/未初始化警告与板级回调仍待处理，避免为消除警告直接设置掩盖错误的默认值。
蓝牙常驻模式已补离线停止接口与上行背压退出，见[WCN-SHUTDOWN.md](WCN-SHUTDOWN.md)；
v97已完成整核/恢复钩子的静态资格，见[构建档](../profiles/v97-wcn/README.md)，尚未entry转换/签包。
随后仍需真实WCN/HCI及daemon验证。现有候选不自动换料。
v98已离线构建只读HCI/主机状态接口和arm64/iOS17 BlueTool服务，原21H461 XPC协议及地址格式已核。
下一步补齐签名runtime/launchd合并与准确版本的transport/chipset适配；不直接套用27版arm64e补丁。
v99已完成最小runtime签包：保留原561任务/缓存，只挂载BlueTool，并按原签名绑定普通流分支。
详见[候选档](../profiles/v99-bt-runtime/README.md)。入口地址变化已按相同start.s对象核验。
该候选会尝试真实上电WCN。11月13日首测runtime准备成功，但在父时钟检查处停止，
尚未进入UART/HCI；已正常同步回程和恢复Android。[父时钟修正](WCN-PARENT-CLOCK.md)
按ArmadaOS固定的四代SM8750源通过host/native检查，v101完整候选实测已越过该门，
六路rail和power stage6通过；v102还曾完成外围patch/NVM/TME-L/activation，
在普通HCI版本检查stage16返回−19。v103按四代Linux修正SPMI的DONE判据并保留
版本应答诊断，但该轮停在初次IBS唤醒stage2。启动重复性和真实版本仍待解决。
同步回程和stock恢复通过，仍无HCI身份/配对验收；
不将三代TB321FU/SM8650的寄存器或固件带入，不把静态通过当蓝牙可用。
触控稳定后加入休眠/唤醒及双击亮屏，随后推进持久 Data、容量/内存、时间和日常应用稳定性。

## 3. 高风险和后续功能

扬声器启用前先讨论衰减和保护；GPU 最后。
KShimC + UniXNU + Android/recovery/fastboot 多入口路线保留，不能覆盖现有安全回程。

每轮只选一个明确功能目标；复用有效冻结证据、合并已明确修复。
必须保留 fresh 电量、目标身份、签名 floor、完整 SHA 与自动回程检查。
一次成功只覆盖该次工况，不代表全部外设或长期 Goal 已完成。
