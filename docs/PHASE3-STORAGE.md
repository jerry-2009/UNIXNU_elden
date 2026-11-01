# 阶段 3 存储：SM8750 UFS 只读探针

状态：**进行中（Stage 1 完成，尚无设备证据）**。

阶段 2.5 的内核侧目标已达成：v51（`cc739804217c3277bb07e4ce967381d5e1dd970eb46e9bb6637ebb83c5c668be`）
跑完 `Entry.S`、`arm_init`、全部 `kernel_startup_initialize_upto` 阶段、`_bsd_init`、
IOKit 与 kext 装载，跳过 AMFI 的 developer-mode latch，停在反复打印的
`Waiting on <dict … IOProviderClass … IOMedia … Apple_HFS …>`。它等的就是本阶段要造的
块设备。

## 目标与验收判据

**目标**：XNU 用 NativeUfs 驱动在 elden 上完成只读存储探针——读到 UFS 控制器、
GCC/SMMU 状态与 LUN0 几何，但不发布根设备、不写任何一个扇区。

**验收**：设备 RAM-boot 探针镜像后，console 打出 `NATIVE_UFS` 诊断链路
（GCC UFS GDSC/branch 状态 → 控制器 HCS/UTRL 就绪 → LUN0 READ CAPACITY = 4096 字节块），
无 panic、无超时死等。这与 v51 形成对照：v51 是没有 UFS 驱动，本阶段是驱动能读控制器。

**非目标**：发布根卷、`native-ufs-root=1`、PMGR 集成、QMP PHY 与 RPMh 时钟驱动、
读写 userdata、改 GPT、切槽位、刷写。

## 硬件清单（来自同机型 Linux 设备树）

参考来源：`https://github.com/h0cheung/tb322fc-linux-kernel`，本仓库 `.cache/audit/`
里钉在 `bf96c3d4048973298ede78487177c6f1b4f6bc0f`；
`arch/arm64/boot/dts/qcom/sm8750-lenovo-elden.dts`（2471 行）与
`sm8750.dtsi`（8051 行）。分发包仓库
`https://github.com/h0cheung/tb322fc-linux`（`c1fecc6`）只有打包与支持矩阵，
不含驱动代码。

| 资源 | 值 | Linux 出处 |
| --- | --- | --- |
| UFS 控制器 | `ufs@1d84000`，reg `0x1d84000`+`0x3000` | `sm8750.dtsi:5948` |
| 控制器 compatible | `qcom,sm8750-ufshc`、`qcom,ufshc`、`jedec,ufs-2.0` | 同上 |
| 控制器中断 | `GIC_SPI 265`，`IRQ_TYPE_LEVEL_HIGH` | 同上 |
| QMP PHY | `phy@1d80000`，reg `0x1d80000`+`0x2000`，`qcom,sm8750-qmp-ufs-phy` | `sm8750.dtsi:5925` |
| ICE | `crypto@1d88000`（`qcom,ice`），控制器以 `qcom,ice` 引用 | `sm8750.dtsi:2135` |
| HC 时钟（8 个） | `GCC_UFS_PHY_AXI_CLK`、`GCC_AGGRE_UFS_PHY_AXI_CLK`、`GCC_UFS_PHY_AHB_CLK`、`GCC_UFS_PHY_UNIPRO_CORE_CLK`、`RPMH_LN_BB_CLK3`、`GCC_UFS_PHY_TX_SYMBOL_0_CLK`、`GCC_UFS_PHY_RX_SYMBOL_0_CLK`、`GCC_UFS_PHY_RX_SYMBOL_1_CLK` | `sm8750.dtsi:5948` |
| PHY 时钟（3 个） | `RPMH_CXO_CLK`、`GCC_UFS_PHY_PHY_AUX_CLK`、`TCSR_UFS_CLKREF_EN` | `sm8750.dtsi:5925` |
| 复位 | `GCC_UFS_PHY_BCR`（控制器），PHY 侧 `resets = <&ufs_mem_hc 0>` | 同上 |
| 电源域 | `GCC_UFS_PHY_GDSC`（控制器）、`GCC_UFS_MEM_PHY_GDSC`（PHY）、`rpmhpd_opp_nom` | 同上 |
| SMMU | `apps_smmu`，UFS 流 `0x60`，`dma-coherent` | 同上 |
| 通道 | `lanes-per-direction = <2>` | 同上 |
| 供电 | PHY `vreg_l1j_0p91`(0.91 V)、`vreg_l3g_1p2`(1.2 V)；HC `vreg_l17b_2p5`(2.5 V, 1.3 A)、`vreg_l1d_1p2`(1.2 V, 1.2 A) | `sm8750-lenovo-elden.dts:2389-2404` |
| 复位 GPIO | `tlmm 215`，低有效 | 同上 |

