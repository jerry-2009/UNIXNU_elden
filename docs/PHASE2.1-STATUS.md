# 阶段 2.1 状态：FDT、ADT 与内存交接

更新时间：2026-10-25

状态：**阶段 2.1 的主机审计完成。已采集设备 live FDT 并完成固定源码重建、
固件 RAM／保留区交叉检查、XNU ADT 生成与独立解码、boot CPU/GIC/定时器检查和
参数语义审计。
尚未执行阶段 2 镜像的实机启动。**

阶段 2.1 不改变 `board.stage = 1` 或 `kernel.status = "phase-2-pending"`。
这里的主机结果不证明 XNU、DarwinBoot、存储、显示或触控在设备上运行。

## 结论

原先 `[0x80000000, 0x100000000)` 的 2 GiB 范围不是可用交接区。它与固定 Linux
树中的 44 个 `no-map` 保留区相交，包括 `gunyah-hyp`、`smem`、DSMP、
modem、CDSP、ADSP、camera、ramoops 和 GOP splash。该范围已从 XNU 硬件树移除。

随后检查的 `[0xA8000000, 0xB8000000)` UEFI `Kernel` carveout 也被 live FDT
排除：ABL 把当前 Android ramdisk 放在
`[0xB74AC000, 0xB7FFEE30)`，与窗口尾部相交。该区间也没有作为 RAM-boot 阶段 2
的交接窗口。

当前最小 XNU 交接窗口为：

```text
[0xC2400000, 0xD2400000)  256 MiB
```

它同时满足以下条件：

- 位于 live 12 GiB FDT 的 `[0xB81C0000, 0xD4E23000)` RAM 范围内；
- 避开 live FDT 的全部 `reserved-memory` 和上述 initrd；
- 位于 elden UEFI `PlatformMemoryMapLib` 的 conventional `DXE Heap`；
- 与 GOP framebuffer `[0xFC800000, 0xFF300000)` 和 UEFI FD
  `[0xFF300000, 0xFF700000)` 分离。

## 固件 FDT

设备所有者通过 Android Studio SDK `adb` 以 root 只读采集
`/sys/firmware/fdt`。原始文件只保存在本机 `.cache/device/elden-live.fdt`：

| 项目 | 结果 |
| --- | --- |
| live FDT | 885,861 字节 |
| live FDT SHA-256 | `8a653a3e790f29bf2b0f3545135f06fe771360f31da3d37c04f648c26b95e26e` |
| 根 compatible | `qcom,sun-qrd`, `qcom,sun`, `qcom,sunp`, `qcom,qrd` |
| elden 标记 | `qcom,mdss_dsi_elden_nt36523_csot_3k_dsc_vid` 和 non-3K variant |
| 显示 | Android physical size 1904×3040 |
| UFS | `soc/1d84000.ufshc` |
| RAM | 约 11.19 GiB 可用区间，对应市售 12 GiB SKU |
| live initrd | `[0xB74AC000, 0xB7FFEE30)` |

刷机后的 vendor boot 把根 compatible 改写为通用 QRD/Sun 字符串，但 FDT 中仍有
elden 面板配置，显示、UFS 和低地址内存图也与 elden 一致。审计脚本要求通用 Sun
树同时包含 elden 标记，不能仅凭被改写的产品属性接受其他设备。

固定 Linux 源树仍用于完整候选重建和 16 GiB 变体验证：

```text
h0cheung/tb322fc-linux-kernel@6f97250ead155fc3b980856323e99a4623dae73d
arch/arm64/boot/dts/qcom/sm8750-lenovo-elden.dts
```

| 项目 | 结果 |
| --- | --- |
| 完整候选 FDT | 142,699 字节 |
| 完整候选 FDT SHA-256 | `e74bd077cb90b8255de6133dc08322e935fb6157b4dc9ebbec341ac854a8c136` |
| RAM 范围 | 14 个非空 bootloader 填充区间，代表 16 GiB 变体 |
| 保留区 | 固定源码中的全部 `reserved-memory` 区间 |
| GOP | `0xFC800000`，`0x02B00000` 字节，1904×3040，stride 7616，`a8r8g8b8` |
| initrd | 候选源码无 initrd；当前 live 值来自设备采集 |
| 原始现场 FDT | 不提交；仅保存在本机 `.cache/device/` |

