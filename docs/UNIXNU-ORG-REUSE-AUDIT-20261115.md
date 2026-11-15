# UniXNU 全组织复用审核 — Y700 Elden，2026-11-15

已审查 GitHub API 此次可见的 **32 个公开仓库**，包括元组件、板级工程、工具和虚拟平台。16 个已有独立克隆，补齐14个；30个有本地参考，`.github` 与纯QEMU平台 `ArmVirtPlatform` 只读远端文档。research 共61个独立Git根。此次审核不构建、不访问设备、不改变候选输入。

最有价值的差距是 **ShengUfs 的传输优化**，而不是重新实现触控、蓝牙或RAM块设备。当前clean-build映射的 UFS 源码仍是单槽轮询，上游已有多槽/IRQ/直接DMA；UFS和RamBlock还缺固态介质声明。已有组件不等于其最新优化已被消费；未单独clone也不等于过去没用过它。

本报告为源码、差量及集成证据审核，不是32仓所有函数/全部分支的逐行安全审计，也不是新硬件验收。默认分支固定在下表SHA；读取了README、catalog、提交/文件差量，对高优先项继续核对实现和本机消费源码。目录的verified_devices只描述其记录对应范围，不能替代每个最新提交的验收说明。

## 1. 可执行顺序与验收边界

| 顺序 | 工作 | 已有作业/具体入口 | 最小有价值的验收 |
| --- | --- | --- | --- |
| 1 | 完成本轮正在推进的负载调速，不另起重复CPU实现 | Sheng `package/CpuFreqProbe.cpp` 的最忙核负载、上快下慢、触控boost/帧floor方法；现有Elden v147草稿已经采用同SoC Pagani策略+本机SCMI | 精确LEVEL_SET/GET确认、异常恢复、帧延迟/电流联合窗口；不只查八核online，不全核锁最大 |
| 2 | 先核17版IOStorage消费，再补UFS/RamBlock固态属性 | ShengUfs `2f6c7b0`；RamBlock `8732b3e`，均在start时发布Device Characteristics/Medium Type | 两块介质的IORegistry及DKIOCISSOLIDSTATE/挂载属性证据、固定打开/滚动负载时延；不根据macOS27常数宣称17加速倍率 |
| 3 | 设计一次有吞吐/尾延迟/CPU占用判据的UFS差量移植 | `fd420df`队列/IRQ/PRDT；`34ff541`完成等待；`c1ec2b5`缓存方向；`57f031c`认证表页缓存 | 先已知块完整哈希和故障/超时恢复，再同数据集4K/大块、QD1/8/32、p50/p95及CPU占用；保留写入门和可回程。没有证据不把卡顿全归UFS |
| 4 | 推进Wi-Fi真实板级回调 | 已构建Ath12kWifi+Peach125对象；`nw_abi.h`、本机WCN供电/PCIe/MSI/DMA/MHI/QRTR接口 | 真实固件ready→网络接口→扫描→关联→DHCP→双向流量及重连；不重写现成MAC/WPA逻辑 |
| 5 | 收尾原生蓝牙发现/配对/持久化 | 已用QcaBluetooth方法并做到17版BLE扩展报告；沿现有Native17链 | 可识别的目标设备、明确配对、断连重连；只有持久Data/稳定身份满足才测掉电留存，不把HCI ready当配对成功 |
| 6 | RTC/内存/USB生命周期按实际症状补差量 | ArmDTPlatform板级时钟、DarwinBoot与XNU配对回收、QcomDwc3角色处理 | 消除实际等待并保留服务语义；内存所有权、SMMU和恢复路径各自验证。16GiB要算EFI保留区和页表，不是改一个数字 |
| 7 | GPU最后独立推进 | Adreno740/Metal/PM4/Firmware/AirNir/Smmu构成整条链 | 先A830合法上电/映射/命令完成，后shader/资源/fence/系统UI；A740寄存器不直接抄 |

官方 `docs/porting/steps.md` 第6步建议平台/内存→存储→显示亮度→输入→GPU→Wi-Fi→蓝牙→USB→DSP/音频/电源。这里保留本项目既定的GPU最后、音频另议和无人值守回程约束；已经验过的前置环节不重复冒烟。指南里QEMU建议也不改变本项目“不跑QEMU”的约定。

## 2. 本机源码差距证据

### UFS：确实尚未消费新传输

`profiles/current-build/plan.json` 当前provider指向以下正式归档源码，已重新计算完整SHA并匹配；不是只按历史仓库标签猜测：

