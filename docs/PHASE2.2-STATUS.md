# 阶段 2.2 状态：可追溯的最小 XNU

更新时间：2026-10-25

状态：**阶段 2.2 的主机出口已完成。目标 kernelcache、源码、补丁、4 KiB
内核、预链接产物和 ADT 已生成并审计；尚未打包启动镜像，也没有执行 DarwinBoot
或 XNU 实机启动。**

本阶段不改变 `board.stage = 1` 或 `kernel.status = "phase-2-pending"`。产物位于
独立格式 2 输出目录，阶段 1 的固件、启动镜像和 RAM-boot 基线没有被覆盖。

## 固定输入

保持 `ipados-17.7.11-21H461`、`iPad7,1 / j120ap` 和同一目标 IPSW：

```text
https://updates.cdn-apple.com/2025SpringFCS/fullrestores/122-77166/DCA6CFE8-90E9-4B92-880D-3DE171798E40/iPad_Pro_HFR_17.7.11_21H461_Restore.ipsw
```

| 输入 | 固定值 |
| --- | --- |
| XNU | `10063.141.1` / `d8b80295118ef25ac3a784134bcf95cd8e88109f` |
| Darwin | `23.6.0` |
| DriverKit | `xnu-10063.121.3` |
| TrustCache | `xnu-8796.101.5` |
| UniXNU 当前主仓 | `16e592abee8a550dec8154ed1f38b5ebc4f16213` |
| 原始 kernelcache | 46,415,872 字节 |
| kernelcache SHA-256 | `f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7` |

IPSW 产品、版本、build、device class、chip ID 和 board ID 均由 UniXNU 的
`ipsw info` 校验。原始 kernelcache 的 SHA-256 与 OS profile 中的固定值一致。

## 补丁顺序修正

实际准备内核时发现 UniXNU `16e592ab` 的 `zzz-boot-progress.patch` 包含一个依赖
`sheng-platform-power.patch` 的可选 PMGR 上下文，但 ARM64 profile 没有应用后者。
直接执行会在 `bsd_init.c` 停止。

设备仓增加
`patches/xnu/phase2.2-boot-progress-pmgr-context.patch`，只补入
`XNU_SHENG_PMGR` 编译期关闭的同一上下文，并把设备 series 放在共享 iPadOS series
之前。最终 57 个有序补丁全部应用成功；elden 没有启用 `XNU_SHENG_PMGR`。

同时，`CONFIG_XNU_BOOT_PROGRESS` 在最低 2.2 内核中关闭。当前 UniXNU 构建器要求
boot-progress、UFS、owner-root 和 Virtio 审计链同时存在，这与本阶段只验证
ArmDTPlatform/ArmCpu 的边界冲突。`boot-progress=2` 启动参数也已移除；后续完成依赖
后作为独立诊断配置启用。

## 构建结果

主机没有安装完整 Xcode/iPhoneOS SDK。为取得可检查的最小内核，本机构建使用
Command Line Tools、`iphoneos` 平台定义的 SDK 查询 shim、源码构建的 `iig` 和
单文件 firehose shim。最终 Mach-O 明确为 `arm64`、`LC_BUILD_VERSION platform 2`
和 `minos 17.0`，4 KiB TCR/部署审计通过。

这是主机输入验证，不把 Command Line Tools 代替完整 Xcode 的结果当作发布工具链
资格。正式发布或最终设备候选必须在完整 Xcode/iPhoneOS SDK 上重建并复核相同输入、
哈希来源和审计结果。

| 产物 | 字节 | SHA-256 |
| --- | ---: | --- |
| 原生 XNU | 21,206,040 | `02f216348851ba9ce70616430ff7607be9d3305cbc8b2ae1186f0e7d6b20fce7` |
| 预链接 `kernel.macho` | 54,050,816 | `65a3e799e1eb7f631a3b146dfc890ef5a8147c8fc613ee383a1665b398fb1ef9` |
| 硬件 DTB | 1,557 | `805c7b06228aa9398d564a843bbe890c865d905d1d2b8b970c33659f8df72cd4` |
| ADT 主机候选 | 13,152 | `435de6436ebc30cd2e609517fcaaae097956d7d7cbff54e788c10263195f9920` |

ADT 使用 `unique-chip-id=1` 的主机结构检查值。该值不是设备身份，也不是最终发布
输入；最终 ADT 必须由所有者本地提供唯一 chip ID 后重新生成。ADT 含随机 64 字节
seed，因此哈希本来就不是稳定构建值。

## 预链接与 ABI 审计

固定 kernelcache 与 OS profile 的 SHA-256 一致。预链接报告选择：

