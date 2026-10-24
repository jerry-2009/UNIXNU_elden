# 阶段 1：UEFI 正常启动（已通过）

目标是用同一张 `fastboot boot` 镜像连续两次冷启动，进入可见、可用音量键
操作的 UniXNU 菜单，并满足：

```text
DISPLAY OK
INPUT OK
UNIXNU: config: loaded
UNIXNU: menu: shown
```

本实现不依赖 UFS。`EldenRamDiskDxe` 从固件卷取出一张 4 MiB、只读 FAT16
镜像并通过 `EFI_BLOCK_IO_PROTOCOL` 发布；现有 `DiskIoDxe`、`PartitionDxe` 和
`FatDxe` 随后提供 `EFI_SIMPLE_FILE_SYSTEM_PROTOCOL`。UniXNU 从其中读取
`\EFI\UniXNU\unixnu.toml`。

## 已集成

- `lenovo-y700g4` 的 1904×3040 GOP/显示与按键路径；
- `UniXNU.efi`；
- `UniXNUDxe.efi`，负责把 UniXNU 注册为前置启动项；
- `DarwinBoot.efi`，阶段 1 只验证它能装入固件卷，不启动内核；
- `EldenRamDiskDxe.efi` 与内置 FAT payload；
- 无安全启动的 `PakalaNoSb.dsc` 和 4 MiB `SM8750_EFI.fd` 启动格式。

## 构建状态

2026-10-25 已完成 DEBUG/CLANGPDB 构建、自动二进制检查和两次实机 RAM
冷启动。当前产物：

- `out/SILICIUM_UEFI.fd`：4,194,304 字节；
- `out/elden-phase1.img`：2,686,976 字节；
- 镜像 SHA-256：
  `b56ef4b7e5a71382b8c279c4ee1560764fabd126ba37ac0fd6e495c80b9ec6e1`。

检查器会验证 Android v3 头、gzip 内容、BootShim/FD 一致性，并从最终 FD
解压 FVMAIN，确认 UniXNU、UniXNUDxe、DarwinBoot、EldenRamDiskDxe 和
4 MiB FAT payload 均已装入，并确认 `UFSDxe` GUID 不存在。

首次实机 RAM 启动在厂商 `UFSDxe` 内发生二级页表翻译异常，未到达 UniXNU
菜单。阶段 1 不需要 UFS，现已从 APRIORI、DSC 和 FDF 中移除 `UFSDxe`。
同一镜像已由设备所有者完成两次 RAM 冷启动，均进入 UniXNU 菜单；音量键
可移动选择，退出后原厂 Android 正常恢复。

注意：上游 `linux-y700g4.dtb` 仍是 `dummy` 占位文件。阶段 1 菜单不依赖该
DTB，但设备树功能和后续启动阶段不能据此视为已验证。

## 准备

**当前方法（2026-10-25）：Intel macOS + MacPorts LLVM/LLD 20 + 直接 EDK II
CLANGPDB 构建。** 当前阶段不要求完整 Xcode，不要求迁移 Linux。

主仓和以下参考仓位于 `third_party/`：

| 目录 | 用途 |
| --- | --- |
| `mu_wide_platforms` | UEFI 基线，含本机 `lenovo-y700g4` 包 |
| `UniXNU` | UniXNU、DarwinBoot 和通用驱动 |
| `UniXNU-piano` | 同 SoC 的菜单、载荷与实机记录 |
| `elden-linux` | 本机硬件常量与后续驱动资料 |
| `UniXNU-sheng` | 驱动接入参考 |
| `Project-SunUEFI` | SM8750 固件集成参考 |

首次从 GitHub 克隆后，先获取两个构建依赖并应用
[`patches/overlays/`](../patches/README.md)：

```sh
python3 scripts/bootstrap_third_party.py --clean-build-deps
```

完整编译前还需初始化 `mu_wide_platforms` 的子模块，可执行
`python3 scripts/bootstrap_third_party.py --init-submodules`。该方法会下载
数 GB 上游源码；已有准备完整的本地工作区可直接跳过。

