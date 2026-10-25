# 阶段 2：实施计划与验收关卡

更新时间：2026-10-25

状态：**阶段 2.0 已完成：格式 2 配置、输出隔离和现行阶段 1 候选的两次 RAM
冷启动均通过；阶段 2 尚无可启动 XNU 的镜像或实机证据。**
本计划替代原先直接“准备内核 → 打包 → 看 DarwinBoot 日志”的顺序。
`board.stage = 1` 和 `kernel.status = "phase-2-pending"` 保持不变。

## 目标与完成边界

从 UniXNU 菜单加载与目标 profile 一致的 4 KiB XNU，依次证明内核入口执行、
`ArmDTPlatform` 平台专家匹配、boot CPU 的 `ArmCpu` 初始化及 GIC/定时器基本路径。
每一步都要有对应位置的日志、探针或可定位的符号证据。

任意早期 panic 只能算调试进展。平台专家和 boot CPU 检查点通过后，可以以
可定位的后续 provider 缺失或根卷等待结束本阶段，并交接阶段 3。
UFS、根卷挂载、iPadOS 用户态、原生显示、触摸、GPU 和 SMP 不作为阶段 2 完成条件。
UEFI 菜单、加载器日志和入口色条分别只证明其所在层，不能相互代替。

## 对照现有项目步骤

按 UniXNU 官方八步流程拆分，并与本仓阶段 0–6 对齐：

| 官方步骤 | elden 已有基础 | 阶段 2 对应工作 |
| --- | --- | --- |
| 1. 收集输入 | 阶段 0 恢复资料、阶段 1 固件和实机记录 | 2.0 核对基线；2.1 补真实 FDT/保留区；2.2 补 XNU 输入 |
| 2. 选择共享支持 | ARM64、iPadOS、临时 SM8750 profile | 2.0 核对组件、源码和配置合并 |
| 3. 设备仓库 | 格式 2 的 board、DTS、feeds、移植记录 | 保留现有布局；开发可用本地 SoC，发布前固定共享提交 |
| 4. 解析与检查配置 | 已声明四层配置和 5 个组件 | 2.0 重跑 defconfig/status/tree，检查组件源码与补丁 |
| 5. 硬件描述与固件 | GOP/按键/内置 RAM FAT 已验收 | 2.1 分开固件 FDT 与 XNU ADT；2.3 验证大载荷通道 |
| 6. 按依赖适配驱动 | 只选择最小平台和 CPU 路径 | 2.5 先 boot CPU，再把存储/显示/触摸交给后续阶段 |
| 7. 构建与启动 | 阶段 1 构建和静态检查可用 | 2.2 内核 → 2.3 通道 → 2.4 加载器 → 2.5 XNU |
| 8. 完善与发布 | 尚未达到 | 分开记录源码、主机与实机证据，发布时复审 feeds/lock |

主依赖顺序：**2.0 →（2.1 与 2.2 可并行）→ 2.3 → 2.4 → 2.5**。
大载荷通道可提前做源码分析，但实机试验前必须明确基线和内存边界。
不按日期承诺完成时间；每关以产物和证据决定是否进入下一关。

## 当前事实与阻塞

### 阶段 1 验收记录与本地文件不同

历史验收见 [PHASE1-STATUS.md](PHASE1-STATUS.md) 和
[PHASE1-HANDOFF.md](PHASE1-HANDOFF.md)。2026-10-25 规划时读取的本地文件如下：

| 产物 | 历史实机验收 SHA-256 | 当前本地 SHA-256 |
| --- | --- | --- |
| `out/elden-phase1.img` | `b56ef4b7e5a71382b8c279c4ee1560764fabd126ba37ac0fd6e495c80b9ec6e1` | `94b6a6315b04fc9d276bc15e9519107be292244380fc3bf139f5af6c96a3bb0a` |
| `out/SILICIUM_UEFI.fd` | `021a2a65db9ea5d2254604a2f81cea15fa70436f61b3591f25c056f5bcb7e37e` | `e5420517d55f4b638c07617a252d3a65c95cfb731584dcb10dd1d98bae412580` |

