# 当前状态 · 2026-11-16

v158已经在真机读到Peach40210200/major2，BAR0/2尺寸与映射、禁BM和原生身份确认均通过。
同步回程及完整stock/Android/充电无线设置恢复通过；日志drop21，必需记录齐，不冒称完整无丢字。
[本轮完整证据](../profiles/pcie-endpoint-trial/README.md)。下一步SMMU/DMA/MSI与MHI；Wi-Fi尚未联网。

v157 PCIe根链路已实机通过：Gen3 ×2、正确root/endpoint、127项PHY写入及禁DMA状态。
同步返回fastboot并完整恢复Android和原设置。[结果与边界](../profiles/pcie-root-trial/HARDWARE.md)。
Wi-Fi下一步是BAR/芯片major确认、SMMU/DMA/MSI和MHI；目前仍不能联网。
当前设备为最后已恢复的stock，所有本轮设备任务结束；再次访问前须重新读取电量与状态。

v156已实机接通UFS自动Hibern8：原厂5000µs策略、32次硬件进入/退出和空闲后数据校验均通过，
原控制配置/同步回程/stock Android恢复通过。唤醒读取约0.8–1.0ms，整机省电及完整充电仍未验收。
[当前电源功能证据](../profiles/ufs-idle-trial/README.md)。

v155已完成32槽UFS/直接DMA实机：独立请求表读写PAR属性44，48批/1536条命令等数据校验齐，
硬件未完成门铃峰值27；root/SMP/同步回程与全SHA stock Android恢复通过。固定顺序QD32的
128KiB读数2430–2837MiB/s，未控制设备缓存，不能当GUI或孤立性能倍率。末10次高SOC发布电流
中位−36mA，仍不证明净充/省电/完整周期。[完整说明](../profiles/ufs-queue-trial/README.md)。
下一步用此驱动接Wi-Fi硬件回调，后续候选去掉重复诊断批读。GPU工作树保持独立。

当前主线依组织审核推进UFS。v152完整中断等待版已过实机：两原像完整哈希、64对数据/
128条对照、实际IRQ及睡眠唤醒、root/SMP/回程/stock Android恢复通过。单槽时延仍相近，
未证明性能提升；下一步多槽/独立request list/DMA。[推进计划](PLAN.md)与
[完整证据](../profiles/ufs-wait-trial/README.md)说明范围。当前认证表整表驻留，暂不叠缓存。
Wi-Fi尚未可用，蓝牙配对/重连未验完，
日用净充与完整保护周期也未完成；完整Goal保持active。

v145（11月15日）菜单级GUI整合通过：完整复用v144内核/入口/运行资产，只将ebl5改6。
PD与系统背光共存，软件Home进入SpringBoard、四帧CRC/视觉核对通过，原亮度/Android
均恢复。画面仍有占位组件；默认亮度2048尾10样本中位−177.5mA，日用净充尚未完成。
详profiles/pd-gui；没有把软件输入或同核GUI整合当完整实指/充电/图形验收。

v144（11月15日）完成当前组合的9V启动/ICL0暂停/500mA恢复，随后才做背光对照。
半原始亮度码798的九份完整后过渡样本均支持净充电，中位+190mA；原亮度1597两段
均近零。仍非峰值快充/长时/全周期证明。1281918B/drop26，无重连；同步回程和完整
stock/Android设置恢复通过。详profiles/pd-power-trial；普通GUI候选仍v142，Goal未完成。

v143（11月15日）完成原亮度/减半/恢复的45秒分段采样，排除前六周期后10/9/10样本，
电池电流中位−480.5/−212/−368.5mA，仍全部放电；原亮度两段存在负载漂移。
背光及Android均完整恢复。短边PD合同5V3A不代表实际取15W；后续核现有9V启动流程
为何未接入当前配置。日用仍v142，v143是后端试验。Wi-Fi仍未通，蓝牙未完成配对/重连验收。

