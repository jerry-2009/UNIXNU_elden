# 阶段 2 状态

更新时间：2026-10-25

状态：**阶段 2.0、2.1 和 2.2 的主机侧工作已完成。载荷通道、DarwinBoot 和
XNU 实机检查点尚未完成。**

本文记录主机结果和阶段 1 基线判断。它不表示已经生成可启动 XNU 的镜像，也不改变
`board.stage = 1` 或 `kernel.status = "phase-2-pending"`。阶段 2.1 和 2.2 的
完整结果分别见 [PHASE2.1-STATUS.md](PHASE2.1-STATUS.md) 和
[PHASE2.2-STATUS.md](PHASE2.2-STATUS.md)。

## 2.0 结论

阶段 2.0 按
[实施计划的 2.0 节](PHASE2-HANDOFF.md#20核对基线与格式-2-配置)核对：

- 阶段 1 的历史实机验收记录、源码提交和固定依赖明确保留；
- 历史验收镜像未能在当前工作区恢复，当前 `out/` 通过重新构建和设备复核建立基线；
- 格式 2 配置由独立当前 UniXNU 检出解析，未升级阶段 1 的固定依赖；
- 四层配置、配置片段、补丁顺序和 5 个 canonical component 已检查；
- 格式 2 输出与阶段 1 的 `out/` 分开；
- 未生成阶段 2 内核、payload 或启动镜像。

因此 2.0 的现行阶段 1 基线明确，且阶段 2 输出仍与它分离。

## 2.1 主机结论

- 从已连接设备采集 885,861 字节 live FDT，并从固定 Linux 提交保留完整候选树；
- 原低 2 GiB 候选与 44 个保留区冲突；UEFI `Kernel` carveout 候选又因 live
  initrd 冲突，最终迁至 `0xC2400000 + 0x10000000`；
- 共享 ADT 生成器和独立解码器均通过，CPU、GIC、timebase、NVRAM、产品身份和
  `sleep-disabled=1` 符合输入；
- 最低 boot CPU 阶段移除未经 elden 验证的 `armcpu-spi-ipi=1`；
- 全部产物写入 `.cache/phase2.1/`，阶段 1 `out/` 未改变。

完整区间和复现命令见 [PHASE2.1-STATUS.md](PHASE2.1-STATUS.md)。

## 2.2 主机结论

- 目标 iPadOS 17.7.11 kernelcache 固定为
  `f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7`；
- XNU `10063.141.1`、DriverKit `xnu-10063.121.3`、TrustCache
  `xnu-8796.101.5` 和 57 个有序补丁全部解析并应用；
- 原生 4 KiB 内核为 21,206,040 字节，预链接 `kernel.macho` 为 54,050,816 字节；
- 预链接选择 30 个可执行 Apple 组件、7 个内核接口、119 个段范围和 30 个模块入口；
- 原生内核部署目标为 iOS 17.0，TCR TG0/TG1 都是 4 KiB，1,010 个目标文件审计通过；
- 主机 ADT 为 13,152 字节；最终设备身份仍需所有者本地提供唯一 chip ID；
- 56 MiB FAT16 测试卷容纳 54,063,968 字节输入并回读一致，剩余 3,734,016 字节。

完整哈希、工具链条件和非验收边界见 [PHASE2.2-STATUS.md](PHASE2.2-STATUS.md)。
本机只有 Command Line Tools；虽然已生成并审计正确 iPhone 平台/4 KiB Mach-O，
正式发布前仍须在完整 Xcode/iPhoneOS SDK 上重建。

## 阶段 1 基线

历史实机验收由设备所有者在同一镜像上完成两次 RAM 冷启动。当前仓库只保留了
记录和实机照片，没有保留该镜像或 FD 的原始字节。

| 项目 | 已记录值 |
| --- | --- |
| 验收镜像 | `b56ef4b7e5a71382b8c279c4ee1560764fabd126ba37ac0fd6e495c80b9ec6e1` |
| 验收 FD | `021a2a65db9ea5d2254604a2f81cea15fa70436f61b3591f25c056f5bcb7e37e` |
| 设备仓记录提交 | `c591b1a0a471f24978aba25c56c8f6ec9bd06668` |
| UniXNU | `c62bf12595f9a86c1b7282cf12d5af40b441fdac` |
| Mu-Silicium | `3e1d052064beb6e59cda3cfba87d50e6cc088174` |

证据来源见 [PHASE1-STATUS.md](PHASE1-STATUS.md)、
[PHASE1-HANDOFF.md](PHASE1-HANDOFF.md) 和 `porting.toml` 的 `device` 证据。

当前 `out/` 是使用现行阶段 1 配方重新构建并完成两次 RAM 冷启动的文件：

| 产物 | 字节 | SHA-256 | 判定 |
| --- | ---: | --- | --- |
| `out/elden-phase1.img` | 2,686,976 | `94b6a6315b04fc9d276bc15e9519107be292244380fc3bf139f5af6c96a3bb0a` | 现行基线 |
| `out/SILICIUM_UEFI.fd` | 4,194,304 | `e5420517d55f4b638c07617a252d3a65c95cfb731584dcb10dd1d98bae412580` | 现行基线 |

它们通过静态结构检查，且 `out/build.json` 与当前字节一致，但哈希与历史验收值
不同。构建前已将旧候选只读保存在本机
`.cache/phase2.0/candidate-2d47da288c66/`；当前候选另有只读副本位于
`.cache/phase2.0/candidate-94b6a6315b04/`。两处缓存都是本地恢复点，不随
仓库分发。设备所有者已使用当前 image 完成两次 RAM 冷启动；两次均进入菜单，
按键可用，退出后原厂 Android 正常启动。

## 格式 2 配置

校验使用独立的 UniXNU `main` 检出
`16e592abee8a550dec8154ed1f38b5ebc4f16213`。没有使用或升级
`third_party/UniXNU` 的阶段 1 固定检出。

配置按以下顺序解析：

1. ARM64 profile；
2. `soc/sm8750/soc.toml` 过渡 profile；
3. `ipados-17.7.11-21H461` OS profile；
4. 设备 `board.toml`。

解析结果保持 4 KiB 页，并选择以下 canonical component：

| 组件 | 固定提交 | 阶段 |
| --- | --- | --- |
| `ArmDTPlatform` | `417ff95d6a6e8607ddea9309ec45c3bfd4a67c60` | kernel |
| `ArmCpu` | `9066b53bbc82e92a98ec44a11dd50fd13eaf1a1b` | kernel |
| `SoftwareAES` | `4a45326da5c2cd6fe6813d79ee43db20805628af` | kernel |
| `XnuPrelink` | `f876e3ee62e18fc06653dd75ed7dafcfb3950ac0` | prelink |
| `DarwinBoot` | `3325e352d7df68a9f9ad74832ed94a6acbbd7390` | firmware |

配置片段顺序为 ARM64 → SM8750 → iPadOS，所选 defconfig 最后应用。补丁序列
顺序为 ARM64 → SM8750 → iPadOS → device，当前共解析 56 个补丁。SM8750 和
设备 series 当前为空，未发现缺失的已声明补丁文件。

`soc/sm8750` 仍是 `feeds.toml` 中的本地开发来源，`unixnu.lock` 没有对应的共享
SoC 提交。它满足当前开发解析，但仍是发布前必须解决的不固定输入。

## 输出隔离

格式 2 的主机解析输出为：

```text
.cache/phase2-plan/UniXNU/out/elden/ipados-17.7.11-21H461/elden/
```

该目录现在包含解析后的 `.config`、组装树、原生内核、预链接
`kernel/kernel.macho`、对应 ADT 和审计报告，但不包含 `payload.img` 或
`boot.img`。阶段 1 的 `out/` 仍由 `scripts/build_phase1.py` 管理，本阶段没有
重建或覆盖其中文件。

后续阶段 2 构建必须继续使用单独的 `--out` 根目录或已解析的输出目录；不得把
阶段 2 产物写回 `out/elden-phase1.img` 或 `out/SILICIUM_UEFI.fd`。

## 主机检查

| 检查 | 结果 |
| --- | --- |
| `defconfig elden_defconfig` | 通过，写入独立输出目录下的 `.config` |
| `tree` | 通过，组装了 5 个组件、设备 kit 和共享构建树 |
| `status --json` | 通过，四层来源、5 个组件、56 个补丁和 4 KiB 页可解析 |
| `porting-record.py check` | 通过，检查 13 个结构化区域 |
| 硬件 DTS | 通过，生成 1,557 字节 DTB |
| DTB SHA-256 | `805c7b06228aa9398d564a843bbe890c865d905d1d2b8b970c33659f8df72cd4` |
| 完整 FDT | 通过，142,699 字节，SHA-256 `e74bd077cb90b8255de6133dc08322e935fb6157b4dc9ebbec341ac854a8c136` |
| live FDT | 通过，885,861 字节，SHA-256 `8a653a3e790f29bf2b0f3545135f06fe771360f31da3d37c04f648c26b95e26e` |
| 阶段 2.1 审计 | 通过，ADT、RAM／保留区、UEFI map、CPU、GIC 和参数检查通过 |
| 阶段 2.2 内核构建 | 通过，XNU、corecrypto、ArmDTPlatform、ArmCpu、SoftwareAES、pthread 和预链接完成 |
| kernelcache 固定 | 通过，46,415,872 字节，SHA-256 `f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7` |
| 4 KiB / Mach-O 审计 | 通过，iOS 17.0、arm64、TCR TG0/TG1 均为 4 KiB |
| 目标对象 / prelink XML | 通过，1,010 个对象 0 失败；7,730 个 XML 标签可解析 |
| 2.2 载荷尺寸 | 通过主机 FAT16 装入测试；56 MiB 卷剩余 3,734,016 字节 |
| `make_payload.py --verify-only` | 通过，阶段 1 内嵌 FAT 与配置一致 |
| 阶段 1 重建 | 通过，使用当前阶段 1 脚本生成 image、FD 和载荷报告 |
| `verify_artifact.py` | 通过，阶段 1 新候选的 Android v3、FD、模块和 FAT 结构有效 |
| 实机复核 | 通过；设备所有者报告同一 image 两次 RAM 冷启动进入可用菜单并正常返回 Android |

DTS 使用 `dtc 1.8.1-gf99e3af0` 编译。反编译检查确认
`lenovo,elden`/`qcom,sm8750`、19.2 MHz timebase、PSCI SMC、GICv3 和
8 个 CPU MPIDR 节点存在。live FDT 根兼容串被刷机后的 vendor boot 改成通用
`qcom,sun-qrd`，但仍包含 elden 面板标记，物理显示为 1904×3040；审计按设备标识
和硬件树交叉确认，不把通用兼容串误当成另一块板。

## 尚未完成

- 在 DarwinBoot 交接时记录实际 ADT、boot args 和已分配窗口地址；
- 验证大载荷 ramdisk/FDT/HOB 通道；
- 验证 DarwinBoot 输入和拒绝路径；
- 取得 XNU 入口、`ArmDTPlatform`、boot CPU `ArmCpu`、GIC 和 timer 的实机证据。

下一项工作从 [阶段 2.3](PHASE2-HANDOFF.md#23先证明大载荷-ram-通道)开始，
在独立候选上验证 Android v3 ramdisk、FDT/initrd、HOB 和 UniXNURamDiskDxe/FAT
通道。阶段 2.2 的内核和 ADT 不证明 XNU 已执行。