本地 image 为 2,686,976 字节，FD 为 4,194,304 字节；`out/build.json`
与当前本地文件一致。历史验收仍保留为原始来源记录；当前重建产物也已完成
两次 RAM 冷启动复核。
2.0 重建前已将旧候选只读保存到本机 `.cache/phase2.0/candidate-2d47da288c66/`；
本轮重建没有把新候选提升为基线。

### 容量与输入

- 阶段 1 的 `EldenRamDiskDxe` 只发布内嵌 4 MiB FAT16，容不下预链接 XNU。
- 阶段 1 构建记录中的内层 FVMAIN 总计 18,403,328 字节、已用 18,402,408 字节，
  仅剩 **920 字节**。外层压缩 FD 为 4 MiB；外层余量不等于内层可用容量。
- 固件 `DeviceTreeBlob/Linux/linux-y700g4.dtb` 仍是 6 字节 `dummy`。
  `dts/elden.dts` 可编译也不能替代 ABL/UEFI 的完整固件 FDT。
- 没有可打包的 `kernel.macho` 和对应 `.adt`，也没有阶段 2 产物。
  trust cache、Data seed 是后续可选输入，不阻塞载荷通道或加载器拒绝路径测试。
- `payload.panic_screen = false`；菜单能显示不能证明 XNU panic 或控制台可见。

## 2.0：核对基线与格式 2 配置

工作：

1. 找回并只读保存历史验收 image/FD、构建报告、源码提交和日志；如无法找回，
   把当前文件视为新候选，由所有者重新完成两次冷 RAM 启动验收后再建立基线。
2. 阶段 1 继续固定 `third_party/UniXNU` 的
   `c62bf12595f9a86c1b7282cf12d5af40b441fdac`。格式 2 校验使用独立的当前主仓，
   不通过升级阶段 1 依赖来做配置检查。
3. 核对 ARM64 → SM8750 → iPadOS → device 的配置层次、片段、补丁顺序、
   源码提交和构建 recipe。组件保持 canonical ID：`ArmDTPlatform`、`ArmCpu`、
   `SoftwareAES`、`XnuPrelink`、`DarwinBoot`。
4. 阶段 2 实施时先隔离输出目录和报告；当前 `firmware.output_fd/output_image`
   仍指向阶段 1 路径，不能直接使用它们覆盖基线。没有已验收的一键阶段 2 构建入口。
5. `soc/sm8750` 可继续作为开发过渡输入；发布前才要求迁入已评审的共享仓提交，
   更新 `feeds.toml` 和 `unixnu.lock`，并复核差异。

出口：基线来源明确，配置和组件可解析；遗留输入缺口逐项列出，阶段 1/2 输出互不覆盖。

### 2.0 结果

主机部分已完成，详细结果见 [PHASE2-STATUS.md](PHASE2-STATUS.md)：

- 独立 UniXNU `16e592abee8a550dec8154ed1f38b5ebc4f16213` 通过
  `defconfig`、`tree`、`status` 和移植记录检查；
- 四层配置、5 个 canonical component、56 个有序补丁和 4 KiB 页设置可解析；
- 格式 2 输出位于独立目录，阶段 1 的 `out/` 未被重建或覆盖；
- `dtc 1.8.1` 生成 1,557 字节 DTB，阶段 1 候选的载荷和 FD 结构检查通过；
- 设备所有者报告同一新候选完成两次 RAM 冷启动并进入可见、可操作的 UniXNU
  菜单，退出后原厂 Android 正常启动。

历史验收镜像没有在当前工作区找到原始字节。当前 image
`94b6a6315b04fc9d276bc15e9519107be292244380fc3bf139f5af6c96a3bb0a`
已由所有者完成新基线复核，可以作为后续阶段 2 工作的现行阶段 1 基线。

## 2.1：固件 FDT、XNU ADT 与内存交接

保留两条不同用途的树：

- **固件 FDT**：供 ABL/BootShim/Mu SEC 使用，包含可信内存/保留区，后续承载 initrd 范围。
- **硬件 DTS → 共享 ADT**：由 `dts/elden.dts`、SoC DTSI 和 `board.toml` 经
  UniXNU `scripts/make-adt.py` 生成 `kernel.macho.adt`，供 XNU 使用。

工作：

1. 从所有者提供的只读 `/sys/firmware/fdt` 或可复现的 elden Linux 构建取得实际 FDT，
   记录来源与哈希。原始树可能含设备标识，只留本机；仓库提交脱敏后的资源描述。