| 当前输入 | SHA256 | 观察 |
| --- | --- | --- |
| `profiles/v91/native-build/extra/aaa89ac1f150/NativeUfs.cpp` | `aaa89ac1f1502b55422783b4a7bf5bf01fcba24b35616e938cee3e45201a9955` | UfsHost单共享DMA/lock；RootQueue和RootCommands为单槽轮询路径；无Solid State发布 |
| `profiles/v91/native-build/extra/3a22f86e4324/RootQueue.h` | `3a22f86e432446a3cd7267078c195cfca5b8bb1c2bd55741e67d265de97c6447` | takeover关闭中断；本机MCQ检查、早期等待及UIC恢复不可丢 |
| `profiles/v91/native-build/extra/05dd92a331a2/RootCommands.h` | `05dd92a331a20657b3773278011a913b74cf8c220b98fd3e96aebeea3190d8df` | 本机写门/完成和错误处理所属输入 |
| `profiles/v91/native-build/extra/e2ace3522943/NativeRamBlock.cpp` | `e2ace3522943df38806ef2006525371691beaf0199f971266bd849d4f5253391` | 已有RAM/稀疏Data实现，无固态属性、无PackedRAMDisk释放 |

上游 `NativeUfs.cpp`、`RootCommands.h`、`RootTransportLayout.h`、`CompletionWait.h`、`VerifiedTableCache.h` 需要作为一组阅读：

- **多槽/直接DMA**：最高32槽，分配或寻址限制时降级；独立WC request list避免两个32B UTRD共64B cache line发生陈旧回写。直接PRDT最多64项/1MiB命令，未对齐bounce128KiB。必须重新绑定SM8750真实IRQ、capability、DMA地址宽度和SMMU所有权。
- **完成等待**：先短轮询/WFE，预算默认200µs，之后允许睡眠且照顾待调度线程；不能在中断屏蔽、preemption关闭、早期/崩溃路径照搬睡眠。结合ArmCpu定时器/idle语义，而非简单将IODelay改成WFE。
- **数据缓存方向**：设备写回的数据才失效；不应把写源数据在完成后当作设备写入。保持现有非一致性DMA屏障/整行约束。
- **认证表缓存**：8MiB默认页缓存、逐页认证、压力下预分配；若当前策略已内存驻留完整表，需要先判断收益。哈希验证不删除。
- **恢复约束**：保留Elden的root LUN/GPT/128GiB窗口、Data命令门、SM8750 UIC/MCQ拒绝、USB/SDAM回程与截止时间。用差量组件而不是将上游NativeUfs.cpp覆盖本机文件。

上游固态属性两提交说明的是macOS27.3的观察，并明确“Compiled ... Not run on hardware”。RAM和UFS声明Solid State语义合理，但本机17的调用链/阈值仍需验证。`737f6da` seed回收也明确未实机，依赖XNU `ml_static_mfree_prepare`、`IODTFreeLoaderInfo`及loader内存所有权；不是可单独打开的安全开关。

ShengUfs `b6fe07b...` 的**完整树**等于 `57f031c...`；RamBlock `00a6e5d...` 的**完整树**等于 `737f6da...`。中间APFS container发布已撤回；不能拿中间feature提交当当前推荐布局。比较记录见[当前输入及撤回证明](evidence/unixnu-org-storage-inputs-20261115.json)，工作台亦保留 `source-comparison.json`。

### CPU/平台：方法可复用，控制器不能混用

Sheng的 `CpuFreqProbe.cpp` 提供16ms采样、最忙核而非全簇负载相加、快速升频/延迟降频、触控与帧活动boost。它操作SM8550 EPSS三个CPU域及L3；Elden是SM8750两簇SCMI。当前并行v147组件文档已明确使用Pagani SM8750策略+本机确认/回退状态机，尚未完整内核/实机，不能重复新造同类governor。

`ArmCpu.cpp` 的共享IRQ、IPI/idle和timer统计可为UFS/触控服务；`ArmDTPlatform.cpp` 的RTC等待与board clock注册是另一条独立依赖。Sheng `ShengPlatformPower.cpp` 部分CPU/idle操作主动panic拒绝；有这个类不等于成熟睡眠驱动。DarwinBoot新内存回收也没有本机验收，必须与XNU保留区/页表池配套。

### 充电、触控与笔：避免移植错层

Sheng提供QcomGlink、背光、ThermalLevel、板级时钟和电源服务结构，但没有可直接解决Lenovo双口供电仲裁、旁路及保护周期的一整套驱动。QcomDwc3的数据角色处理也不是双口选电。当前正常亮度仍可能净放电；不要用本报告覆盖既有充电状态结论。

