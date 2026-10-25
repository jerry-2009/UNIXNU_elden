# 阶段 2 状态

更新时间：2026-10-25

状态：**阶段 2.0 已完成。阶段 2 的固件树、内存、XNU 输入、载荷通道和 XNU
实机检查点均尚未完成。**

本文记录主机结果和阶段 1 基线判断。它不表示已经生成可启动 XNU 的镜像，也不改变
`board.stage = 1` 或 `kernel.status = "phase-2-pending"`。

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

该目录包含解析后的 `.config` 和组装树，不包含 `kernel.macho`、`payload.img`
或 `boot.img`。阶段 1 的 `out/` 仍由 `scripts/build_phase1.py` 管理，本轮没有
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
| DTB SHA-256 | `60316b6d4e753610610126d691f6d39ba54edd21e9b02875ec034e81e27a4371` |
| `make_payload.py --verify-only` | 通过，阶段 1 内嵌 FAT 与配置一致 |
| 阶段 1 重建 | 通过，使用当前阶段 1 脚本生成 image、FD 和载荷报告 |
| `verify_artifact.py` | 通过，阶段 1 新候选的 Android v3、FD、模块和 FAT 结构有效 |
| 实机复核 | 通过；设备所有者报告同一 image 两次 RAM 冷启动进入可用菜单并正常返回 Android |

DTS 使用 `dtc 1.8.1-gf99e3af0` 编译。反编译检查确认
`lenovo,elden`/`qcom,sm8750`、19.2 MHz timebase、PSCI SMC、GICv3 和
8 个 CPU MPIDR 节点存在。该 DTB 是主机生成的候选硬件树，不等同于设备实际
固件 FDT，也不包含完整保留区。

## 尚未完成

- 从设备或可复现 Linux 构建取得真实固件 FDT、内存保留区和设备标识脱敏证据；
- 核对 FD、BootShim、解压区、initrd、GOP、XNU、ADT 和 boot args 的实际区间；
- 准备目标 kernelcache、ABI、SDK 和可追溯的 `kernel.macho`；
- 生成并检查 `kernel.macho.adt`；
- 验证大载荷 ramdisk/FDT/HOB 通道；
- 验证 DarwinBoot 输入和拒绝路径；
- 取得 XNU 入口、`ArmDTPlatform`、boot CPU `ArmCpu`、GIC 和 timer 的实机证据。

下一项工作从 [阶段 2.1 和 2.2](PHASE2-HANDOFF.md#21固件-fdtxnu-adt-与内存交接)
开始，可并行采集固件/内存输入与可追溯 XNU 输入。
