# UniXNU-elden

Lenovo Legion Y700 四代（TB322FC / `elden`，SM8750P）的设备仓。目录布局
已迁移到 UniXNU 设备格式 2：共享 ARM64 与 iPadOS profile、SM8750 SoC
描述、设备 DTS、组件选择、固定源码、载荷配置和构建脚本分别管理。

当前进度：**阶段 0 已完成；阶段 1 的 UniXNU 菜单、GOP 显示、音量键输入和
FAT 载荷已使用同一镜像完成两次实机 RAM 冷启动验收。阶段 2.0 已完成：格式 2
配置与输出隔离通过，现行阶段 1 基线也完成两次 RAM 冷启动复核；阶段 2 尚未生成
可启动 XNU 的镜像。**

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

产物写入 `out/`。阶段 1 验收镜像 SHA-256：

```text
b56ef4b7e5a71382b8c279c4ee1560764fabd126ba37ac0fd6e495c80b9ec6e1
```

详细命令和排查步骤见 [阶段 1 构建与测试](docs/PHASE1.md)。

## 设备支持

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| UEFI / BootShim | ✅ | 同一镜像两次 RAM 冷启动通过 |
| GOP 显示 | ✅ | 1904×3040，菜单可见 |
| 音量键输入 | ✅ | 可移动、确认菜单项 |
| UniXNU 菜单 | ✅ | 从内置只读 FAT 载荷读取配置 |
| DTB | ⚠️ | 上游仍为 `dummy` 占位文件 |
| DarwinBoot / XNU | ❌ | 阶段 2 尚未开始实机验证 |
| UFS 根卷 / iPadOS 用户态 | ❌ | 后续阶段 |
| 触摸 | ❌ | 后续阶段 |

## 阶段 2 推进顺序

按[实施计划](docs/PHASE2-HANDOFF.md)依次通过：**2.0 基线与配置 →
2.1 硬件树/内存与 2.2 内核输入（并行）→ 2.3 大载荷 RAM 通道 →
2.4 DarwinBoot → 2.5 XNU 入口、平台专家和 boot CPU**。

2.0 的结果见[阶段 2 状态](docs/PHASE2-STATUS.md)。历史验收镜像的原始字节
未保留；当前 `out/elden-phase1.img` 已由设备所有者完成两次 RAM 冷启动复核，
成为现行阶段 1 基线。
下一步可补齐真实固件 FDT、内存保留区与 XNU 输入；4 MiB 内嵌 FAT 与仅剩
920 字节的内层 FV 不能直接容纳阶段 2。DarwinBoot 的输入校验日志不计为 XNU 验收。

## 迁移边界

- `components.include` 只选择第一里程碑需要的平台、CPU、AES、预链接和
  DarwinBoot 组件；UFS、显示、触摸、GPU、网络和音频在实现与验证前不虚报。
- `dts/elden.dts` 先发布 2 GiB 连续 DRAM 窗口、8 核 MPIDR、GICv3 和
  PSCI 输入。整机内存映射、UFS、显示和触控节点仍待板级适配。
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