v142（11月15日）将已验原生背光服务接回v140基线：仅短参数fallback，一对象重编，
原亮度/保护/恢复代码不变；系统请求2048/硬件回读2048，退出恢复1597并释放成功。
1144721B/drop0，同步回程/全SHA恢复stock/Android设置一致并熄屏。手动滑块和净充电未验。
47仓参考同步完成，Sheng仅新增充电源码归属说明，Armada新增方向/触控同步与功耗源码归属；
候选未自动换输入，两个既有远端缺失保留。详profiles/backlight-service及工作台reference-reviews。

v141（11月15日）只读AT检查：SDAM/ADC/DC读写翻译均匹配预期PA，DC为0xc7c1010，
PAR属性一致。无FIFO访问，不能证明总线写可用，旧异常尚未精确定因；第二SID7是GLINK
debug proxy。171487B/drop1，同步回fastboot/全SHA恢复stock及Android设置一致并熄屏。
详profiles/spmi-translation-survey；诊断不是日用默认，后续仍用v140，充电缺口保持。

11月15日补充更正：v140原测试模型把普通/EU窗口标签反置，现已按setter/原字符串确认
普通29优先、续充比例31仅影响EU分支、SOC截断整数；59处核对及新18/原146检查通过。
实际v140两驱动源未变，无新镜像或刷机，原实机交接记录保留。详CHARGING-STATUS.md。

v140（11月15日）修复旁路→自动窗口高SOC时不释放手动停充标志，以及主机用手动停充
模拟窗口上限的问题。27处原厂指令/表检查，旧7/新11场景与原146项ASan/UBSan通过。
两PMIC对象/整核/Apple30/entry/AVB过；一次旁路→80%→旁路→40–60%→原厂实机完成代次1..5。
两次退出均实际SET28=1/ACK，固件仍保持上限停充；原厂窗口/许可恢复。同步回fastboot/
全SHA stock恢复及Android/root/green/boot完成，刷前后设置一致并熄屏。详profiles/charge-window-handoff。
低SOC续充/完整周期、双口净取电仍欠；没有把本轮模式转换当全充电完成。所有本轮设备任务已结束。

v139充电确认层已修复：拒绝过期/旧策略轮次回读，ACK后等待有30秒预算，遥测失效不再
继续标为可用。原实际函数复现缺口，修复及146项正常模式检查通过；冻结6c7fbcb客户端
保留旧DC试验排除，2 PMIC对象重编/Apple30/entry/AVB通过。一次旁路→原厂实机确认通过，
代次0→1→2；完整恢复Android后充电开关和两窗口与刷前一致。双口净取电/完整保护周期
仍未完成；充电文档已整合，旧状态原样归档，不能把验证层修复当全充电验收。

v138（11月15日）通过延后90秒连日志口的实机测试：等待真实IOKit地址57次后，原始
校验通过、HCI初始化0、服务持续连接。2041参数7次/2042启停13次均有对应成功回复，
349条完整扩展广播报告投递到原生套接字，incomplete0/malformed0。不是349台设备，
也尚非界面列表/配对/持久密钥验收。日志299260B/drop47，退出仅在我们请求关机之后，
完整恢复stock/Android并熄屏。v137自定义sysctl等待未读通且独立供电stage1/-19拒绝，
失败证据保留；新路径复用原地址读者已有IOKit API，不放宽电源或身份检查。

v135实读确认能力byte37ff、补丁已执行，发现此前把17版两扫描位角色对应反了。
v136按实际发送器纠正为32e标准扩展扫描、32d厂商回调；同像有效复核中client1/ready1
持续，out110/up916，回程时119/1071，未记录原200b/c拒绝。唯一观察到的BT退出在我们
RPC ACK/driver withdrawal之后，为SIGKILL9。仍未验附近设备记录/配对，2007可选拒绝保留。
首次尝试因COM短暂消失而暴露daemon早于真实地址发布的启动竞态，未运行到扫描，不混记。
两次均同步回程/完整恢复Android；PC有界重试已补，目标端脱离USB启动顺序仍待修。

