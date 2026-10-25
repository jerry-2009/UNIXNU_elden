# 阶段 2 交接文档

更新时间：2026-10-25

状态：**阶段 1 已通过；阶段 2 已生成并静态校验主机镜像，尚未实机 RAM
启动。**

格式 2 迁移后，板级 ADT 输入由 `dts/elden.dts`、`soc/sm8750/dts/`
和 `board.toml` 的 `[payload.adt]` 共同提供。共享生成器替代了原来的
设备专用 `make-elden-adt.py`。迁移范围和未完成硬件输入见
[`FORMAT2-MIGRATION.md`](FORMAT2-MIGRATION.md)。

## 目标

从阶段 1 已验证的 UniXNU 菜单进入 DarwinBoot，并让 4 KiB XNU 到达内核入口
和平台专家。阶段 2 的最低可见证据是：

```text
DARWINBOOT: loader v2 installed EL1
DARWINBOOT: inputs validated
```

允许继续为明确的缺失 provider panic 或控制台输出，而不是无输出死机。阶段 2
不要求挂载 iPadOS 根卷，也不要求进入用户态。

## 阶段 1 基线

通过实机验收的镜像：

```text
out/elden-phase1.img
b56ef4b7e5a71382b8c279c4ee1560764fabd126ba37ac0fd6e495c80b9ec6e1
```

该镜像只包含 `Return to firmware` 菜单项，不包含 `xnu` 载荷。阶段 2 必须
建立新的可测试镜像并重新记录哈希，不能把它与阶段 1 镜像混用。

## 已确认的板级数据

以下数值来自同一台 `elden` 上运行的 Linux、`elden-linux` 记录和 SM8750
平台资料：

| 项目 | 数值 |
| --- | --- |
| SoC | SM8750P |
| DRAM base | `0x80000000` |
| GIC distributor | `0x16000000`，大小 `0x10000` |
| GIC redistributors | `0x16080000`，大小 `0x200000`，stride `0x40000` |
| timebase | `19,200,000 Hz` |
| CPU MPIDR affinity | `0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x10000, 0x10100` |
| UFS host / PHY | `0x1d84000` / `0x1d80000` |
| panel | 1904×3040，bonded dual-DSI + DSC |

不得把序列号、唯一芯片 ID 或完整备份信息提交到仓库。`unique-chip-id`
应在本机生成或从设备安全读取，只写入本地构建输入。

## 当前阻塞项

### 1. 固件 DTB 仍是占位文件；XNU 硬件树只覆盖首个里程碑

`third_party/mu_wide_platforms/Platforms/PakalaPkg/Device/lenovo-y700g4/`
`DeviceTreeBlob/Linux/linux-y700g4.dtb` 仍为 6 字节 `dummy`。格式 2 的
`dts/elden.dts` 已提供 CPU、GIC、定时器、PSCI 和 2 GiB 连续 DRAM
窗口，但它不是完整硬件树。阶段 2 仍需从设备 `/sys/firmware/fdt` 或可复现的
`elden` Linux DTB 取得完整内存、保留区、UFS、显示和触控输入。

### 2. XNU 输入仍未纳入仓库或固定构建

阶段 2 主机镜像目前使用公开 CI 产出的预链接内核：

- 内核 SHA-256：
  `6912319adf0b623eb04987f2dbd29c4b5c9f97ca18b469571bd67c7815c86c07`；
- 上游 `UniXNU-piano` Run #23 的工件 ZIP 摘要：
  `87be3e891b25a6af894fec6e37c2134bbba1c30d77fe9bb9be8c8c1bc9cde6f6`。

该二进制只作为主机验证输入，不提交到设备仓。正式构建仍需固定可审计的
kernelcache、ABI、patch 和 prelink 输入。目标身份继续沿用 `iPad7,1`。
当前镜像没有 trust cache 和 Data seed。

### 3. 大载荷通道已实现，待实机确认

阶段 2 使用 UniXNU 共享 `UniXNURamDiskDxe`，从 ABL 输入 FDT 的
`linux,initrd-start/end` 发布启动镜像 ramdisk。载荷为 64 MiB FAT 卷，
包含预链接内核和 ADT sidecar。Android v3 镜像已通过静态逐字节校验。

下一步仍必须由设备所有者用 `fastboot boot` 验证 ABL 是否保留完整 ramdisk
范围，并确认 UniXNURamDiskDxe 能发布该卷。不得把结构校验通过当作设备可用。

### 4. 内层 FV 几乎已满

阶段 2 `FVMAIN` 为 14,213,120 字节，其中已用 14,211,096 字节，只剩
2,024 字节。继续增加模块前必须调整 FV 布局，并把容量检查保留为构建失败
条件。外层 `FVMAIN_COMPACT` 仍有 1,472,240 字节余量。

## 推荐实施顺序

1. 使用本机 `unique-chip-id` 重新运行 `scripts/build_phase2.py`，生成设备
   可用而非 `--test-seed` 的镜像，并复核全部哈希。
2. 先使用 QEMU fixture 验证 ADT、菜单项和 DarwinBoot 拒绝路径。
3. 编译 `dts/elden.dts`，用 UniXNU 共享 ADT 生成器校验 `/chosen`、
   `/cpus`、`/psci`、`/arm-io`、`/defaults`、`/options` 和 NVRAM proxy；
   补齐真实内存保留区后再加入 UFS、显示与触控节点。
4. 设备所有者执行一次 RAM 启动，优先确认 `UNIXNURAMDISK` 与 DarwinBoot
   日志；同一镜像再重复一次冷启动确认结果稳定。
5. 设备所有者只执行 `fastboot boot`，先确认 DarwinBoot 日志；出现 panic 时
   记录模块、provider、PC 和最后画面。

## 验收

- 同一镜像两次 RAM 冷启动到达相同 DarwinBoot/XNU 阶段；
- DarwinBoot 打印 loader 版本、EL1、内核地址和 framebuffer 信息；
- ADT 至少包含平台专家要求的全部节点；
- 内核入口被执行，或出现可定位的缺失 provider panic；
- 退出后原厂 Android 正常启动。

## 安全边界

- 只允许 `fastboot boot <image>`。
- 禁止 `fastboot flash`、`set_active`、`erase`、`format`、分区或 GPT 修改。
- 不把唯一设备身份、序列号、完整备份或密钥提交到仓库。
- 构建脚本继续不得调用 `fastboot`。