仓库还提交了脱敏、可独立编译的资源描述
[`dts/elden-firmware-memory.dts`](../dts/elden-firmware-memory.dts)。它记录当前
12 GiB live 内存图、保留区和预期 framebuffer，但不冒充原始 FDT。该文件当前生成
3,925 字节 DTB，SHA-256 为
`03741bb6ddd72b3bef9162ee1d4d1be62abb378b63f304ab3006023b0383b4fd`。

阶段 1 固件中的
`DeviceTreeBlob/Linux/linux-y700g4.dtb` 仍由原验证构建保留为 6 字节 `dummy`。
阶段 2.1 没有覆盖阶段 1 固件或 RAM 启动基线。

## 硬件树与 ADT

`dts/elden.dts` 当前生成 1,557 字节硬件 DTB，SHA-256 为
`805c7b06228aa9398d564a843bbe890c865d905d1d2b8b970c33659f8df72cd4`。
共享 `unixnu.devicetree.generate()` 生成 13,152 字节 ADT。ADT 包含 64 字节随机
种子，因此跨次生成的 SHA-256 和 CHRP NVRAM 校验值本来就不固定；应审计每次
`audit.json` 指向的实际 ADT，而不是把某次哈希当成稳定构建值。
该主机审计使用非设备的 `unique-chip-id=1`，只用于结构验证，不能作为最终身份输入。

独立 ADT 解码检查通过：

| 检查项 | 结果 |
| --- | --- |
| `/chosen` | DRAM `0xC2400000 + 0x10000000`；64 字节 seed；CHRP NVRAM 8 KiB |
| DarwinBoot | `darwinboot-memory-size = 0x10000000` |
| `/defaults` | `sleep-disabled = 1` |
| `/options` | 存在 |
| `/chosen/memory-map` | 无可选输入时不包含 RAMDisk、PackedRAMDisk、TrustCache 或 GPU addon 占位符 |
| `/cpus` | 8 个 MPIDR：`0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x10000, 0x10100` |
| 启动 CPU | 只有第一个 `cpu0` 为 `running`；其余为 `waiting` |
| 定时器 | 19,200,000 Hz |
| PSCI | `smc` |
| GIC | distributor `0x16000000`；redistributor `0x16080000`；stride `0x40000` |
| `/arm-io` | 基址 `0x16000000`，窗口 `0x01000000`；`intc` 使用小端 u64 地址/长度对 |
| 产品身份 | 选中 OS profile 的 `iPad Pro (12.9-inch) (2nd generation)` |

## 地址与生命周期

| 区间 | 地址／大小 | 生命周期与归属 | 当前证据 |
| --- | --- | --- | --- |
| Android boot image source | 由 ABL 决定 | ABL 加载 Android v3 kernel 字段 | 未在静态镜像中声明物理地址 |
| BootShim | 镜像内 112 字节源流 | 复制 FD 到固定基址后跳转 | 阶段 1 静态检查 |
| UEFI FD | `0xFF300000 + 0x00400000` | BootShim／Mu SEC 到退出 boot services | BootShim 编译常量，阶段 1 已验证 |
| UEFI BootServices allocation | `0xB90C0000 + 0x1D500000` 静态候选 | UEFI `DXE Heap`，具体碎片由分配器产生 | UEFI 源表，非本次现场 map |
| initrd | live：`0xB74AC000 + 0x00B52E30` | ABL 写入 `/chosen`；Mu SEC/HOB 保留待 2.3 | 本次 Android live FDT |
| GOP framebuffer | `0xFC800000 + 0x02B00000` | UEFI GOP 到 DarwinBoot/XNU 视频交接 | 固定 FDT 与阶段 1 显示证据 |
| XNU 候选窗口 | `0xC2400000 + 0x10000000` | XNU 连续窗口；UEFI `DXE Heap` conventional memory | live FDT、initrd、UEFI map 与保留区交叉检查 |
| ADT | DarwinBoot 分配窗口内，位于 boot args 后一页 | 启动级，DarwinBoot 持有并复制 | 运行时地址须从 loader 日志记录 |
| boot args | DarwinBoot 窗口内，kernel segments 后按 16 KiB 对齐 | 启动级，DarwinBoot 构造 | 运行时地址须从 loader 日志记录 |