本机已安装 `clang-20`、`llvm-20`、mtools。使用项目 Python 虚拟环境，
并启用 MacPorts 工具目录：

```sh
cd UNIXNU_elden
source .venv/bin/activate
export PATH="/opt/local/libexec/llvm-20/bin:/opt/local/bin:/opt/local/sbin:$PATH"
python --version
clang --version
lld-link --version
command -v llvm-lib llvm-rc mformat mcopy
```

先运行无设备写入的静态准备；这一步不编译完整固件：

```sh
python scripts/build_phase1.py --prepare-only --skip-submodules
```

FAT 载荷现在包含真实长文件名 `EFI/UniXNU/unixnu.toml`，并由 mtools 按该
路径读回校验。完整状态见
[`docs/PHASE1-STATUS.md`](PHASE1-STATUS.md)。

## 新构建流程

BaseTools C 工具已在本机生成；若以后重新准备源码，可从源码构建：

```sh
make -C third_party/mu_wide_platforms/MU_BASECORE/BaseTools/Source/C -j4
```

校验已有的 Crypto 归档，确认输出与下面的 SHA-256 完全一致后再解压：

```sh
shasum -a 256 .cache/phase1/basecrypto.zip
```

```text
2136c410dc44135830e2e33062243563d642e0be868d6affc2930c6b0854f5cf
```

```sh
mkdir -p .cache/phase1/basecrypto
unzip .cache/phase1/basecrypto.zip -d .cache/phase1/basecrypto
test -f .cache/phase1/basecrypto/Driver/Bin/CryptoDriver.inc.dsc
```

用统一入口执行完整构建：

```sh
python scripts/build_phase1.py \
  --skip-submodules \
  --crypto-path "$PWD/.cache/phase1/basecrypto"
```

入口使用 `/opt/local/libexec/llvm-20/bin`，需要时可以增加
`--toolchain DIR`；`--target RELEASE` 可切换构建目标。
该入口依次执行静态准备、直接 EDK II 编译、平台 Android v3 打包及产物检查。
它不会调用 stuart 的 setup/update，也不再使用 Zig 包装器。

仅调试固件编译、不生成 Android 启动镜像时可执行：

```sh
python scripts/build_direct_edk2.py \
  --crypto-path "$PWD/.cache/phase1/basecrypto"
```

完整构建成功后，产物为 `out/elden-phase1.img` 和
`out/SILICIUM_UEFI.fd`，同时更新 `out/build.json`。
可用下面的命令独立复核已有产物：

```sh
python scripts/verify_artifact.py \
  --fd out/SILICIUM_UEFI.fd \
  --image out/elden-phase1.img
```

## 设备所有者测试

1. 确认阶段 0 的 9008、恢复包和全量备份仍可访问。
2. 记录 `out/build.json` 中镜像的 SHA-256。
3. 由设备所有者本人执行唯一允许的启动命令：

   ```sh
   fastboot boot out/elden-phase1.img
   ```

4. 确认屏幕同时出现 UniXNU 菜单和配置摘要；用音量键移动、电源键选择。
5. 退出 RAM 启动，断电并确认原厂 Android 可正常启动。
6. 用同一 SHA-256 的镜像再冷启动一次，结果必须一致。

严禁把本流程替换为 `fastboot flash`、`set_active`、`erase`、`format`、
GPT 修改或槽位切换。

## 首次实机排查

| 现象 | 优先检查 |
| --- | --- |
| 停在 BDS | `UniXNUDxe` 是否出现在 FV、BootOrder 是否被改写 |
| 白屏或面板无画面 | `SimpleFbDxe`、panel XML、UEFI 冷启动显示竞态 |
| 菜单使用内置配置 | FAT 是否发布、`ELDEN-PAYLOAD: OK` 日志、配置路径 |
| 有菜单但无按键 | `ButtonsDxe` 与 `SimpleTextIn` 的映射 |
| 固化 `UFS WAIT` | 当前实现不应走 UFS 等待；检查是否用了旧镜像 |