2. 建立地址区间表，逐项记录 FD/BootShim、解压工作区、UEFI 分配、initrd、GOP framebuffer、
   XNU、ADT、boot_args 的起止、生命周期和归属，核对实际 reserved-memory。
   当前 `[0x80000000, 0x100000000)` 只是候选 2 GiB 窗口，不能假定整段空闲。
3. 用共享生成器检查 `/chosen`、`/cpus`、`/psci`、`/arm-io/intc`、`/defaults`、
   `/options`、CHRP NVRAM、产品身份、64 字节熵及 `/chosen/memory-map` 占位符。
   占位符必须与实际打包的可选输入一致；不得为尚无根卷的镜像虚构 UUID。
4. 核对 `arm-io` 地址换算、ADT 小端 u64 `reg` 编码和真实 boot CPU：

   | 项目 | 当前资源输入 |
   | --- | --- |
   | MPIDR affinity | `0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x10000, 0x10100` |
   | GIC distributor | `0x16000000 + 0x10000` |
   | GIC redistributors | `0x16080000 + 0x200000`，stride `0x40000` |
   | timebase / PSCI | `19,200,000 Hz` / SMC |
   | GOP | 1904×3040；基址、stride、格式和保留区须实测 |

5. 审计现有内核参数，尤其 `armcpu-spi-ipi=1` 等开关的实际作用。
   单 boot CPU 起步；描述八核拓扑不代表本关启动所有核心。
   当前 OS profile 不提供 `sleep-disabled=1`，需确认有效的禁用休眠配置进入最终 ADT。

出口：有效的固件 FDT、可检查的 ADT、内存区间和保留区审计；生成器成功只算主机证据。
完整 UFS/显示/触摸节点按后续阶段补齐，不阻塞最小 CPU 路径。

## 2.2：准备可追溯的最小 XNU

工作：

1. 保持 `ipados-17.7.11-21H461`，目标 `iPad7,1 / j120ap`，使用同一目标 IPSW。
   按 OS profile 核对 kernelcache 与 ABI 输入：XNU `10063.141.1`、
   DriverKit `xnu-10063.121.3`、TrustCache `xnu-8796.101.5`。
   kernelcache 预期 SHA-256 为
   `f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7`。
2. 准备源码、SDK/工具链和归档依赖，核对最终配置为 4 KiB、平台/CPU 组件齐备。
   在 macOS 构建 XNU 需要核对完整 Xcode/SDK；阶段 1 LLVM 固件构建成功不足以证明可构建 XNU。
3. 按共享流程完成 kernel、link、prelink，保留配置、源码提交、命令、日志、符号和
   `kernel.macho` 哈希；为最终内核生成对应 `.adt`。
4. `UniXNU-piano` 参考预链接内核可用于隔离实验，但须检查其来源、配置和加载协议。
   旧文档的参考哈希
   `6912319adf0b623eb04987f2dbd29c4b5c9f97ca18b469571bd67c7815c86c07`
   不是 elden 兼容性证据；最终交付应有可复现的目标内核输入。

出口：内核/ADT 大小和哈希明确、ABI 与 prelink 一致，有可复现构建记录及符号。
此时据实际文件大小计算 FAT 元数据、对齐和余量，确定载荷尺寸，不先拍定 64 MiB。

## 2.3：先证明大载荷 RAM 通道

首选调查当前共享实现的路径，**该路径在 elden 尚未验证**：

```text
Android v3 ramdisk（FAT）
  → ABL 在固件 FDT 写入 /chosen/linux,initrd-start/end
  → BootShim / Mu SEC 保留 FDT 与 initrd
  → 入口参数 HOB 保存 FDT 地址（DAEE82E6-8090-4E72-BFB9-78C13CD4E359）
  → UniXNURamDiskDxe → DiskIo / FAT → UniXNU 配置与载荷
```

工作：

1. 审查 Lenovo ABL、BootShim、SEC 的实际传参和内存保留；上游有实现不代表本机通道成立。
   先用小配置/校验数据，再用接近最终载荷大小的数据验证完整性，不急于执行内核。