UEFI 静态源表只用于设计审计。退出 boot services 前必须再与设备实际 memory map
比较；`DXE Heap` 的连续静态范围不能证明运行时仍是一整段。

## CPU 与启动参数

启动参数保持：

```text
-v serial=3 debug=0x14e boot-progress=2 armcpu-diagnostics=1 -no_slto_panic
```

`armcpu-spi-ipi=1` 已从最低 boot CPU 里程碑移除。该参数的实现会为每个逻辑 CPU
预置软件 SPI 1008–1015，并依赖“`ICC_SGI1R_EL1` 不投递 SGI”的板级假设；当前
没有 elden 证据支持该假设。最低里程碑不启用 `sheng-smp=1`，因此先只注册 boot
CPU，不把八核拓扑描述误报成 SMP 已启动。SPI IPI、SGI 投递和 secondary CPU
留到 boot CPU 通过后的独立检查点。

`sleep-disabled=1` 已进入最终 ADT 的 `/defaults`，避免在 suspend 未实现时让
CPU 停驻。UEFI 电源域、RPMh 所有权和实际停核行为仍需设备证据。

## 复现

使用固定 Linux 源树和当前 UniXNU 主仓：

```sh
.venv/bin/python scripts/phase2_1_audit.py --linux-dir .cache/elden-linux
```

只检查仓库内脱敏资源：

```sh
.venv/bin/python scripts/phase2_1_audit.py
```

审计输出位于 `.cache/phase2.1/`，包含 `firmware-linux.dtb`、`hardware.dtb`、
`kernel.macho.adt` 和 `audit.json`。这些主机产物不覆盖 `out/elden-phase1.img`。

当前已用 Android Studio SDK `adb` 采集现场 `/sys/firmware/fdt`，原文件只保存在
本机。现场审计命令为：

```sh
ADB=/Users/jerry/Library/Android/sdk/platform-tools/adb
"$ADB" shell "su -c 'cp /sys/firmware/fdt /data/local/tmp/elden-live.fdt && chmod 0644 /data/local/tmp/elden-live.fdt'"
"$ADB" pull /data/local/tmp/elden-live.fdt .cache/device/elden-live.fdt
"$ADB" shell "su -c 'rm -f /data/local/tmp/elden-live.fdt'"

.venv/bin/python scripts/phase2_1_audit.py \
  --firmware-dtb .cache/device/elden-live.fdt \
  --output-dir .cache/phase2.1-live
```

本次 `audit.json` 的 `checks.firmware_fdt_was_provided_by_device` 为 `true`。
原始 FDT 可能含设备标识，禁止提交。

## 边界与下一步

- 阶段 2.1 的主机出口已满足；live FDT 已用于确认 12 GiB 内存图和 initrd 边界。
- 阶段 1 固件内的 `dummy` 没有替换，也未生成阶段 2 boot image。
- ADT 没有 root UUID、trust cache 或 Data seed 占位符，因为当前没有对应打包输入。
- 2.2 的目标 kernelcache、4 KiB XNU、prelink 和主机 ADT 已完成，见
  [PHASE2.2-STATUS.md](PHASE2.2-STATUS.md)。
- 2.3 才验证 initrd/FDT/HOB RAM 通道；2.5 才验证 XNU 入口、平台专家和 boot CPU。
