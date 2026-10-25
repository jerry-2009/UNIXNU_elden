# UniXNU 移植到联想拯救者 Y700 四代（TB322FC / elden）最小目标实施方案

> 调研日期：2026-10-25  
> 目标修订：2026-10-25  
> 目标设备：Lenovo Legion Y700 Gen 4（4th Gen），型号 TB322FC，代号 `elden`，SoC SM8750P  
> 结论性质：基于公开源码、文档和设备移植记录的静态分析，不代表 `elden` 上的实机验证

## 0. 本次唯一目标

本轮只验收以下三项。三项全部在同一个可重复启动的镜像上通过，才算本轮目标完成：

| 优先级 | 验收目标 | 完成标准 |
| --- | --- | --- |
| P0 | **UEFI 正常启动** | 经 `fastboot boot` 可重复进入 UEFI，GOP 显示、按键输入、启动管理器和载荷读取可用；不是只停在 BDS 或白屏 |
| P1 | **进入 iPadOS 用户态** | DarwinBoot 成功加载 XNU，`launchd` 运行，屏幕上出现可交互的 iPadOS 用户界面；仅到达 XNU 控制台、panic 或 UniXNU 菜单不算完成 |
| P2 | **触摸正常工作** | 在 iPadOS 中可正常点按、拖动和多点触控；坐标、旋转和边缘映射正确，抬起后无粘滞触点 |

本轮使用现有设备仓固定的目标镜像：**iPad7,1 / iPadOS 17.7.11 / build 21H461**。如果改换 IPSW，需要重新验证 kernelcache、trust cache、MobileGestalt 身份和预链接结果。

### 0.1 明确不在本轮范围

以下项目先不做，也不能因为相关工作顺手可做而阻塞上述三个目标：

- Adreno 830 GPU、Metal、GPU scanout、硬件加速桌面；
- 相机、音频、扬声器、麦克风、Wi-Fi、蓝牙、蜂窝网络；
- 充电策略、睡眠/唤醒、热管理、手写笔、振动和传感器；
- Android 容器、macOS、x86 应用、性能调优和日常续航；
- 外观细节、动画流畅度、HDR、刷新率和色彩管理。

显示和 UFS 不单独列为目标，但它们是“进入用户态 iPadOS”的必要前置条件。首阶段可以只使用 GOP framebuffer，不能把 GPU 驱动设为用户态验收门槛。

## 1. 结论摘要

**最小目标是可实现的，但仍不是“把现有镜像刷进去”的工作量。** `elden` 同时具备两个非常有利的条件：

1. 已经有针对本机型、本 SoC 的 Mu-Silicium/UEFI 设备包，开源记录显示它能越过 BootShim 和 ABL，进入 UEFI BDS；
2. 已经有一份活跃的 `elden` 主线 Linux bring-up 仓，提供了真实的 UFS、显示、触控、内存和固件资料。

最大的缺口是：**现成的 `elden` UEFI bring-up 在旧实验中卡在 UFS 初始化和 SMMU 配置，且目前没有 UniXNU 在 `elden` 上的实机记录。** 同 SoC 的小米平板 8 Pro（`piano`）已经实机显示过 UniXNU 菜单，但其内部存储仍未打通；`piano` 能显示菜单，主要依靠 RAM disk 中的载荷，而不是 UFS 已可用。公开记录尚未证明 DarwinBoot 到 XNU 用户态的完整硬件链路。

推荐路线：

