# UniXNU-elden

Lenovo Legion Y700 四代（TB322FC / `elden`，SM8750P）的设备仓。目录布局
沿用 `UniXNU-sheng` 的约定：板级描述、defconfig、设备驱动、载荷配置、
上游覆盖补丁和构建脚本分别管理。

当前进度：**阶段 0 已完成；阶段 1 的 UniXNU 菜单、GOP 显示、音量键输入和
FAT 载荷已使用同一镜像完成两次实机 RAM 冷启动验收。阶段 2 尚未生成可启动
XNU 的镜像。**

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| [`board.toml`](board.toml) | `elden` 板级、IPSW、固件和载荷参数 |
| [`configs/`](configs/) | XNU defconfig 与阶段 0 恢复资产清单 |
| [`drivers/`](drivers/) | 仅存放设备专属驱动，目前为 `EldenRamDiskDxe` |
| [`package/`](package/) | UniXNU 菜单和载荷配置 |
| [`patches/`](patches/) | 固定版本第三方源码的可复现覆盖层 |
| [`scripts/`](scripts/) | 依赖准备、固件构建、载荷生成和产物检查 |
| [`kits/`](kits/) | 后续设备 kit 的预留目录 |
| [`docs/`](docs/) | 移植分析、阶段状态和交接文档 |
| [`assets/`](assets/) | 实机验收截图等仓库资源 |

完整的 `third_party/` 源码、`.venv/`、`.cache/` 和 `out/` 构建产物均为
本地文件且不会提交到 GitHub。

## 文档

- [阶段 0：恢复路径](docs/PHASE0.md)
- [阶段 1：构建与测试](docs/PHASE1.md)
- [阶段 1：实机验收状态](docs/PHASE1-STATUS.md)
- [阶段 2：交接文档](docs/PHASE2-HANDOFF.md)
- [完整移植分析](docs/porting-analysis.md)
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

## 安全边界

- 所有设备启动只由设备所有者本人执行；仓库不提供启动自动化。
- 阶段 1 只允许 `fastboot boot <image>` RAM 启动。
- 禁止刷写、擦除、格式化、槽位切换、分区或 GPT 修改。
- 每次测试记录镜像 SHA-256、构建来源和测试时间。
- 同一镜像至少两次 RAM 启动结果一致后，才继续后续调试。
- 不提交序列号、唯一芯片 ID、恢复备份、密钥或完整固件备份。