Linux 侧支持矩阵（`docs/hardware.md`）：UFS 在 Linux 7.2.6 下配合 F2FS 可用，
说明控制器/PHY 在 elden 板上是好用的；这不等于 XNU 已经有驱动。

## 设备树改动与 ADT 影响

`Stage 1` 在 `soc/sm8750/dts/sm8750.dtsi` 增加 `ufs_mem_hc`、`ufs_mem_phy`
两个节点（默认 `status = "disabled"`），由 `dts/elden.dts` 打开。只写
ADT 生成器会导出的属性：`reg`、`compatible`、`interrupt-parent`/`interrupts`、
`dma-coherent`、`unixnu,adt-name`。`clocks`/`resets`/`power-domains`/`iommus`
等引用属性暂不写——`scripts/unixnu/devicetree.py` 的
`hardware_properties()` 只导出白名单，引用型属性要求 provider 节点存在且启用，
否则被静默丢弃；provider（GCC、RPMh、TCSR、SMMU、TLMM、PMIC）尚未在本 source 中描述。

导出后 `arm-io` 窗口按 `arm_io_window()` 的规则变化：

| | 窗口 base | 窗口 size | `intc` reg | `ufshc` reg | ADT 大小 |
| --- | --- | --- | --- | --- | --- |
| 阶段 2.5 | `0x16000000` | `0x1000000` | `0x0`/`0x10000` | — | 13,152 B |
| 本阶段 | `0x1000000` | `0x16000000` | `0x15000000` | `0xd84000` | 13,624 B |

原因是 UFS 块（`0x1d80000`/`0x1d84000`，约 30 MiB）位于 GIC（`0x16000000`，369 MiB）
之下，16 MiB 对齐后的最小地址变成 `0x1d80000`，于是窗口 base 落到 `0x1000000`。
窗口只是 ADT 的地址基准，子节点 `reg` 以偏移导出；`ArmDTPlatform` 按子节点发布
nub、由 `IOPlatformExpert::getNubResources` 用 `ranges` 换算，不整体映射窗口。

## 驱动现实（ShengUfs / NativeUfs）

- 复用 catalog 的 `ShengUfs`（钉 `e2b32cc429e8cf1501161c1d8c517f8994ceb9b2`）加上
  OnePlus Ace 5 Pro（`hummer`，同 SM8750、同 21H461 IPSW）的
  `patches/native-ufs-sm8750.patch`。这份 1233 行补丁包含 SM8750 的 GCC 分支偏移
  （`0x77028`/`0x7702c`/`0x77030`/`0x7706c`/`0x7707c`/`0x770bc`/`0x770d8`/`0x770f0`）、
  `static_assert(UFS_HC_BASE==0x1d84000 && UFS_HC_SIZE==0x3000)`、8 个 LUN 的
  READ CAPACITY(10) 发现、`hostWakeLink`（清 AHIT8 + Hibern8 退出）重试，
  以及 SM8750 专用根分区名 `UFS_ROOT_PARTITION "unixnu"`。
- 驱动**不读设备树**：控制器 `0x1d84000`、GCC `0x100000`、SMMU `0x15000000`、
  流 `0x60` 都是 C++ 常量。`NativeUfs::inspect` 只读 GCC 的 UFS-MEM-GDSC 寄存器
  （`GCC_BASE + 0x9e000`），源码注明 "No write is performed by NativeUfs yet"——
  时钟、复位、RPMh 与 QMP PHY 全部假定由平台/固件完成。
