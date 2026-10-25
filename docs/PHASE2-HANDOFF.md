# 阶段 2 交接文档

更新时间：2026-10-25

状态：**阶段 1 已通过；阶段 2 尚未生成可启动 XNU 的镜像。**

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

### 2. 缺少可打包的 XNU 输入

本工作区目前没有：

- 与目标 iPadOS 17.7.11 / `21H461` 对应的预链接 `kernel.macho`；
- 该内核的 `.adt` sidecar；
- 可选的 trust cache 与 Data seed。

目标身份沿用项目分析中的 `iPad7,1`，不要更换 IPSW。若使用
`UniXNU-piano` 的预链接内核，必须记录其 SHA-256
`6912319adf0b623eb04987f2dbd29c4b5c9f97ca18b469571bd67c7815c86c07`
并重新验证它与当前设备 ADT、prelink 输入一致。

### 3. 当前载荷通道容量不足

阶段 1 的 `EldenRamDiskDxe` 只发布固件卷内的 4 MiB FAT16 镜像。预链接内核
远大于该容量，因此阶段 2 不能只把文件复制进现有 `payload.img`。

在设计新镜像前必须先确定一种符合 RAM 启动限制的载荷传递方式，例如：

- 扩大并验证 BootShim/FD 的加载窗口；
- 从 Android boot image 的独立数据区传递载荷；
- 在 UEFI 内解压更小的封装载荷；
- 其他不写分区、不改 GPT 的只读发布路径。

不得以修改 Android `userdata`、`modem_a` 或其他持久分区作为默认捷径。

### 4. 内层 FV 几乎已满

阶段 1 `FVMAIN` 只剩 920 字节。阶段 2 增加驱动或数据前必须调整 FV 布局，
并把容量检查加入构建失败条件。

## 推荐实施顺序

1. 使用当前 `board.toml` 的格式 2 配置，核对 SKU DRAM 窗口、CPU/GIC/timebase、
   本机生成的 `unique-chip-id` 和阶段 2 内核参数。
2. 编译 `dts/elden.dts`，用 UniXNU 共享 ADT 生成器校验 `/chosen`、
   `/cpus`、`/psci`、`/arm-io`、`/defaults`、`/options` 和 NVRAM proxy；
   补齐真实内存保留区后再加入 UFS、显示与触控节点。
3. 取得并校验预链接 `kernel.macho`，生成对应的 `kernel.macho.adt`。
4. 解决大载荷的只读传递通道，并把文件放进
   `EFI/UniXNU/Payloads/`。
5. 在 `unixnu.toml` 增加 `xnu` 菜单项，但不移除 `Return to firmware`。
6. 先使用 QEMU fixture 验证 ADT、菜单项和 DarwinBoot 拒绝路径，再生成设备
   RAM 镜像。
7. 设备所有者只执行 `fastboot boot`，先确认 DarwinBoot 日志；出现 panic 时
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