1. 以 [`code002-2/UniXNU-piano`](https://github.com/code002-2/UniXNU-piano) 作为最小设备仓模板；
2. 以 [`mu_wide_platforms` 的 `lenovo-y700g4` 设备包](https://github.com/sunflower2333/mu_wide_platforms/tree/main/Platforms/PakalaPkg/Device/lenovo-y700g4) 作为 `elden` UEFI 起点；
3. 吸收较新的 SM8750 `UFSDxe.patched.efi` 修复，先验证 UEFI UFS/Block I/O；
4. 同时准备一个从启动镜像 RAM disk 发布的只读 FAT 载荷卷，使 UniXNU、DarwinBoot 和内核验证不被 UFS 阻塞；
5. 按“UEFI 正常启动 → UniXNU/DarwinBoot → XNU → UFS 根卷 → iPadOS 用户态 → 触摸”的顺序逐级验收。

实现“用户态 + 触摸”仍需新的 SM8750 存储与显示路径，但不要求先完成 Adreno 830 图形栈。这样可以显著缩小首轮工作范围，并允许先用 CPU/GOP 显示路径验证 iPadOS 启动和输入。

### 当前执行约束与阶段 0 状态

- **阶段 0 已完成（2026-10-25，设备所有者确认）**：Y700 已具备可用的 9008
  引导路径和恢复包，全量固件备份已经完成；恢复能力不再依赖尚未验证的 UniXNU。
  备份位置和内容不进入仓库，也不由自动化流程扫描。
- **后续所有测试必须使用 `fastboot boot <image>` 进行 RAM 启动。**
- 不在 bring-up 测试中使用 `fastboot flash`，不切换或改写 boot 槽，不擦除/格式化分区，不修改 GPT，也不执行 `fastboot set_active`。除非未来另行明确批准，这些操作均不属于测试流程。
- 每次测试前确认 9008 引导、恢复包和全量固件备份仍可访问。RAM 启动失败时直接断电并回到 Android，不尝试在故障状态下修补分区。
- 所有启动操作均由设备所有者本人执行；仓库不提供启动自动化。
- 阶段 0 的完成记录见 [`PHASE0.md`](PHASE0.md)。

## 2. 调研证据

| 资料 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| [UniXNU 移植文档](https://unixnu.com/zh/porting/) | 一个设备需要设备仓、UEFI 仓、ADT、defconfig、负载和板级驱动 | 没有 `elden` 现成支持 |
| [UniXNU 核心仓](https://github.com/UniXNU/UniXNU) | BootShim、UniXNU 启动器、DarwinBoot、4 KiB XNU、通用 ARM64 驱动和预链接框架已经存在 | 通用框架不等于 SoC 驱动已适配 |
| [UniXNU-piano](https://github.com/code002-2/UniXNU-piano) | 与 `elden` 同为 SM8750 族；有可用 `board.toml`、ADT 生成器、内核构建和 prelink 流程 | 其 README 仍把设备描述为未上机；没有证明完整 XNU 用户态可用 |
| [UniXNU-piano 构建记录](https://github.com/code002-2/UniXNU-piano/blob/main/KERNEL-BUILD.md) | 同一 SoC 上 XNU 可构建、预链接，UniXNU 菜单可实机显示；源码给出了 RAM disk 载荷绕过内部存储的方案 | 内部存储仍未打通；不能证明 `elden` 的 UFS、屏幕或 GPU 可用 |
| [Y700 四代 Linux bring-up](https://github.com/h0cheung/tb322fc-linux-kernel) | 大部分板级地址、外设、分区和 UEFI 实验记录；Linux 已能在设备上运行 | Linux 驱动不能直接链接进 XNU |
| [`mu_wide_platforms` `lenovo-y700g4`](https://github.com/sunflower2333/mu_wide_platforms/tree/main/Platforms/PakalaPkg/Device/lenovo-y700g4) | 已有本机型原厂 DXE、内存图、ACPI、1904×3040 framebuffer 配置和 BootShim 启动链 | 老版本 UFS/SMMU bring-up 不完整 |
| [Project-SunUEFI](https://github.com/slwyts/Project-SunUEFI) | 证明 SM8750 + EDK2 + 双 DSI + Linux 的完整启动链在现代平板上可工作 | 它是 `piano` 产品移植，含小米 ABL、合体 BOOT 和板级假设，不能直接套到 `elden` |
| [Android `elden` 设备仓](https://github.com/lolipuru/android_device_lenovo_elden) | Android 分区、关键属性、触屏键位和原厂系统基线 | 不含 XNU 或 UEFI 实现 |

## 3. 已知硬件与软件接口

| 子系统 | `elden` 已知信息 | 对 UniXNU 的意义 |
| --- | --- | --- |
| SoC | SM8750P，8 核 Oryon | 与 `piano` 同 SoC 族，CPU/GIC 地址和 MPIDR 布局可高概率复用，仍需读本机 FDT 核对 |
| GIC/时间 | GICv3 distributor `0x16000000`，redistributor `0x16080000`；timebase 19,200,000 Hz | 可直接进入 `ArmCpu` 的 ADT，但 redistributor 大小和 stride 需按本机树确认 |
| 内存 | DRAM base `0x80000000`；市售有 12 GiB 和 16 GiB 两档 | 不能跨容量复用内存图；DarwinBoot 连续自有窗口最大 8 GiB，但不等于整机 RAM 只能有 8 GiB |
| UFS | host controller `0x1d84000`，PHY `0x1d80000`，4 KiB 逻辑扇区，A/B 槽 | 进入用户态前必须提供 OS/SystemOS 根卷；`NativeUfs` 要增加 SM8750 时钟、PHY、GDSC、regulator、SMMU stream 和 MCQ/legacy queue 策略 |
| 显示 | SM8750 DPU `0xae00000`；DSI0/1 `0xae94000`/`0xae96000`；DSI PHY0/1 `0xae95500`/`0xae97500` | 用户态必须能显示画面；先用 GOP presenter，之后需要新的 XNU DPU/DSI 驱动 |
| 面板 | 1904×3040，bonded 双 DSI + DSC；Linux 仓称为 NT36536 / CSOT PP8807HB1，原厂 DTS 的 panel 节点使用 `nt36523` 命名 | 面板型号字符串存在命名差异，必须用原厂 DTS、固件和实机 ID 交叉确认 |
| GPU | Adreno 830 / gen80000 | 本轮不要求 GPU/Metal；软件显示路径可以接受 |
| 触控 | Novatek SPI 触控，接 `qupv3_se4`/SPI4，DTS compatible 为 `novatek,NVT-ts-spi`，IRQ GPIO 162 | `NativeNovatekTouch` 可作协议层模板，但必须确认 NT36536 的 ID、memory map、固件和 THP 格式 |
| 电源/按键 | Qualcomm PM8550 系 PMIC、音量/电源键 | 首启动只需按键菜单输入；充电、休眠和热管理可后置 |

### 3.1 显示风险不是普通“写个 framebuffer 驱动”

`elden` 的 Linux bring-up 记录显示，显示子系统已有过长期的冷启动竞态：bonded 双 DSI 的首个 DCS 命令可能让 command DMA 引擎挂起，导致只有背光、没有画面。Linux 侧已经把根因缩小到 MDSS 复位、DYN pixel clock 域和 DSI command engine 的初始化顺序，但这仍然是社区正在验证的高风险路径。

对 XNU 的影响：

- UEFI 阶段可以依赖 `DisplayDxe`/GOP 先显示 UniXNU 菜单和固件日志；
- DarwinBoot 可以把 GOP framebuffer 交给 XNU，做最基本的文本/色条输出；
- 真正让 iPadOS 用户态显示可交互界面，仍需要 XNU 内的 SM8750 DPU、DSI、PHY、DSC、背光和 scanout 生产者，或者一条经过验证的 GOP framebuffer 呈现路径；
- 不能假设 Linux 的 DRM 驱动、命令序列和电源时序可以直接复制，必须按 XNU IOKit API 和 4 KiB IOMMU 重新实现。

## 4. 推荐的仓库和代码分层

建议建立两个设备专属仓，保持与 UniXNU 文档一致的职责边界。

### 4.1 `UniXNU-elden`

从 `UniXNU-piano` 复制最小结构，再从 `UniXNU-sheng` 借用成熟的驱动接入方式。

```text
UniXNU-elden/
  board.toml
  configs/
    elden_seed_defconfig
    elden_defconfig
  scripts/
    make-elden-adt.py
    check-elden-adt.py
    build-arm-driver.py
    seed-xnu-headers.py
  package/
    EldenPlatformPower.cpp
    EldenUfsProbe.cpp
    EldenDisplayProbe.cpp
    EldenTouchProbe.cpp
  drivers/
    # 仅放设备专属覆盖；通用 ArmCpu、ArmDTPlatform、
    # ArmSmmu4K、NativeHidInput、NativeUfs、
    # NativeMobileDisplay 和 Novatek 协议层继续使用基础仓
  patches/
    # 只放无法由设备 package 表达的小补丁
```

首版 `board.toml` 不应照搬 `piano` 的 8 GiB、userdata LBA 或产品身份，而应至少替换：

- `[board].name = "elden"`、真实机型描述；
- `[payload].dram_size`：按本机 12/16 GiB SKU 取值；
- `[payload.adt].owned_memory_size`：从 256 MiB–8 GiB 中选择连续窗口；
- `[userdata].first_lba/last_lba/lba_bytes`：来自本机 GPT；如果使用专用分区，还需用 `[[block_slice]]` 或驱动映射，不要默认覆盖 Android `userdata`；
- `root_match_volume_uuid`：生成目标 userdata 后再填；
- `unique_chip_id`：每台设备本地生成，不能上传；
- trust cache、Data seed 和 Product 身份：首阶段不要为了“像 iPad”而一次性引入全部输入。

建议首版 defconfig 只启用：

```text
CONFIG_XNU_SOURCE_CORECRYPTO14=y
CONFIG_XNU_ARM_DT_PLATFORM=y
CONFIG_XNU_ARMCPU=y
CONFIG_XNU_NATIVE_ARCH_TIMER=y
CONFIG_XNU_NATIVE_PAN=y
CONFIG_XNU_NATIVE_CS_HASH_CACHE=y
CONFIG_XNU_TRUST_CACHE_RUNTIME=y
```

第一阶段只关闭会影响 XNU 入口诊断的组件。达到用户态目标前，必须再启用 UFS、显示、触摸、APFS/根卷和 owner userland 路径。GPU、Audio、Wi-Fi、相机等保持关闭；否则首次启动会被多个缺失 provider 和无关 panic 混合淹没。

### 4.2 `uefi-elden`

最合适的基线不是 `uefi-sheng`，而是 `mu_wide_platforms` 中已有的 `lenovo-y700g4` 设备包。该包已经包含：

- `DisplayDxe`、`ArmGicDxe`、`TimerDxe`、`ButtonsDxe`、`PmicDxe`/`SPMIDxe` 等原厂 DXE；
- `PlatformMemoryMapLib` 的真实内存映射；
- 1904×3040 framebuffer 的 PCD；
- 本机型 ACPI/DSDT；
- BootShim 和 Android boot image 打包逻辑；
- 与 `elden` 对应的 UFS、时钟、USB 等二进制候选。

需要加入：

- `UniXNUPkg/Application/UniXNU/UniXNU.inf`；
- `UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf`；
- `DarwinBootPkg/Driver/DarwinBoot.inf`；
- 指向基础 UniXNU 树的 `PACKAGES_PATH`；
- 只读 RAM payload 块设备，或可靠的 UFS `SimpleFileSystem`；
- Framebuffer serial 输出，确保 UI 卡住时还能从屏幕读出 UEFI 日志。

### 4.3 启动镜像格式

不能默认 `unixnu bootimg` 适用于所有设备。`UniXNU-piano` 的实机记录显示，小米设备原厂 `boot_a` 使用 Android header v4，而 `unixnu bootimg` 生成 v0；`piano` 最终使用 SunUEFI 自己的打包器和合体 BOOT。`elden` 也可能依赖自己的 `mkbootimg.py`、header version、加载偏移和 DTB 附加方式。

因此 `elden` 启动镜像应以 `lenovo-y700g4` 包实际可用的参数为准，并用 `boot.json` 记录并验证：

- `header_version`；
- kernel 加载基址；
- firmware volume 基址和大小；
- `kernel_size`；
- 是否附加 DTB；
- BootShim 的 `REQUIRES_KERNEL_HEADER`。

## 5. 分阶段迁移路线

### 阶段 0：资产与恢复路径（已完成）

目标：出现任何启动失败都能回到 Android。

当前状态：

1. Y700 已有可用的 9008 引导和恢复包；
2. 设备固件已完成全量备份；
3. 回滚路径不依赖 UniXNU、UFS 驱动或设备上的任何实验性组件。

阶段 0 的资产与恢复前置条件已经满足。进入阶段 1 后仍须遵守以下硬性规则：

1. 所有测试只通过 `fastboot boot <image>` 做 RAM 启动，不写入 boot 槽或其他分区；
2. 不执行 `fastboot flash`、`fastboot set_active`、擦除、格式化、GPT 修改或槽位切换；
3. 每个测试镜像记录 SHA-256、构建来源和测试时间；
4. 同一镜像至少连续两次 RAM 启动，确认行为一致后才继续调试；
5. 启动失败时先断电并恢复正常 Android，再分析日志；恢复包和全量固件备份始终作为最后回滚手段，不依赖实验性启动链。

### 阶段 1：UEFI 正常启动

目标：UEFI 能稳定、可重复地启动到可见的 UniXNU 菜单，并证明 BootShim、ABL、DXE、framebuffer、按键输入和载荷读取链路完整。

工作：

1. 用现有 `lenovo-y700g4` 设备包编译 `fastboot boot` 镜像，仅做 RAM 启动；
2. 打开 framebuffer serial 和详细日志，记录固件版本、内存图和启动失败点；
3. 先不依赖 UFS，把 `EFI/UniXNU/unixnu.toml`、最小 ADT 和测试 payload 放入 RAM disk；
4. 增加只读 RAM Block I/O，让 `DiskIoDxe`、`PartitionDxe`、FAT 能发布载荷卷；
5. 将 UniXNU 和 DarwinBoot 链入固件卷；
6. 用音量/电源键验证菜单输入；
7. 整个阶段禁止执行 `fastboot flash`、槽位切换、擦除、格式化或 GPT 修改。

UEFI 正常启动的验收标准：

```text
DISPLAY OK
INPUT OK
UNIXNU: config: loaded
UNIXNU: menu: shown
```

- 同一镜像至少连续两次冷启动均到达上述状态；
- 不是停在 BDS、白屏、蓝点、“UFS WAIT”或没有输入的菜单；
- 每次测试记录镜像 SHA-256；
- RAM 启动退出后，原厂 Android 仍能正常启动。

如果只能进入 BDS、却完全读不到载荷卷，优先实现 RAM payload，而不是继续猜 UFS 配置。UFS 可以在本阶段并行取证，但不作为 UEFI 菜单能否显示的阻塞项。

### 阶段 2：DarwinBoot 与 XNU 入口

目标：从菜单加载与 `iPad7,1 / iPadOS 17.7.11 / 21H461` 一致的最小 4 KiB XNU，
证明入口执行、`ArmDTPlatform` 匹配和 boot CPU 的 `ArmCpu`、GIC/定时器基本路径。
2026-10-25 重排后的详细工作与验收以 [PHASE2-HANDOFF.md](PHASE2-HANDOFF.md) 为准。

1. **2.0 基线与配置**：当前本地产物与历史实机哈希不同，先保存可确认来源的基线；
   独立当前主仓解析格式 2，阶段 1 的固定依赖和产物继续保留。
2. **2.1 硬件树与内存**：补真实固件 FDT 和保留区；硬件 DTS 经共享 ADT 生成器生成
   sidecar，核对 CPU/GIC/timebase、产品身份、内存占位符与禁用休眠设置。
   原低 2 GiB 候选已确认与多个保留区冲突，UEFI `Kernel` carveout 候选又撞上
   live initrd；当前改用 `0xC2400000` 的 256 MiB DXE conventional window，详见
   [阶段 2.1 状态](PHASE2.1-STATUS.md)。
3. **2.2 内核输入**：目标 kernelcache/ABI、4 KiB 配置和可复现 kernel/link/prelink
   产物已完成，保存了符号与哈希；可选 trust cache/Data seed 不阻塞早期验证，详见
   [阶段 2.2 状态](PHASE2.2-STATUS.md)。
4. **2.3 大载荷通道**：先验证 Android ramdisk → 固件 FDT → HOB → 共享 RAM disk 驱动
   的候选路径及近最终尺寸 FAT 的完整性；重新测量 FV、BootShim 和内存交叠。
   此路径尚未在 elden 验证，不能直接向现有 4 MiB FAT 复制内核。
5. **2.4 DarwinBoot**：验证菜单、内核/ADT 对应关系与拒绝路径，记录退出 boot services
   前的边界。loader/inputs validated 日志只算加载器证据。
6. **2.5 XNU 实机**：逐项证明入口、平台专家和 boot CPU；同一最终镜像两次冷 RAM 启动
   到相同可定位阶段，随后原厂 Android 正常启动。仅有入口色条或早期 panic 不算完成。

平台专家和 boot CPU 通过后，已知根卷等待或后续 provider 缺失可作为本阶段终点。
UFS、根卷、原生显示、触摸、SMP 和用户态均后置；本阶段完成不代表进入 iPadOS 用户态。

### 阶段 3：UFS、根卷与用户态输入准备

目标：让 XNU 读取 iPadOS 的 OS/SystemOS 镜像，并提供启动用户态所需的 trust cache、Data 种子、根卷匹配和显示通道。

工作：

1. 为 `NativeUfs` 增加 SM8750 profile；
2. 对照 Linux `ufshc@1d84000`/`ufsphy` 和原厂 UEFI DXE，补齐 clock、reset、GDSC、regulator；
3. 配置 APP SMMU 的 UFS stream 和 4 KiB 页表；
4. 处理 4 KiB LBA，避免把扇区大小写死为 512；
5. 判断控制器处于 legacy doorbell 还是 MCQ；不要未经实机确认就假定 MCQ 不支持旧 doorbell；
6. 用只读、专用介质发布 OS/SystemOS 窗口；在现有阶段 0 约束下，不格式化 Android `userdata`，不改写 GPT；
7. 接入 iPad7,1 的 MobileGestalt 产品身份、trust cache、Data RAM disk 和 `root_match_volume_uuid`；
8. 先使用 GOP/CPU framebuffer 呈现路径，让 XNU 能把画面交给用户态。

验收：

- XNU 能枚举 LUN0、GPT 和 OS/SystemOS 窗口；
- 根卷 UUID 可匹配，`launchd` 能开始运行；
- 屏幕至少能显示真实用户态画面，而不是停留在 XNU console；
- UFS 读取路径重复两次结果一致；
- Android 分区和原厂启动链未被修改。

UFS 或等效持久块设备是本阶段硬门槛。RAM payload 只能绕过 UEFI 阶段的存储问题，不能替代完整 iPadOS 根卷。

### 阶段 4：进入 iPadOS 用户态

目标：完成本轮的 P1。iPadOS 核心用户态进程运行，屏幕出现可视、可交互的用户界面。

完成判据：

- `launchd` 作为 PID 1 启动；
- iPadOS 图形和系统用户态服务启动，例如 `backboardd`/WindowServer 对应链路；
- SpringBoard 或等价首屏 UI 可见；
- 至少完成一次用户交互状态更新，例如显示首页、打开系统设置或切换界面；
- 运行期间没有立即复位、硬死机或持续重启；
- 允许使用软件/GOP 显示路径，不要求 Adreno 830 或 Metal；
- 记录启动日志、屏幕照片、Root UUID、kernel SHA-256 和 boot image SHA-256。

如果用户态因 GPU provider 缺失而 panic，应关闭 `NativeAdreno` 和相关 Metal 注入，只保留最小显示、HID 和文件系统路径，直到出现可见 UI。

### 阶段 5：触摸正常工作

目标：完成本轮的 P2。iPadOS 内可通过屏幕完成日常点击和导航。

实现顺序：

1. 读取 Novatek 芯片 ID，确认实际控制器是 NT36536、NT36532 相关变体还是其它协议；
2. 对齐 `elden` 的 SPI4/QUP、IRQ GPIO 162、复位、时钟和 SMMU；
3. 以 `NativeGeniSpi` 和 `NativeNovatekTouch` 为模板，验证固件下载、THP 帧和坐标矩阵；
4. 加入 `elden` 的面板方向、分辨率、边缘补偿和触点槽位；
5. 通过 `NativeHidInput` 发布标准 HID digitizer 事件。

触摸验收标准：

- 单指点击准确命中图标、按钮和文本输入区域；
- 单指拖动连续，释放后不产生粘滞触点；
- 双指缩放和滑动可识别；
- 屏幕旋转后坐标与显示方向一致；
- 屏幕四边和四角没有大范围偏移；
- 一轮测试至少连续操作 10 分钟，无丢帧性失联或触点卡死；
- 手写笔、压力、悬停和掌压优化不属于本轮目标。

### 阶段 6：统一回归

用同一个镜像完成三个目标的联合验收：

1. `fastboot boot` 进入 UEFI；
2. 进入 iPadOS 用户态并看到可交互界面；
3. 在用户态完成点击、拖动、双指操作和屏幕旋转后坐标测试；
4. 至少连续两次得到相同结果；
5. 保存 `boot.json`、`payload.json`、屏幕照片、UEFI/内核日志和所有镜像哈希；
6. 测试结束后仍能恢复原厂 Android。

## 6. 难度和阻塞点

| 工作项 | 难度 | 阻塞的目标 | 判断 |
| --- | --- | --- | --- |
| BootShim + ABL + UEFI BDS | 中 | UEFI | 已有本机型 UEFI 包，主要验证固件版本和镜像格式 |
| UEFI framebuffer/按键 | 低到中 | UEFI | 原厂 DXE 已有，需适配 UniXNU 菜单缩放和输入 |
| ADT/CPU/GIC/定时器 | 中 | iPadOS 用户态 | 同 SoC 参考很强，仍需本机 FDT 验证 |
| 4 KiB XNU 构建和 prelink | 中 | iPadOS 用户态 | 需 macOS/Xcode；核心已有补丁，piano 已证明可构建 |
| UEFI UFS/Block I/O | 高 | iPadOS 用户态 | 旧实验失败在 UFS/SMMU；需要更新 UFSDxe 和核对 MCQ |
| NativeUfs SM8750 | 高 | iPadOS 用户态 | 现有驱动仅明确支持 SM8550/SM7325 |
| SM8750 DPU/dual DSI | 很高 | iPadOS 用户态可见性 | Linux 自身仍有显示冷启动问题；可先验证 GOP/CPU 路径 |
| iPadOS 身份与 userland 启动 | 高 | iPadOS 用户态 | 需要 kernelcache、trust cache、Data seed、文件系统和用户态服务协同 |
| NT36536 触控 | 中到高 | 触摸 | 协议接近现有 Novatek 驱动，但不能直接宣称兼容 |

GPU/Metal、相机、音频、网络、休眠、手写笔和传感器不在本轮验收表中。它们难度再高也不应阻塞 UEFI、iPadOS 用户态和触摸三项验收。

## 7. 不建议的路线

### 直接刷 `Project-SunUEFI` 的 `piano` 镜像

不可取。它依赖小米的 ABL 行为、合体 BOOT 布局、`pianoPkg` 的 DT/内存图和面板选择。`elden` 是 Lenovo 平台，即使 SoC 相同，UFS、PMIC、显示和 UEFI DXE 也不保证兼容。

### 直接复用 `UniXNU-sheng`

`sheng` 是 SM8550 + Adreno 740 + NT36532E 的完整移植。它能作为以下内容的模板：

- 驱动静态库链接；
- `NativeUfs` 的 IOKit 结构和 SMMU 路由；
- `NativeNovatekTouch` 的分层方式；
- boot-progress、panic 和 GOP fallback。

但它的 GIC、显示 DPU、触摸 memory map 和电源域不能按 compatible 字符串直接迁移。Adreno 740 代码不在本轮范围内，也不应作为触摸或用户态启动的前置依赖。

### 先改 GPT/格式化 userdata 再 debug

所有 UEFI、载荷、DarwinBoot 和 XNU 入口问题都可以在零写盘的 `fastboot boot` 路径中先发现。测试流程不得使用 `fastboot flash`，不得切换启动槽、擦除或格式化分区，也不得修改 GPT；这些写入操作都会扩大故障面，并使 Android 恢复更复杂。

## 8. 当前可执行里程碑

原首个里程碑“RAM FAT 启动到可操作菜单并连续两次复现”已有
[阶段 1 实机验收记录](PHASE1-STATUS.md)。阶段 2.0、2.1 和 2.2 的主机工作已完成，
结果见[阶段 2 状态](PHASE2-STATUS.md)、[阶段 2.1 状态](PHASE2.1-STATUS.md)和
[阶段 2.2 状态](PHASE2.2-STATUS.md)。当前进入阶段 2.3，验证大载荷 RAM 通道。

真实 FDT/内存保留区与目标 XNU 输入已经完成，下一步验证大载荷通道。
使用共享 ADT 生成器，按[阶段 2 计划](PHASE2-HANDOFF.md)逐关推进；UFS、显示和
触摸驱动不作为当前首次 XNU 入口验证的前置任务。

## 9. 最终判断

### 可行性

- **UEFI 正常启动：可行性较高。** 本机型 UEFI 包已存在，且旧实验已进 BDS；RAM payload 可以避开存储缺口。
- **进入 iPadOS 用户态：高风险但可作为有限目标。** UFS、DPU/DSI、trust cache 和用户态服务都必须打通，但 GPU/Metal 不必成为前置条件。
- **触摸正常工作：中等可行。** 现有 Novatek/GENI SPI/HID 框架可以复用，主要工作是 NT36536 协议和设备常量验证。

### 推荐策略

**只围绕三个验收点推进：UEFI 正常启动、iPadOS 用户态可见可交互、触摸准确。** 先以 RAM payload 打通 UEFI 和 DarwinBoot，再逐个解决 UFS、显示和触摸；GPU、音频、网络、相机和其他外设全部后置。这样能尽早得到可判断的硬件结论，也能避免无关驱动延误首个端到端用户态结果。