- 匹配方式：`NativeUfs::probe` 的第二个 personality
  （`IOMatchCategory NativeUfsRoot` + `IOPlatformDevice`/`IOPlatformExpertDevice`）
  无条件挂到平台专家上，**不需要** DT `compatible` 匹配；第一个 personality 才要求
  provider 的 `compatible` 含 `"qcom,sm8550-ufshc"`。所以 elden 的节点里有
  `"qcom,ufshc"` 不影响探针路径，是否补 `"qcom,sm8550-ufshc"` fallback 由 Stage 2
  的实际匹配结果决定。
- `fastboot boot` 路径下，ABL 必须先读 `boot.img` 才能启动本镜像，因此 UFS 控制器与
  PHY 已被它拉起；"固件已完成 PHY/时钟初始化"这一假设正是探针要验证的第一件事。

## 决策

1. **复用 hummer/13T 的 SM8750 UFS substrate，不自己写驱动**：SM8750 与 SM8550 的
   UFS 基址相同，这份补丁是本 SoC 家族唯一已知可用的实现。
2. **不移植 hummer 的引擎**：只在钉住的 `16e592ab` 引擎上加 `ShengUfs` 组件与补丁，
   保住已设备验证的 phase-1/2 流水线。
3. **本阶段不写 PHY 驱动**：先验证 ABL 留下 UFS 可用；若探针显示 branch/GDSC 关闭，
   再单独评估 PHY/RPMh 初始化归属。
4. **不碰 phase 2 的 defconfig/payload**：新增 `configs/elden-ufs_probe_defconfig` 与
   `package/phase3-ufs-probe-unixnu.toml`，`elden_defconfig`、phase 2.3 payload 与
   v51 证据链保持可复现。
5. **DT 先只加生成器能导出的属性**，引用属性等 provider 齐了再补。
6. **探针阶段保留 v51 的 AMFI poke**，PMGR 集成（`sheng-pmgr=2` + `_sheng_pmgr_run`）
   留到根发布阶段。

## 阶段计划

### Stage 1（本提交，纯主机）

- `soc/sm8750/dts/sm8750.dtsi`：`ufs_mem_hc`/`ufs_mem_phy` 节点。
- `dts/elden.dts`：打开两个节点，供电与复位写入注释。
- `porting.toml` 的 `storage` 区：实盘清单、ADT 窗口变化、审计证据。
- 本文档。
- 验证：`dtc` 编译；`unixnu defconfig/status/tree`；独立生成 ADT 解码确认
  `arm-io/ufshc` 的 `reg = 0xd84000/+0x3000`、`arm-io/ufsphy` 的
  `reg = 0xd80000/+0x2000`、`interrupts = (0, 265, 4)`；`porting-record.py check`。

### Stage 2（主机，构建面 spike）—— 代码就位，主机工具链未通

代码已全部落库，但**尚未编出内核**：本机只装了 Command Line Tools，没有
Xcode/iPhoneOS SDK，XNU 内核链接所需的 `mig`/`iig`/`xcrun` 查询在 2026-11-01 这轮
调试里只推进到 XNU 编译阶段（`bsd/`、`security/`、`iokit/` 已能编译），随后卡在
汇编命令与 `sysproto.h` 生成，属于主机工具链缺口，不是仓库问题。

- `scripts/driver-patches/sheng-ufs-sm8750.patch`（37,397 B）：把 13T/hummer 的
  `patches/native-ufs-sm8750.patch` 收敛到 ShengUfs 的 8 个非测试文件
  （`GccUfs.h`、`LunDiscovery.h`、`NativeUfs.cpp`、`RootCommands.h`、
  `RootDiagnostics.h`、`RootLayout.h`、`RootQueue.h`、`SmmuTakeover.h`），
  丢掉 `tests/*` 的 8 个 hunk（对 catalog pin `e2b32cc4` 已不再适用）。
  对 `e2b32cc429e8cf1501161c1d8c517f8994ceb9b2` 做 `git apply --check` 通过。
  放在 `scripts/` 而不是 `patches/`：`scripts/unixnu/tree.py:88-90` 会把设备
  `scripts/` 整棵树复制进引擎树，构建器才能从 `ROOT/scripts/driver-patches/` 取到它；
  `tree/package` 是指向引擎 `package` 的符号链接，不能用来回指设备仓库。
