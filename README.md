# UniXNU-elden

Lenovo Legion Y700 四代（TB322FC / `elden`，SM8750P）的设备仓。目录布局
已迁移到 UniXNU 设备格式 2：共享 ARM64 与 iPadOS profile、SM8750 SoC
描述、设备 DTS、组件选择、固定源码、载荷配置和构建脚本分别管理。

当前进度：**阶段 0 已完成；阶段 1 的 UniXNU 菜单、GOP 显示、音量键输入和
FAT 载荷已使用同一镜像完成两次实机 RAM 冷启动验收。阶段 2.0–2.2 的主机输入
（格式 2 配置、live FDT/ADT、57 项补丁的 4 KiB XNU 与预链接内核）已完成并
审计。阶段 2.3 的 56 MiB FAT16 embed-payload 通道与阶段 2.4 的 DarwinBoot
交接都已在设备上完成两次 RAM 冷启动：EL1、256 MiB 窗口、退出 boot services
和绿色面包屑已确认。阶段 2.5 用入口蓝带和 PSCI 复位探针把内核推进到
`kernel_bootstrap_thread` 内部：XNU 入口执行已确认，并定位到两个平台依赖
——`PE_create_console` 读取 iBoot video console 交接区 `0x3C0F0000` 触发外部
异常，以及第 16 号 `kernel_startup_initialize_upto` 里程碑没有返回。下一步是
把 console 接到 `boot_args` 的 GOP 描述上，让内核日志能上屏。**

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| [`board.toml`](board.toml) | 格式 2 的四层配置选择、`elden` 板级、固件和载荷参数 |
| [`feeds.toml`](feeds.toml) | SM8750 SoC 来源；当前为可审计的本地过渡 profile |
| [`dts/elden.dts`](dts/elden.dts) | 板级内存和 SoC DTSI 引用 |
| [`soc/sm8750/`](soc/sm8750/) | 正式共享 SoC 仓发布前的过渡 profile |
| [`configs/`](configs/) | XNU defconfig 与阶段 0 恢复资产清单 |
| [`drivers/`](drivers/) | 仅存放设备专属驱动，目前为 `EldenRamDiskDxe` |
| [`package/`](package/) | UniXNU 菜单和载荷配置 |
| [`patches/`](patches/) | 设备 XNU 补丁序列和固定版本第三方源码覆盖 |
| [`scripts/`](scripts/) | 依赖准备、固件构建、载荷生成和产物检查 |
| [`kits/`](kits/) | 后续设备 kit 的预留目录 |
| [`docs/`](docs/) | 移植分析、阶段状态和交接文档 |
| [`assets/`](assets/) | 实机验收截图等仓库资源 |
| [`porting.toml`](porting.toml) | 统一维护者与 agent 适配记录 |

完整的 `third_party/` 源码、`.venv/`、`.cache/` 和 `out/` 构建产物均为
本地文件且不会提交到 GitHub。

## 文档

- [阶段 0：恢复路径](docs/PHASE0.md)
- [阶段 1：构建与测试](docs/PHASE1.md)
- [阶段 1：实机验收状态](docs/PHASE1-STATUS.md)
- [阶段 2：实施计划与验收关卡](docs/PHASE2-HANDOFF.md)
- [阶段 2：主机状态与基线](docs/PHASE2-STATUS.md)
- [阶段 2.1：FDT、ADT 与内存审计](docs/PHASE2.1-STATUS.md)
- [阶段 2.2：可追溯的最小 XNU](docs/PHASE2.2-STATUS.md)
- [阶段 2.3：大载荷 RAM 通道（主机侧）](docs/PHASE2.3-STATUS.md)
- [阶段 2.4：DarwinBoot 交接与内核入口探针](docs/PHASE2.4-STATUS.md)
- [阶段 2.5：XNU 入口检查点与平台依赖](docs/PHASE2.5-STATUS.md)
- [完整移植分析](docs/porting-analysis.md)
- [格式 2 迁移记录](docs/FORMAT2-MIGRATION.md)
- [第三方源码版本](docs/third-party.md)
- [第三方版本锁](unixnu.lock)

## 准备

从 GitHub 克隆后，在仓库根目录执行：

```sh
python3 scripts/bootstrap_third_party.py --clean-build-deps
```

该脚本克隆固定版本的 UniXNU 和 `mu_wide_platforms`，并应用
`patches/overlays/` 与 `drivers/` 中的项目修改。完整 EDK II 构建还需要
初始化上游子模块：

```sh
python3 scripts/bootstrap_third_party.py --init-submodules
```

参考资料仓可通过 `--all-references` 一并获取。当前验证环境是 Intel macOS
、MacPorts LLVM/LLD 20、Python 3.12 和 mtools。

## 格式 2 配置验证