v133/v134（11月15日）按Sheng标准扩展扫描策略移植准确17版getter/缓存/底层开关，
并在成功HCI完成时重新发布，分别38/40规则，解析器仅扩到40。静态/实际函数测试
及整核/签包通过，但两轮实机仍0x200b/status0xc、out50/up49后退出，不能称扫描已修。
实际能力字节和最终开关尚未抓到；下一步只取这组判定证据，不强开能力或重复猜修。
两轮均同步回程、完整恢复stock/Android并熄屏。47仓同步完成，Sheng属性引用寿命、
官方macOS内存/I/O及QcomDwc3的PD数据角色分支已归档，不自动换候选输入。

v132（11月15日）实机已跨过原生HCI初始化：真实完成回调result0/accepted1，
bluetoothd发布On，H4 out50/up49；随后在另一调用栈退出，扫描/配对仍未通过。
准确17版支持位控制可选0c5b步骤，完整失败/身份/超时保护保留。新4单元整核、
32规则/Apple30/entry/AVB均核验，日志1172960B/drop31无断点；同步回程、完整
stock8b8e72da恢复、Android/root/green/boot完成并熄屏。全部设备任务结束。
下一步定位post-On退出，详profiles/bt-complete17；充电双口/保护周期及Wi-Fi仍欠。

v130（11月15日）已修复明确的内核panic：H4 connect不再把proc_find引用留出系统
调用，改存PID/uniqueid/unit并按回调配平引用。原代码host复现refcount1，新代码
ASan/UBSan、原生构建和实机通过；首次H4 out26/up25，原panic未记录，日志继续，
同步RPC回fastboot及完整stock/Android恢复重新正常。daemon之后另有初始化退出，
尚未stack-ready/配对；下一步按新退出栈查0x0c33/0x0c31附近流程。

BaseCrypto获取缺口已关闭：Microsoft mu_crypto_release v1.1.3官方附件重新下载，
ZIP和994件输入全部匹配；新增tools/fetch_basecrypto.py及公开锁，见CLEAN-INPUTS.md。

v129（11月15日）实机首次完整确认：BlueTool的boot/init均完成8阶段、result0，
随后H4 client connected pid79/unit1、connect-result0。仍未证实后续命令流量/配对，
USB之后中断；自动实fastboot/全SHA恢复Android成功，无同步复位证明。下一步定位
连接成功之后的控制路径，不再怀疑已返回成功的boot/init或假放行deepsleep。
实际助手SVC发送器64例通过，整像首次查出旧未消费头替换错误后已修正再包；详profiles/bt-helper-trace。

v128补齐Bluetooth DT节点与platform-service发布，实机确认encoding1/speed8M和双侧
发布成功；之后仍USB停顿，H4未观察到。已自动实fastboot/完整stock/Android恢复。
静态查明marconi-bt警告只是先尝试该名字失败，后续bluetooth地址查询已成功；不能
靠造marconi别名解决。下一步确认自有BlueTool的真实script/result/reply完成，现有
bootstrap Ready/0不等于用户态回复成功。详profiles/bt-registry。Goal仍active。

v127已将BlueTool四字段缓存、签名和新信任项完整接入。实机两轮cache stage5/status0，
925323B完整回读和runtime prepared1；之后仍停顿。第一轮114763B/drop23后写查询超时；
同像纯接收对照110710B后也不再增长，监听器保持到设备复位，说明PC周期查询不是
必要触发条件。两轮自动实fastboot/全SHA恢复stock、Android/root/green通过，无同步
回程证明，已熄屏。仍不能称H4连通或判定内核死锁。下步静态核对XPC完成/native17
启动路径，避免更多盲目内核探针；sysent97/98/54已核实指向正确函数。

v126仍只捕获bootstrap两次Ready/0，socket/ioctl/connect记录未到USB断点前出现。
110923B/drop0后Write timeout，自动fastboot/完整stock恢复成功，非同步RPC证明。
已转向补齐实际运行配置：原BlueTool仍为mobile/pressed-exit，缺少sheng的四项
lifecycle覆盖。新925323B缓存已签名、宿主XPC解析和560其他任务/原信任模块核验
通过，尚未挂载、未装入boot。下一步先整合此缓存，避免继续更细的无结果探针。
详docs/BLUETOOL-LIFECYCLE.md；设备当前Android/root/green，已熄屏，全部任务结束。