- `scripts/build-sheng-ufs-probe.py`：按 catalog 取 ShengUfs 的 `repository`/`revision`，
  checkout 到 `build/sheng-ufs/src`，幂等打补丁，读
  `build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json`
  重放编译命令（换 `record['file']`、去掉 `-W` 旗标、加
  `-I .cache/xnu-work/osfmk`、`-I src`、
  `-DNATIVE_UFS_SM8750=1 -DNATIVE_UFS_READ_ONLY=1 -DNATIVE_UFS_PROBE_ONLY=1`），
  校验 Mach-O 魔数 `0xfeedfacf/0x100000c/0/1`、拒绝 `IOBlockStorageDevice` 导入，
  产出 `build/sheng-ufs/libShengUfs.a`。
- `configs/elden-ufs_probe_defconfig`：`CONFIG_XNU_BUILD_ARCHIVES=y`、
  `CONFIG_XNU_NATIVE_UFS=y`、SOURCE_CORECRYPTO14、ARM_DT_PLATFORM、ARMCPU、
  NATIVE_ARCH_TIMER、NATIVE_PAN、NATIVE_CS_HASH_CACHE、TRUST_CACHE_RUNTIME；
  不开 `SHENG_PMGR` 与 `OWNER_ROOT_*`，`CONFIG_XNU_EXTRA_LD_ARCHIVES=""`。
- `board.toml [kernel].archives`：arm64 档案列表的完整替换（只有开 BUILD_ARCHIVES 时生效），
  末项是 `build-sheng-ufs-probe.py`。`build-xnu-4k-baseline.sh:614-619` 在
  `XNU_NATIVE_UFS=1` 时强制链接 `build/sheng-ufs/libShengUfs.a`，档案不需要另配。
- `package/phase3-ufs-probe-unixnu.toml`：phase 2.5 payload 的副本，标题
  `ELDEN 3 UFS PROBE`，args 含 `-v serial=3 debug=0x14e armcpu-diagnostics=1
  -no_slto_panic security-mode-change-enable=1 amfi_get_out_of_my_way=1
  native-ufs-probe=2 native-ufs-diagnostics=1`，不含 `native-ufs-root=1`/`sheng-pmgr=2`。
- 工作目录按 defconfig 命名：`…/elden-ufs_probe/`（phase 2.5 的 `…/elden/` 不动）。

#### 主机工具链（唯一阻塞项）

阶段 2.2 在同一台只有 CLT 的机器上留下了 shim，位置
`.cache/phase2-plan/toolchain/`：`bin/xcrun`（把任何 `-sdk` 映射到 macOS SDK，但
`--show-sdk-platform-path` 返回 `xcode-iphone/Platforms/iPhoneOS.platform`，于是
`PLATFORM=iPhoneOS`、`MACH_VM_MAX_ADDRESS` 取 iOS 值）、`bin/xcodebuild`、
`iig`（源码构建的真二进制）、`xcode-iphone/`（合成 Xcode 树）。可用的环境是：

```sh
export PATH="$PWD/.cache/phase2-plan/toolchain/bin:$PWD/.venv/bin:$PATH"
export CCC_OVERRIDE_OPTIONS="+-Wno-unknown-warning-option"
.venv/bin/python .cache/phase2-plan/UniXNU/unixnu build kernel -D . -j 8
```