ShengHidInput/`package/HidInputProbe.cpp` 的IOHID链已经复用。最新 `1e3c3ae` digitizer属性retain修补要与本机实际copyProperty路径对照，不应覆盖v100已修好的交付失败/抬指重试。NT36532E矩阵算法不能替换Y700 NT36536点包。AP501U与双马达研究仍是独立能力，组织中没有证据表明存在即用的Y700 Apple Pencil/双SLA0815驱动。

板级事实继续沿 **ArmadaOS-Freedom TB322FC→其固定h0cheung Linux6f97250e→原厂DTS/HAL/实测**。TB321FU是另一代SM8650参考，SM8550 sheng亦只是方法来源；不要因型号相近移植寄存器/固件。

## 3. 全部32仓适用性矩阵

短SHA链接固定到此次审阅提交；完整SHA、catalog pin、OS ABI、现有checkout与源码入口见[机器清单](evidence/unixnu-org-reuse-20261115.json)。`research/`路径相对工作台。没有许可证元数据不代表允许无条件复制，落地时保留对应LICENSE/NOTICE及来源。

| 仓库 / 审阅提交 | 优先级与复用点 | Elden现状及边界 | 本地参考 |
| --- | --- | --- | --- |
| [.github `e4b06b6f`](https://github.com/UniXNU/.github/tree/e4b06b6feecdb51bf9237dd224df443cee33a35a) | **参考**：组织入口和官方文档导航 | 无需内核运行集成；不克隆。仅远端README/元数据 | 远端文档；不克隆 |
| [Adreno740 `54b41b8f`](https://github.com/UniXNU/Adreno740/tree/54b41b8f59e90a167f6f75160739c5f825945fbc) | **后期GPU**：A7xx队列、地址空间隔离、故障恢复、缓存与fence生命周期 | 历史构建已有GPU组件；Elden GUI仍CPU渲染，A830未验收。主线A740/SM8550；不能把A740寄存器或固件直接用于A830 | `research/Adreno740-ipados27` |
| [AdrenoFirmware `20ad3d7a`](https://github.com/UniXNU/AdrenoFirmware/tree/20ad3d7aca14bd46aecab6335c780f5413fa054b) | **后期GPU**：HFI消息、启动状态机、投票与故障退出 | 新增独立参考；当前消费版本需沿GPU固件输入进一步核定。README报告sheng GMU/HFI实机成功；目录verified_devices为空，不等于任意版本已验 | `research/AdrenoFirmware` |
| [AdrenoMetal `73d582fd`](https://github.com/UniXNU/AdrenoMetal/tree/73d582fd4d5772b1f5fa83581a25077a16f2b6cd) | **后期GPU**：Metal/IOSurface资源生命周期、池化、压力回收、提交与等待 | 已有历史组件和A830参考fork；新增官方克隆补齐主线。与GPU用户客户端、Turnip和OS ABI联动；27/macOS改动不能原样覆盖17 | `research/AdrenoMetal-official` |
| [AdrenoPM4 `282606b5`](https://github.com/UniXNU/AdrenoPM4/tree/282606b528b2595bc4274ea7490b62b323f35a5f) | **后期GPU**：PM4编码与队列组织方法 | 已有独立参考；当前消费版本随GPU构建依赖核定。包格式/寄存器随Adreno代际变化，A830须逐项核对 | `research/AdrenoPM4-night` |
| [AirNir `b356371a`](https://github.com/UniXNU/AirNir/tree/b356371a74cd158c2902f4886f373ebb0f833a36) | **后期GPU**：AIR到NIR/Turnip的shader翻译链 | 新增独立参考，按图形构建依赖审查。README为离线UI shader编译；不等于Y700硬件渲染 | `research/AirNir` |
| [AppleKeyStoreState `6ff4f11d`](https://github.com/UniXNU/AppleKeyStoreState/tree/6ff4f11d8fdf853351f8d98e1bbe1373fb8da2e6) | **已复用**：软件密钥服务、wrap/unwrap、用户态启动依赖 | v123已采用6ff4f11d；bluetoothd越过readRootKeys。仅临时RAM Data的软件状态，identity=1 fixture不提供硬件保护/持久配对 | `research/AppleKeyStoreState` |
| [ArmCpu `d90e457b`](https://github.com/UniXNU/ArmCpu/tree/d90e457b8392623853ec85c860feef546c767621) | **近期**：共享level IRQ、计时器/IPI/idle统计、调度资格检查 | 八核在线已验证；保留Elden启动与回程修补。ArmCpu不是板级DVFS驱动；WFI不等于深度PSCI suspend | `research/ArmCpu` |
| [ArmDTPlatform `e8bd8d5d`](https://github.com/UniXNU/ArmDTPlatform/tree/e8bd8d5de395c6cbc00d762c1bef57dbd15a448d) | **近期**：平台服务注册、RTC缺失时避免无限等待、板级时钟接口 | 历史构建已有；需对照当前clock/RTC接入后选择差量。上游新接口需板级provider；不能伪造RTC或ready | `research/ArmDTPlatform` |
| [ArmSmmu4K `83969cd8`](https://github.com/UniXNU/ArmSmmu4K/tree/83969cd874503e65997ff7639f7dcf3d0a92cd17) | **按依赖**：4K页表、IOVA映射及故障定位的共用算法 | 已有独立参考；当前消费版本随GPU/SMMU集成核定。SM8750真实stream/CB/ASID/地址宽度必须由本机确定 | `research/ArmSmmu4K-night` |
| [ArmVirtPlatform `d1423a8b`](https://github.com/UniXNU/ArmVirtPlatform/tree/d1423a8bceac4be0478a93d9173587111c040084) | **不采用**：QEMU virt平台 | 不是Y700硬件平台；不克隆。远端README/元数据；本项目不跑QEMU | 远端文档；不克隆 |
| [Ath12kWifi `5f7f5a8a`](https://github.com/UniXNU/Ath12kWifi/tree/5f7f5a8a9f02f7ab45ed10a2f226e348c519a838) | **近期**：复用ath12k/MHI/QRTR/MAC及现成用户态链 | 125对象及Peach backport已构建；真实WLAN硬件回调未接通。缺的是本机电源/PCIe/BAR/MSI/DMA/MHI边界；源码存在不是网络可用 | `research/Ath12kWifi` |
| [DarwinBoot `5243c68e`](https://github.com/UniXNU/DarwinBoot/tree/5243c68ec332a227fe3680cd5da6d5a0e127035c) | **按依赖**：保留内存区间与loader payload回收契约 | 当前已有板级loader和6GiB/独立8GiB分支。最新回收/排除区README明确未实机；须配对XNU改动，不是16GiB开关 | `research/DarwinBoot` |
| [GopFramebuffer `b0d812d5`](https://github.com/UniXNU/GopFramebuffer/tree/b0d812d578efa2acb005b66f73168891719af09a) | **近期**：CPU显示拷贝、fence取消/快照、格式和帧耗时统计 | 已复用；v105/v106修好拷贝/映射，保留该分支修补。macOS半浮点颜色路径与17白色占位不自动同因 | `research/GopFramebuffer-official` |
| [QcaBluetooth `986d6319`](https://github.com/UniXNU/QcaBluetooth/tree/986d6319d1d2819b27ed2c9786776f10bf63cc76) | **近期**：原生HCI桥、BlueTool协议、扩展发现与生命周期 | 已移植为17/WCN7861路径；v138可持续投递LE扩展报告。sheng27配对证据不可当Elden17验收；最新IBS时钟修补仅host验证 | `research/QcaBluetooth` |
| [QcomBaseband `dd0199cf`](https://github.com/UniXNU/QcomBaseband/tree/dd0199cf3300764ed52b23f4a47761f91fab21a2) | **概念参考**：QMI/QRTR异步生命周期与用户客户端边界 | 新增独立参考；Y700无蜂窝目标，不接入基带驱动。SC7180 IPA4.2与本机无线芯片/接口不同，禁止抄寄存器 | `research/QcomBaseband` |
| [QcomDwc3 `0dd83827`](https://github.com/UniXNU/QcomDwc3/tree/0dd83827279ee070dca7ddb486c90365567cc99d) | **按依赖**：Apple XDCI/XHCI服务、数据角色、USB收发与PHY初始化方法 | 已有参考；Elden的CDC调试/回程独立且已成功。默认27 ABI、单板PHY/SMMU/UCSI；不包含Y700双口选电策略 | `research/QcomDwc3` |
| [QcomGeniSpi `eac47bae`](https://github.com/UniXNU/QcomGeniSpi/tree/eac47baefe6a5d2368a70351e6ad1b6361bedbe2) | **已复用**：GENI SPI传输与QUP DMA接口 | 已有历史组件/触控路径；此次补独立克隆。本机GENI引擎、时钟、IRQ、CS和DMA绑定不可照搬 | `research/QcomGeniSpi` |
| [RamBlock `00a6e5dd`](https://github.com/UniXNU/RamBlock/tree/00a6e5dd6bb1709e817e13daec7986308cfb6d0f) | **近期**：补固态介质属性；后续审查seed回收和持久Data顺序保证 | 已用临时Data；匹配源码缺Solid State属性和seed释放。8732b3e/737f6da提交明确未实机；自动格式化/持久布局不在此次范围 | `research/RamBlock` |
| [ShengHidInput `11406145`](https://github.com/UniXNU/ShengHidInput/tree/114061452959a547aaa08f9ca5aa54033394ca2f) | **已复用**：独立digitizer、报告交付、edge事件及属性引用寿命 | Elden独立digitizer/17 edge路径及v100抬指修复已用。最新arm64e路径编译不等于17/本机验收；保留本机交付失败修复 | `research/ShengHidInput` |
| [ShengNovatekTouch `69fdd622`](https://github.com/UniXNU/ShengNovatekTouch/tree/69fdd6223ed2572aa8bd8351e77c53a238276130) | **局部复用**：触控上报/中断/接触生命周期与故障退出 | 本机NT36536点包已工作，AP501U调研独立。上游NT36532E矩阵tracker不同，不替换本机解包或笔通道 | `research/ShengNovatekTouch` |
| [ShengPreflight `9cfc8d2c`](https://github.com/UniXNU/ShengPreflight/tree/9cfc8d2c8d77f2008ba228fa6eff83d2c7ab7fd2) | **局部复用**：UEFI前置资源检查与证据记录模式 | 本机已有EldenUfsStage2等资格检查。Xiaomi Pad6S专用前置代码，不直接刷到Lenovo | `research/ShengPreflight` |
| [ShengUfs `b6fe07b3`](https://github.com/UniXNU/ShengUfs/tree/b6fe07b307eeddc5e258c9d5d4387b968a55e4e9) | **近期**：固态属性、IRQ/多槽/直接PRDT、完成等待和认证表缓存 | 当前匹配源码仍单槽轮询；主线优化存在真实差距。性能必须本机同负载实测；保留SM8750接管、窗口、回程、写入门 | `research/ShengUfs` |
| [SoftwareAES `da07dd5c`](https://github.com/UniXNU/SoftwareAES/tree/da07dd5c7d62bbe960f5bd4fe7789574d3a49d8c) | **已复用**：IOAESAccelerator接口与软件AES服务 | 现有AES provider已有成功记录，避免重新实现。Darwin26 nonce/ABI扩展不能整体覆盖17；不代表硬件AES | `research/SoftwareAES` |
| [uefi-sheng `66421cb7`](https://github.com/UniXNU/uefi-sheng/tree/66421cb7bb5694843aec8de1ca3d1de4c20cca38) | **局部复用**：UEFI集成/显示handoff/固件打包方法 | 本机固件、签名与回滚floor独立。SM8550设备固件，不是Y700可刷镜像 | `research/uefi-sheng` |
| [UniXNU `0c1bac3d`](https://github.com/UniXNU/UniXNU/tree/0c1bac3d51a3009dca1708b15a5198f4b43d057a) | **总入口**：官方指南、component catalog、OS ABI、构建/补丁/发布规范 | 现有clean-build已独立重建；以当前正式输入为准。目录revision、默认分支HEAD、Elden消费版本三者分开；指南不是所有driver的实机证明 | `research/UniXNU-official` |
| [UniXNU-sheng `5ae8b487`](https://github.com/UniXNU/UniXNU-sheng/tree/5ae8b4876a378a5104330a5ae514ec9d6deae373) | **总入口**：板级集成、CPU governor、时钟、HID、背光、UFS测试方法 | 已广泛复用；本轮继续核package内未拆独立仓的实现。SM8550 EPSS/3域、充电/PMGR不直接套SM8750；PMGR若干方法仍主动拒绝 | `research/UniXNU-sheng` |
| [UniXNU-sm8550-common `2dc650ca`](https://github.com/UniXNU/UniXNU-sm8550-common/tree/2dc650ca76ae38715cd0712e60a44b14fe251745) | **局部复用**：资源ownership、QUP/SMMU、GENI时钟与SoC分层结构 | 已有参考；为SM8750层提供接口设计模板。明示SM8550/SM8550 DTS，不是本机寄存器事实来源 | `research/UniXNU-sm8550-common` |
| [VerifiedRoot `974f043d`](https://github.com/UniXNU/VerifiedRoot/tree/974f043d0c71ba2e60331483a41c6c6d35274ee3) | **已复用**：认证块读取与根哈希/策略契约 | 根卷校验链已工作；与UFS表缓存一起核对。优化不能跳过哈希或以未验证缓存冒充已认证数据 | `research/VerifiedRoot` |
| [VirtioMmioBlock `4e1013eb`](https://github.com/UniXNU/VirtioMmioBlock/tree/4e1013eb8c45077b57f8d38d61b389fe899ea1c3) | **不采用**：虚拟只读块设备及协议结构参考 | 此次克隆只为完整审查，不进入Y700配置。QEMU传输，不是物理UFS优化；无QEMU测试 | `research/VirtioMmioBlock` |
| [VirtioMmioConsole `70253216`](https://github.com/UniXNU/VirtioMmioConsole/tree/70253216890b2afcaa6333948726f896f84fc757) | **不采用**：虚拟控制台及协议结构参考 | 此次克隆只为完整审查，不进入Y700配置。QEMU传输，不替代已验证USB CDC回程；无QEMU测试 | `research/VirtioMmioConsole` |
| [XnuPrelink `440589b0`](https://github.com/UniXNU/XnuPrelink/tree/440589b0c31625f17edf363e24b3c82c51c70bb9) | **工具复用**：准确ABI匹配、原生/原厂符号绑定、fileset布局和碰撞拒绝 | 已有固定17 prelink输入；此次补独立克隆。最新大量27/macOS fileset修补，不能拿缺失map强放行或换27地址 | `research/XnuPrelink` |


## 4. 同步盲点与后续维护

本轮原有16个组织仓同步：10个已最新、5个固定检出仅fetch、1个错误。错误来自 `Adreno740-ipados27` 仍跟踪已删除的 `feat/ipados27-gpu-parity`；本地HEAD `10ac0eaa0ad8f24426da85d3570026081dc50bc5`保持。已另外只fetch默认主线引用到 `origin/main=54b41b8f59e90a167f6f75160739c5f825945fbc` 并审阅，不切换checkout或修改candidate pin。

这个异常今后仍可能由旧tracking规则报告；**本轮没有暗改同步器或仓库跟踪分支**。维护者应同时核默认分支而非把一次tracking fetch失败视为“上游无更新”。删除分支修复应另做明确的引用配置变更，保留固定旧HEAD和记录。

新增14仓已追加 `config/reference-repositories.json`，原47项observed_head逐项保持；常规同步器自动发现research独立根，所以新增仓会参加后续同步。当前其他整理任务的 `maintenance/IN_PROGRESS.json` 保持，定时同步仍应遵守锁、暂缓。此次最终仅执行inventory校验。

新增：AdrenoFirmware、AdrenoMetal-official、AirNir、ArmCpu、ArmDTPlatform、DarwinBoot、QcomBaseband、QcomGeniSpi、RamBlock、SoftwareAES、VerifiedRoot、VirtioMmioBlock、VirtioMmioConsole、XnuPrelink。目录名保留已有alias，未制造第二份同URL克隆；A830第三方fork与官方主线保留为不同来源。

## 5. 给实现者的使用方法

1. 从本报告的子系统优先级定位源码入口，按机器清单的完整SHA读取；若checkout与审阅HEAD不同，使用 `git show <SHA>:<path>`，不要为看代码切换冻结checkout。
2. 同时读取正式Elden对应profile/provider；原历史v91上游revision只作为历史证据，实际消费源码以hash/patch链为准。catalog pin同样不等于最新主线。
3. 提取最小可解释差量，记录OS17 ABI、本机寄存器/firmware/所有权条件；保留错误返回、数据完整性及回程。现有clean-build入口承担复现，不加入旧绝对路径产物依赖。
4. 先核构建/真实函数故障路径，再做能回答明确问题的一次联合硬件窗口。host测试、编译、sheng实机、Elden实机分别记录。不为每个新增README多刷一次。
5. 将验证过的差量提交正式 `UniXNU_elden`；将原始实验记录放工作台 `lab/records`，参考评审放 `lab/reference-reviews`，research只留独立Git仓。

证据快照：工作台 `lab/reference-reviews/20261115-unixnu-org/` 内API枚举、克隆动作、同步完整报告、provider哈希、最终inventory及逐仓README/提交输入。此次未替换内核、未测试平板，未改变长期Goal状态。