格式 2 解析器位于当前 UniXNU 主仓。首次解析会复用仓库内的
`soc/sm8750` 过渡 profile：

```sh
PYTHON=.venv/bin/python
UNIXNU_DIR=../UniXNU

"$PYTHON" "$UNIXNU_DIR/unixnu" defconfig elden_defconfig -D "$PWD"
"$PYTHON" "$UNIXNU_DIR/unixnu" status --json -D "$PWD"
"$PYTHON" "$UNIXNU_DIR/unixnu" tree -D "$PWD"

"$PYTHON" "$UNIXNU_DIR/scripts/porting-record.py" check --device "$PWD"
```

硬件 DTS 可独立编译：

```sh
dtc -I dts -O dtb -i soc/sm8750/dts -o /tmp/elden.dtb dts/elden.dts
```

首次 `tree` 会初始化共享组件子模块；若 `status` 提示组件补丁缺失，先运行 `tree`
再重试。源码树可组装不代表 XNU reference、SDK、kernelcache 和 ABI 输入已齐备，
内核构建前仍需完成对应准备。当前 `third_party/UniXNU` 仍固定为阶段 1 已验证的提交，因此阶段 1 构建继续使用
`scripts/build_phase1.py`，不会因迁移改变已验收镜像的构建路径。

## 阶段 1 构建

```sh
cd UNIXNU_elden
source .venv/bin/activate
export PATH="/opt/local/libexec/llvm-20/bin:/opt/local/bin:/opt/local/sbin:$PATH"
python scripts/build_phase1.py --prepare-only --skip-submodules
```

完整构建需要已验证的 Crypto 归档：

```sh
python scripts/build_phase1.py \
  --skip-submodules \
  --crypto-path "$PWD/.cache/phase1/basecrypto"
```

产物写入 `out/`。现行阶段 1 基线镜像 SHA-256：

```text
94b6a6315b04fc9d276bc15e9519107be292244380fc3bf139f5af6c96a3bb0a
```

历史验收镜像 `b56ef4b7…` 的原始字节未保留。详细命令和排查步骤见
[阶段 1 构建与测试](docs/PHASE1.md)。

## 阶段 2.3 构建

阶段 2.3 使用独立的 `out/phase2.3/` 输出，不覆盖阶段 1 基线：

```sh
python scripts/build_phase2_firmware.py \
  --crypto-path "$PWD/.cache/phase1/basecrypto" --jobs 6
python scripts/make_phase2_probe.py
python scripts/build_phase2_image.py --kind probe
python scripts/build_phase2_image.py --kind boot
python scripts/verify_phase2_artifact.py --kind probe \
  --image out/phase2.3/elden-phase2-probe.img
python scripts/verify_phase2_artifact.py --kind boot \
  --image out/phase2.3/elden-phase2-boot.img
```

`payload.img` 由 UniXNU CLI 生成（需要 `dtc` 和 `--unique-chip-id`）。阶段 2.3
的设备步骤与哈希见 [阶段 2.3 状态](docs/PHASE2.3-STATUS.md)。

## 阶段 2.4 入口探针

阶段 2.4 复用阶段 2.3 的固件，只替换载荷里的内核：探针在入口画一条蓝色色带
再跳回内核，用来区分"XNU 入口执行"与"交接后挂住"。

```sh
python3 scripts/make_entry_probe_kernel.py
python3 scripts/make_phase2_payload.py   --output out/phase2.4/payload.img   --kernel out/phase2.4/probe/kernel.macho   --adt out/phase2.4/probe/kernel.macho.adt   --kernel-bytes 54050912   --kernel-sha256 a8f04b455996a4656a3055254c127e42f0676187c9550aa0b5fa57bbbe94e2d9
python3 scripts/build_phase2_image.py --kind boot   --fd out/phase2.3/SILICIUM_UEFI.fd   --payload out/phase2.4/payload.img   --output out/phase2.4/elden-phase2.4-probe-boot.img   --embed-payload --work out/phase2.4
python3 scripts/darwinboot_preflight.py   --kernel out/phase2.4/probe/kernel.macho   --adt out/phase2.4/probe/kernel.macho.adt
```

产物、判读表和设备步骤见[阶段 2.4 状态](docs/PHASE2.4-STATUS.md)。

## 阶段 2.5 检查点探针

MMU 打开后帧缓冲不再映射，屏幕不能继续当输出。阶段 2.5 改用"复位即检查点"：
`scripts/make_entry_probe_kernel.py` 把目标函数入口或任意指令地址原地替换成
`等 2 秒 → PSCI SYSTEM_RESET` 的 stub；设备在绿条后约 2 秒自行重启说明内核
到达该检查点，一直冻结说明没到。`--ret-at` 可把已知的 Apple 平台依赖（如
iBoot console）直接改成 `ret` 跳过。