2. 在阶段 2 专用固件配置的 DSC/FDF 接入共享 `UniXNURamDiskDxe`、`HobLib`、`FdtLib`、
   DiskIo/FAT 与 collation 依赖；按实际介质布局决定是否需要 PartitionDxe。
   驱动必须在 UniXNU 读取配置前可用，避免同名卷造成配置来源不确定。
3. 优先保持 4 MiB FD 和 BootShim 基址 `0xFF300000`，评估把内嵌大载荷移出 FV。
   每次重新测量内外 FV、模块清单、解压容量和内存交叠，超限应构建失败。
   如必须扩大 FD，先重算 BootShim 的 FD_SIZE、加载窗口和所有区间。
4. 核对 Android v3 header（1580 字节）、页对齐、kernel/ramdisk 偏移、gzip 与 FDT 尾部。
   当前 shim 为 112 字节；任何变更均需按实际产物复核，不能沿用旧尺寸假设。
5. 所有者对同一通道测试镜像进行两次冷 RAM 启动，证明近最终尺寸 FAT 可读、数据一致、
   配置/菜单/按键可用，重启仍能进入原厂 Android。

出口：大载荷从 boot image 到 UEFI 文件系统的路径有主机及实机证据。
如 initrd/FDT/HOB 交接失败，停在本关修复桥接；其他 RAM 方案需要重新做容量与内存设计。
阶段 1 的内嵌载荷构建路径继续保留；不以持久分区作为替代通道。

## 2.4：验证 DarwinBoot 输入与拒绝路径

工作：

1. 将内核和对应 sidecar 放进 `EFI/UniXNU/Payloads/`；菜单保留 `Return to firmware`，
   手动选择 `xnu`，逐项核对最终参数。`xnu` 项的 `dtb` 应为空，不把固件 FDT 当作 ADT 传入。
2. 用 QEMU/fixture 检查缺失 ADT、非法 Mach-O、占位符不匹配等拒绝路径。
   这些测试覆盖菜单和加载器逻辑，不算 SM8750 硬件验收。
3. 检查最终 boot image 中的内核、ADT、FAT 与输入逐字节一致，模块齐全且不重新引入
   阶段 1 已移除的崩溃 `UFSDxe`；记录最终 image/FD/载荷/内核/ADT 哈希。
4. 实机记录 loader 版本、EL1、内核 VA/PA/entry、boot_args、内存窗口、GOP 信息和最后检查点。

以下日志均发生在内核执行之前，仅作为本关证据：

```text
DARWINBOOT: loader v2 installed EL1
DARWINBOOT: inputs validated; exiting boot services
```

出口：加载器输入、退出 boot services 前的边界和拒绝行为可解释。
两条日志不能证明 XNU 入口、平台专家或 `ArmCpu` 已运行。

## 2.5：XNU 入口、平台专家与 boot CPU 实机验收

按顺序保存证据：

| 检查点 | 应收集的证据 | 不足以证明的情况 |
| --- | --- | --- |
| XNU 入口执行 | 已知位置的入口探针，随后内核版本/参数或可定位执行轨迹 | 仅有 DarwinBoot 日志 |
| 平台专家 | `ArmDTPlatform` 匹配及所需 ADT 属性被消费的日志/符号位置 | 仅有入口色条或任意 panic |
| boot CPU | `ArmCpu` 初始化、自身 redistributor 映射及 GIC/定时器诊断计数 | 仅有八核拓扑或 PSCI 节点 |
| 后续交接 | 已知根卷等待或后续 provider 失败，能够定位停点 | 无输出黑屏/复位 |

先建立可见的探针/日志链，再追踪内核问题。若需 panic renderer，应作为独立实现与校验项，
不能把当前 `panic_screen = false` 当作已集成。出现故障记录最后成功检查点、模块、
provider、PC/LR、符号解析和画面/日志，区分入口前失败、平台失败与后续依赖失败。
IPI/SMP 在 boot CPU 稳定后另立关卡，不扩大本轮最低验收范围。

出口：**同一最终镜像至少两次冷 RAM 启动通过入口、平台专家和 boot CPU 检查点，
停在相同可解释阶段，随后原厂 Android 正常启动。** 镜像哈希变化需重新计数。
若仅到达入口或出现早期 panic，保留结果并回到对应关卡，不标记阶段 2 完成。

## 主机检查与实施记录