- 30 个可执行 Apple 组件，1 个 codeless 组件；
- 7 个 `com.apple.kpi.*` 内核接口；
- 119 个组件段范围；
- 42,532 个 kernel 指针绑定和 26,762 个 component 指针绑定；
- 30 个模块入口和稀疏索引 ABI 1；
- AMFI 早期安全初始化器
  `com.apple.driver.AppleMobileFileIntegrity=0xfffffff005ab4ae0`。

预链接报告中的 `runtime_qualified`、`abi_qualified` 和 `loadable` 按生成器语义
仍为 `false`。它们只能由后续加载和实机执行证据提升，阶段 2.2 不据此声称 ABI
运行通过。预链接 XML 由固定 XNU 标签/字符串 lexer 解析，7,730 个标签通过。

## 4 KiB 与符号检查

`audit-xnu-kernel.py` 对原生内核的结果：

```text
cpu_subtype: 0
deployment: iOS 17.0
entry_va: 0xfffffff0073ed488
initial_tcr: 0x22a51a251a
TG0: 4096 bytes
TG1: 4096 bytes
```

`check-xnu-granules.py` 同时验证 BCM2837 为 4 KiB；`check-native-4k-policy.py`
在 5 个 RAM 边界上验证 native-4k 始终使用 kernel/user32 shift 12。
`audit-xnu-objects.py` 检查 1,010 个目标文件，0 个失败。

最终预链接 Mach-O 含 `ArmDTPlatform` 与 `ArmCpu` 的类、metaclass、probe/start、
GIC distributor 和 timer 相关符号。主机符号存在性不证明对应 probe 或设备初始化
已在真机执行。

## 载荷尺寸

内核、ADT 和配置共 54,063,968 字节。使用 mtools 创建 56 MiB FAT16 测试卷后成功
容纳全部文件，剩余 3,734,016 字节；从卷中回读的 `kernel.macho` SHA-256 与输入
完全一致。因此阶段 2.3 的起点是 56 MiB，而不是继续沿用阶段 1 的 4 MiB 内嵌卷。
该卷只用于主机尺寸验证，尚未验证 ABL/initrd/FDT/HOB 大载荷通道。

## 产物位置

```text
.cache/phase2-plan/UniXNU/out/elden/ipados-17.7.11-21H461/elden/
  kernel/kernel.macho
  kernel/kernel.macho.adt
  kernel/kernel.json
  xnu-inputs.json
  logs/kernel.log
  logs/prelink.log
  tree/build/xnu/kernel-audit.json
  tree/build/xnu-granules/constants.json
  tree/build/xnu/native-4k-policy/report.json
```

未生成 `payload/payload.img` 或 `boot/boot.img`。`unixnu build payload` 在生成 ADT
后按 4 MiB 上限正确拒绝，证明当前板级 `[payload] size_mib = 4` 只属于阶段 1，
不能在阶段 2 启动候选中复用。

## 最终回归

- `defconfig`、`status --json`、`tree` 再次通过，选择 5 个 canonical component
  和 57 个有序补丁；
- `porting-record.py check` 通过，检查 13 个结构区域；
- 硬件 DTS 生成 1,557 字节 DTB，SHA-256 保持
  `805c7b06228aa9398d564a843bbe890c865d905d1d2b8b970c33659f8df72cd4`；
- Phase 2.1 脱敏资源审计通过，XNU 窗口仍为 `0xC2400000 + 0x10000000`；
- Phase 1 `make_payload.py --verify-only` 与 `verify_artifact.py` 均通过；
  2,686,976 字节镜像的 Android v3、112 字节 BootShim、4 MiB FD、所需模块和
  内嵌 FAT 保持有效，且没有重新引入 `UFSDxe`。

## 复现命令

完整命令和本机 Command Line Tools shim 的位置记录在构建日志与设备
`porting.toml`。标准环境应在安装完整 Xcode 后运行：

```sh
cd .cache/phase2-plan/UniXNU
./unixnu defconfig elden_defconfig -D ../../../..
./unixnu fetch -D ../../../..
./unixnu tree -D ../../../..
./unixnu build kernel -D ../../../..
python3 scripts/porting-record.py check --device ../../../..
```

## 边界与下一步

- 2.2 只证明主机能使用固定输入构建并预链接目标 4 KiB XNU，不证明内核入口执行。
- kernelcache、XNU、DriverKit 和 TrustCache 的来源已固定；最终发布工具链仍需
  完整 Xcode/iPhoneOS SDK 重建。
- 最终 ADT 需要一个本地唯一 chip ID；当前 ADT 只覆盖结构和 ABI sidecar 检查。
- 下一关为 2.3：按 56 MiB 实际尺寸验证 Android v3 ramdisk、FDT/initrd 和 HOB 到
  UniXNURamDiskDxe/FAT 的只读 RAM 通道，再由设备所有者执行两次 RAM 冷启动。