已踩过的坑（写在这里，避免下次重来）：新 lane 的 `tree/` 需要从 `…/elden/tree` 播种
`.cache/fakeroot`（含 `.xnu-10063.141.1-headers`）、`build/xnu/ios-obj/EXPORT_HDRS`、
`DEVELOPMENT_ARM64_BCM2837/link.filelist`（1006 行，`build-corecrypto-14.py` 缺它就拒绝）
和 1011 个 `*.json` 编译记录（`build-mockfs-fixture.py` 要 `bsd/DEVELOPMENT/vfs_conf.o.json`）；
`cmake`/`ninja` 装在 `.venv`（`pip install cmake ninja`）；`build-arm-driver.py` 自带
`-Werror -Wno-unnecessary-virtual-specifier`，Apple clang 17 会把它当未知警告，
靠 `CCC_OVERRIDE_OPTIONS` 压掉。仍余：汇编规则（`AS = $(CCACHE) $(CC)`）报
`c: command not found`，以及 `EXPORT_HDRS/bsd/sys/sysproto.h` 被重生成成 44 行残片。

**结论**：装完整 Xcode（iPhoneOS SDK）后这些 shim 全部不需要，构建与发布要求一致；
在那之前不要把 CLT 产物当发布工具链（阶段 2.2 已立此规矩）。

### Stage 3（设备，所有者 RAM-boot 探针）

- 用 `--poke` 六件套加 v51 的 AMFI poke 构建探针镜像。
- `native-ufs-probe` 从 `2` 起逐级推进，每级一张屏照，判读规则与结果写进本文证据表。
- `porting.toml` 记录 host build 与 device result 两条证据，附镜像 SHA-256。

### Stage 4（后续）

根发布需要：`sheng-pmgr=2` + `build-sheng-platform-power.py` 生成的 PMGR instrument、
`native-ufs-root=1`、`[userdata]` 实盘几何与 `root_match_volume_uuid`、
`build-verified-root-probe.py`，以及 elden 自己的 UFS 证据链（不能沿用 sheng 的
`check-ufs-preboot-evidence.py`）。这些依赖所有者提供的只读 GPT 转储，不阻塞 Stage 1/2。

## 风险

| 风险 | 应对 |
| --- | --- |
| 钉住的 `16e592ab` 引擎没有 `drivers/NativeUfs` 与 `kits/NativePrelink` | Stage 2 是 spike；若组件路径不通，退化为自写最小只读寄存器探针（只读 GCC/HCS/LUN0，不涉根） |
| ShengUfs 只认 `qcom,sm8550-ufshc` | personality 2 不依赖匹配；先不加 fallback，Stage 2 按实际结果决定 |
| SMMU takeover 与 ADT/SMMU 流所有权冲突 | 探针阶段不启用 SMMU，先只读 |
| ABL 没留下可用 UFS（branch/GDSC 关闭） | 探针会直接显示；届时再决定 PHY/RPMh 初始化归属 |
| 4 KiB LBA、LUN 数量与分区假设 | LUN 发现会打印实际 READ CAPACITY，用实测值回填 `[userdata]` |

## 限制

- 本阶段没有任何 elden 设备上的 UFS 结果；Stage 1 只能证明设备树与 ADT 正确。
- `arm-io` 窗口变大（`0x1000000`+`0x16000000`）只做过主机侧生成与解码，尚未在设备上
  用这一版 ADT 引导过；Stage 3 的第一张探针屏照同时验证这一点。
- provider 节点（GCC/RPMh/TCSR/SMMU/TLMM/PMIC）缺失，所以供电与时钟仍是注释而非属性。
- 不改 GPT、不格式化、不刷写；设备测试只有所有者执行的 `fastboot boot`。

## 证据

| 日期 | 类型 | 内容 | 结果 |
| --- | --- | --- | --- |
| 2026-11-01 | host | `dtc` 编译 `dts/elden.dts`（含新 UFS 节点） | 通过，`ufs@1d84000` reg `0x0 0x1d84000 0x0 0x3000`、`interrupts <0 0x109 4>` |
| 2026-11-01 | host | 独立生成 ADT 并解码 | `arm-io` base `0x1000000` size `0x16000000`；`ufshc` reg `0xd84000/+0x3000`；`ufsphy` reg `0xd80000/+0x2000`；ADT 13,624 B（阶段 2.5 为 13,152 B） |
| 2026-11-01 | host | `unixnu defconfig/status/tree -D .` | 通过；组件与补丁解析不变 |