v125阶段日志确认bootstrap两次均返回Ready/result0。之后USB再次写超时，未捕获
H4 connect/send入口；日志109806B/drop7且有断点，不能将缺失记录当回调绝未执行。
自动回实fastboot、完整stock恢复及Android/root/green通过，复位原因无同步证据。
下步原21H461 socket/CTLIOCGINFO/connect入口与返回；不回头改已验固件上电。
新增只读观察构建仍从build_clean来源产生，详profiles/bt-transport-trace。

v124进一步核出v123的BlueTool103次启动限制拒绝。按现有IconServices方式，只为
准确CDHash/路径/只读RAM union/已就绪runtime和观察到的e6错误加限定处理；全局
限制保持。实机一次限定放行，但108145B后USB写超时，未证实BlueTool处理XPC或
H4已连接，不能据此断言内核死锁。设备自动回fastboot，复位原因未捕获；完整stock
恢复和Android/root/green通过，已熄屏。候选保留诊断，不提升为默认。下步bootstrap
sysctl与native connect/send的有限阶段记录。详profiles/bluetool-owner-launch。

v123已越过蓝牙首退：软件AppleKeyStore实机wrap/unwrap返回0，原bluetoothd
PID79打印“Server attached, going into msg loop”。本轮1186758B日志/drop0，
未记录原exit或launch-constraint重试；H4端仍client0/ready0，扫描配对未通。
上游密钥算法保留，只在显式mode2的512MiB临时Data启用；当前ADT身份1是fixture，
不代表硬件安全存储或持久密钥。全像28f234da…，typed sync回fastboot和全SHA
恢复stock8b8e72da…通过，最终Android/root/green并请求熄屏，全部设备任务结束。
下一步检查准确21H461发现/打开com.apple.uart.sk.bluetooth的路径。Wi-Fi仍缺
真实WLAN/PCIe/DMA/MSI/网络接入，用户确认Off无法开启。完整Goal保持active。
详profiles/elden-software-keystore与drivers/EldenKeyStore/README.md。

源码复现修复：`build_clean.py --variant gui|bluetooth` 已分别从新克隆/空输出生成
完整签名boot并通过审核，不再要求旧v99/旧对象或工作台路径；原始系统、固件、
Crypto与签名材料仍需按清单提供，原生构建宿主为macOS。GUI新像df0480ac…、
蓝牙新像96b0fd19…均未刷，不能用静态重建扩大实机结论。详见CLEAN-BUILD.md。

最新v118/v119已实机：真实HCI初始化保持成功，原机型空对象fault未再记录。
但bluetoothd首进程主动exit1，后续11次启动约束拒绝，H4 client仍0；扫描配对未通。
v119仅增加原身份限定退出日志，未改安全策略；下一步定位首退的listeners/startup真实错误。
日志分别1168878B/drop4、1159506B/drop108，均typed sync/fastboot/全SHA恢复Android。
所有本轮任务终止；细节在profiles/v118-native17与v119-bt-exit。
用户分享触控HID清单已与现有独立Digitizer/edge-tip/抬指链路对照，本轮不改触控。

最新[v117](../profiles/v117-hci-debug/README.md)已实机完成外围固件、普通蓝牙958段、
HCI Reset及身份/版本/地址检查，`hci=0 ready=1 patch=80ab`，真实H4 host已发布。
原21H461 bluetoothd尚未连入，12次在file offset0x2f2fc0/FAR0x2a8崩溃；扫描配对未通。
v115按本机stock HAL实现最多10次/10ms的FD唤醒，v116定位Reset前的保留调试ACL，
v117只过滤完整且长度一致的0x2edc调试帧。所有状态/身份/超时检查保留。
最后日志1164295B/drop25，typed sync、实际fastboot、全SHA恢复stock通过。
当前Android/root/green/boot_completed，已请求熄屏；所有本轮任务终止。
下一步沿sheng成功路线适配准确iOS17机型对象/标准HCI分支，不搬iOS27偏移。
下方v114是此前失败窗口，8GiB GUI v109继续独立冻结，不混写蓝牙分支的6GiB。