```sh
# 示例：跳过 PE_create_console，复位放在 _machine_startup
.venv/bin/python scripts/make_entry_probe_kernel.py \
  --output-dir out/phase2.4/v31 \
  --reset-at _machine_startup \
  --ret-at 0xfffffff007941dec \
  --clang /opt/local/libexec/llvm-20/bin/clang
# 再用 make_phase2_payload.py / build_phase2_image.py / verify_phase2_artifact.py
# 生成镜像，参数与阶段 2.4 相同，只替换 --kernel 和额外字节数/SHA 断言。
```

检查点清单、每个镜像的 SHA-256 与反汇编依据见
[阶段 2.5 状态](docs/PHASE2.5-STATUS.md)。探针内核不是可启动系统，只用于
定位；跳过 Apple 平台初始化的镜像不能作为阶段 2 的交付产物。

## 设备支持

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| UEFI / BootShim | ✅ | 同一镜像两次 RAM 冷启动通过 |
| GOP 显示 | ✅ | 1904×3040，菜单可见 |
| 音量键输入 | ✅ | 可移动、确认菜单项 |
| UniXNU 菜单 | ✅ | 从内置只读 FAT 载荷读取配置 |
| 大载荷 RAM 通道 | ✅ | 56 MiB FAT16 嵌入载荷两次 RAM 冷启动通过 |
| DarwinBoot 交接 | ✅ | 2.4：两次冷启动到 EL1、256 MiB 窗口与退出 boot services |
| XNU 输入 | ✅ | 4 KiB 原生内核、预链接 kernelcache 与 ADT 主机审计通过 |
| DTB / ADT | ⚠️ | live FDT 与 ADT 主机审计通过；XNU 启动尚未验证 |
| XNU 入口 | ✅ | 入口蓝带（中线整宽）与 2 秒 PSCI 复位两次成立 |
| 平台专家 / boot CPU | ⏳ | 内核停在 `kernel_bootstrap_thread` 第 16 号启动里程碑 |
| UFS 根卷 / iPadOS 用户态 | ❌ | 后续阶段 |
| 触摸 | ❌ | 后续阶段 |

## 阶段 2 推进顺序

按[实施计划](docs/PHASE2-HANDOFF.md)依次通过：**2.0 基线与配置 →
2.1 硬件树/内存与 2.2 内核输入（并行）→ 2.3 大载荷 RAM 通道 →
2.4 DarwinBoot → 2.5 XNU 入口、平台专家和 boot CPU**。

2.0 的结果见[阶段 2 状态](docs/PHASE2-STATUS.md)，2.1 的结果见
[阶段 2.1 状态](docs/PHASE2.1-STATUS.md)，2.2 的结果见
[阶段 2.2 状态](docs/PHASE2.2-STATUS.md)。历史验收镜像的原始字节
未保留；当前 `out/elden-phase1.img` 已由设备所有者完成两次 RAM 冷启动复核，
成为现行阶段 1 基线。
阶段 2.3 的嵌入载荷通道、阶段 2.4 的 DarwinBoot 交接与阶段 2.5 的入口检查点
都已取得设备证据。当前结论：入口执行、`arm_init` 全程与线程启动都已确认；
内核死在 `kernel_bootstrap_thread` 第 16 号 `kernel_startup_initialize_upto`
里程碑内部。下一步先做 console 补丁（iBoot 交接区缺失时改用 `boot_args`
的 `Video[0..5]`），让内核日志能上屏，再继续二分该里程碑直到 `_bsd_init`。
DarwinBoot 的输入校验日志不计为 XNU 验收。

## 迁移边界

- `components.include` 只选择第一里程碑需要的平台、CPU、AES、预链接和
  DarwinBoot 组件；UFS、显示、触摸、GPU、网络和音频在实现与验证前不虚报。
- `dts/elden.dts` 使用 UEFI `DXE Heap` 中的 256 MiB 连续 XNU 窗口、
  8 核 MPIDR、GICv3 和 PSCI 输入。`dts/elden-firmware-memory.dts` 保存脱敏的
  固件 RAM／保留区描述；UFS、显示和触控节点仍待后续适配。
- `soc/sm8750` 是过渡目录，用来在没有公开
  `UniXNU-sm8750-common` 时保持格式 2 可解析。发布前必须迁入共享仓并在
  `feeds.toml` 固定 40 位提交，不能把本地目录当作发布来源。

## 安全边界

- 所有设备启动只由设备所有者本人执行；仓库不提供启动自动化。
- 阶段 1 只允许 `fastboot boot <image>` RAM 启动。
- 禁止刷写、擦除、格式化、槽位切换、分区或 GPT 修改。
- 每次测试记录镜像 SHA-256、构建来源和测试时间。
- 同一镜像至少两次 RAM 启动结果一致后，才继续后续调试。
- 不提交序列号、唯一芯片 ID、恢复备份、密钥或完整固件备份。