以下命令在设备仓根目录执行，使用独立当前主仓，不重建固件：

```sh
PYTHON="$PWD/.venv/bin/python"
UNIXNU_DIR="$PWD/.cache/phase2-plan/UniXNU"

shasum -a 256 out/elden-phase1.img out/SILICIUM_UEFI.fd
"$PYTHON" "$UNIXNU_DIR/unixnu" defconfig elden_defconfig -D "$PWD"
"$PYTHON" "$UNIXNU_DIR/unixnu" tree -D "$PWD"
"$PYTHON" "$UNIXNU_DIR/unixnu" status --json -D "$PWD"
"$PYTHON" "$UNIXNU_DIR/scripts/porting-record.py" check --device "$PWD"
dtc -I dts -O dtb -i soc/sm8750/dts -o /tmp/elden.dtb dts/elden.dts
"$PYTHON" scripts/make_payload.py --verify-only
"$PYTHON" scripts/verify_artifact.py --fd out/SILICIUM_UEFI.fd --image out/elden-phase1.img
```

`UNIXNU_DIR` 可改为其他已核对提交的当前主仓。`.cache/` 是本机缓存，不随仓库分发。
首次 `tree` 会初始化共享组件子模块并访问网络；如 `status` 提示组件补丁缺失，先完成此步。
`tree` 成功只证明组件源码树可组装，不代表 XNU reference、SDK、kernelcache 或 ABI 输入齐备。
准备内核构建时执行所需的 `unixnu fetch`，检查网络依赖、源码与 lock 差异后再构建。
主机静态通过不证明当前哈希已有实机验收，也不证明阶段 2 可启动。

### 本轮主机检查（2026-10-25）

| 检查 | 结果 |
| --- | --- |
| defconfig / tree / status | 通过；四层 profile、5 个组件和 56 项补丁可解析，报告在本机 `.cache/phase2-plan/status.json` |
| porting-record check | 通过，检查 13 个 area；不提升任何实机支持状态 |
| make_payload --verify-only | 通过，现有内嵌 FAT 与配置匹配 |
| verify_artifact | 通过，Android v3、112 字节 shim、4 MiB FD、所需模块齐全且无 UFSDxe |
| DTS 编译 | 通过；`dtc 1.8.1-gf99e3af0` 生成 1,557 字节 DTB，SHA-256 为 `60316b6d4e753610610126d691f6d39ba54edd21e9b02875ec034e81e27a4371` |
| 阶段 1 重建 | 通过；新 image 为 `94b6a6315b04fc9d276bc15e9519107be292244380fc3bf139f5af6c96a3bb0a`，FD 为 `e5420517d55f4b638c07617a252d3a65c95cfb731584dcb10dd1d98bae412580` |
| 镜像/FD 哈希 | 与历史实机验收值不同；新候选已由所有者完成两次 RAM 冷启动 |

重建未覆盖历史验收文件，因为这些文件已不存在；旧本地候选先被只读保存。
设备证据仅覆盖阶段 1 UniXNU 菜单，不包含 XNU 入口、平台专家或硬件 provider。

每关向 `porting.toml` 对应 area 追加证据：源码依据、主机命令/结果、实机镜像哈希/时间/
最后检查点分别记录。阶段 2 实施后的报告应包含各产物大小、哈希、内存区间、FV 用量、
工具链/源码提交、ADT 摘要与两次设备测试结果；不要预填成功状态。

本轮依据 UniXNU 主仓 `16e592abee8a550dec8154ed1f38b5ebc4f16213` 的
`docs/zh/porting/steps.md`、`device-repository.md`、`device-tree.md`、`uefi-firmware.md`、
`bring-up.md`，以及组件目录、设备树匹配、XNU 源码与补丁、prelink、payload、building
和目标 OS profile 重新规划。官网读取返回 403 时，核对的是官方 GitHub 仓同一提交的文档源码。
迁移细节见 [FORMAT2-MIGRATION.md](FORMAT2-MIGRATION.md)。

## 设备操作与提交边界

设备测试仅由所有者手动执行 `fastboot boot <image>`。不增加启动自动化，不刷写、擦除、
格式化、切换槽位或修改 GPT。不提交设备标识、熵种子、trust cache、Data seed、备份或密钥。