蓝牙独立分支最新v114：SPMI总线串行化已实机跨过ADC/WCN同时失败，v113曾完成外围
固件/激活并收到真实HCI版本包；v114已修长度字段检查，但初次唤醒仍不稳定，尚未联网/配对。
v112有GIC地址笔误已撤回；各像均已恢复stock Android，当前未运行设备任务。

最新[v109](../profiles/v109-memory8/README.md)已实际启动8GiB窗口，八核保持onlineff。
软件上滑和点击得到有内容的Settings/General采样图（CRC b92cfd0a）。最后日志6089821B/
drop10，Home过渡重复列和widget占位仍在，不宣称动画完善。三轮均同步回程、完整恢复
stock Android并熄屏。16GB最大利用、About耗时、逐页压力/长时稳定性仍待继续。
下方6GiB及v106表述为此前基线，最新容量以v109记录为准。

最新无人值守v108补齐同版原IONetworkingFamily，六次实机检查证实IONetworkStack存在、
IOKit busy0。About实际耗时尚未复测，不把服务注册当联网成功；见[诊断](NETWORK-INITIALIZATION.md)。
日志1475520B/drop36，同步RPC及完整stock恢复通过，设备已回Android并请求熄屏。

最新实机为[v106](../profiles/v106-rt-memory/README.md)：真实手指能上滑、打开Settings和General，
About在较长网络初始化等待后也能打开。v105引入映射缓存后滑动明显改善，但点击会使backboardd
在DC ZVA处重载；v106按上游RT内存策略限定修正managed DRAM后，本轮未再记录该异常。
两发分别drop24/28，均同步回fastboot并完整SHA恢复Android。整屏copy约60ms，仍非流畅度终验。
CPU八核上线，内存仍6GiB；充电双口/净充电、无线、休眠和持久Data仍未完成。
以下v100记录是历史基线，不能当作最新完整功能范围。

最新软件交互已验为 **v100**（继承v94显示/v91功能）：iPadOS 17.7.11 (21H461) 在 Y700 Gen4 / TB322FC 上进入
SpringBoard，通过一次软件上滑、一次短按 Settings，收到实际渲染的 Settings/General 页面。
这证明该软件输入路径可用，尚不能宣布真实手指操作或日用性能验收。

11月13日无人值守两项功能闭环已完成：v100保持相同Settings采样像素，v96首次
发布真实电池并在状态栏显示96%。两轮均捕获同步RPC回fastboot并完整SHA恢复Android。
v96是独立v94电池菜单候选，不含v100触控修复；当时末10轮净电流中位−413.5mA，
仍为放电。日志分别drop50/28，不能算充电全部完成或全程无丢日志。
详情见[v100记录](../profiles/v100-hid-delivery/hardware-result.json)和
[电池记录](evidence/v96-battery-live-20261113.json)。

| 项目 | 已有证据 | 尚未完成 |
| --- | --- | --- |
| 根卷与用户态 | UFS 上的 iPadOS 根卷、RAM Data、launchd、SpringBoard、Settings | 持久 Data、完整应用场景 |
| USB 调试与回程 | 内核日志、帧回读、会话绑定 RPC、panic 后定时定向 fastboot | 断线及供电变化下的完整长期稳定性 |
| CPU | v94准入online/work/timers/ipis均ff，八核实际参与检查 | 持续在线/负载、DVFS与长期稳定性仍待实测 |
| 显示与输入 | GOP CPU 显示、软件上滑/短按、触点/HID 链已推进 | 真实手指准确操作、流畅性和鬼触排除 |
| 电源 | 真实96%状态栏、电池状态、背光、原厂 ADSP/GLINK、UCSI 事件及 PD 流程已有实测 | 双口共享500mA与净充电、完整快充/回退/保护工况 |
| Wi-Fi / 蓝牙 | 板级资源、固件、Wi-Fi认证服务及蓝牙v99候选已离线准备 | 硬件链、联网、配对和持续使用验收 |
| GPU / 音频 | 参考实现和板级调查保留 | GPU 最后；扬声器先讨论衰减与保护 |

v91 的完整日志有 **24 字节 dropped**；对应 Settings 帧 CRC 和所统计的光栅事件保留。
不得把这轮写成全程无丢字节。详细边界与 SHA 在
[`profiles/v91/hardware-baseline.json`](../profiles/v91/hardware-baseline.json)。

v92 仅为离线 framebuffer 映射实验，尚未完成签名、资格与实机验证。
当前设备已恢复 stock Android。本轮整理、源码重建和编译均未访问平板。

## 冻结指纹

- v91 boot：`879ef26b2f438bc63856769deee0d1b0790d51a55b30bcc57f5fb92d34ca746f`
- v91 kernel：`2d72dea2e1b69adf063a9db2b91b06cb16e1bc880425a868f62f6611989efe69`
- v91 owned dylib：`f748e9cf601db43167eaf7736b0a161771b8c01eeb46860820604ccf892ac034`
- stock boot：`8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890`

Boot rollback floor 始终为 **1738713600 / footer location 0**，父链 location 3。
写入前核对目标、fresh 电量准入和完整镜像；写后完整 SHA 读回。
本文不是其他设备的刷写授权或通用刷写指南。

## 源码重建实机验证

2026-11-12：修复新 Data 种子被 macOS 所有者映射掩盖的99:99→501:20差异后，
全源码候选 `211b084ba1f04cfb4235e2626c8e2ee4a7d9288b96797c61743aa7282b021d40`
已自动上滑、短按打开有内容的 Settings。CRC `3bd2f297` 与原v91画面一致。
本轮日志5007472B、drop17；会话绑定RPC的RESET_AFTER_SYNC已捕获，随后实见fastboot，
并完整SHA恢复stock Android。旧4866…仅静态通过、实机停启动图，已经撤回。
原Data单变量对照1959…也通过Settings，因而没有借此更改内核或供电控制。

生成器与打包器现在都读取原始APFS inode验证233项所有者，不能再只依赖stat视图。
详见 `DATA-SEED-OWNERSHIP.md` 和 `profiles/v91/validation/source-rebuilt-hardware.json`。
这是一次软件交互验收；该轮约0.7秒整屏拷贝后来由v94优化，物理触控、持久Data及其余外设继续按PLAN。

## 后续显示映射优化

v94通过帧缓冲全部5653页读写翻译检查，17次整屏copy中位数为134.14ms，
对照716.65ms，约5.34倍。采样Settings截图CRC3bd2f297与原图一致；不是全分辨率
像素校验或整体FPS。4960298B日志/drop40，会话RPC同步回fastboot和stock全SHA恢复通过。
当前用户要求继续离线，真实手指待方便时再验。详见FRAMEBUFFER-WC.md。

离线v95 paired-store候选已完成469组host验证、ARM64无FP/SIMD与静态打包检查，
未上机、没有进一步提速结论。它继承v94映射及观察规则，保留原copy回退。
当前稳定功能证据仍属于v94，后续按用户离线约束处理。

离线输入复核复用同一v94日志：软件短按间隔101099µs，UIKit两组首条间隔100034µs；
四条hook记录计数完整，但全日志drop40，严格观察仍不完整。控制器7579帧/invalid0，
本轮物理变化0；28次HID成功含软件输入，不当实指成功。坐标转换与固定Linux报文相符，
不新增猜测性输入补丁。详细来源、未验证错误路径和一次实指验收流程见[INPUT-STATUS.md](INPUT-STATUS.md)。

充电核查发现v94只启用合格电池数据供温控使用，状态栏发布器关闭，末段仍净放电。
v96已离线签核：复用完整v94内核/资产，仅以等价参数简写腾出空间并恢复电池UI三项配置，
原XNU解析器420项检查通过，未刷入。它不修复双口功率限制，不替代v94实指基线。
完整电源缺口、候选身份与复现入口见[CHARGING-STATUS.md](CHARGING-STATUS.md)。
