# 阶段 1 交接文档

更新时间：2026-10-25

状态：**阶段 1 已通过。同一镜像两次 RAM 冷启动均进入可见、可用音量键操作
的 UniXNU 菜单，退出后原厂 Android 正常启动。**

## 目标

用同一张 `fastboot boot` 镜像连续两次冷启动，在 Lenovo Legion Y700 四代
（TB322FC / `elden`）上进入可见、可用音量键操作的 UniXNU 菜单，并确认：

```text
DISPLAY OK
INPUT OK
UNIXNU: config: loaded
UNIXNU: menu: shown
```

阶段 1 不启动 XNU，不依赖 UFS，不执行刷写、擦除、格式化、槽位切换或 GPT
修改。所有设备启动只由设备所有者本人执行。

## 已完成

- 在 Intel macOS 上使用 MacPorts LLVM/LLD 20 和直接 EDK II CLANGPDB
  构建链路；
- 接入外部 Crypto 归档，并处理 EDK II 对工作区外绝对路径的限制；
- 接入 `EldenRamDiskDxe`、UniXNU、UniXNUDxe、DarwinBoot 和 4 MiB 内置
  FAT payload；
- FAT 载荷内部使用真实长文件名 `EFI/UniXNU/unixnu.toml`，并通过 mtools
  路径读回校验；
- 修正 RAMDisk 设备路径、Android v3 头大小和 UniXNULib/FDT 依赖；
- 移除 `UFSDxe` 后完成新的 DEBUG/CLANGPDB 固件和 Android v3 镜像构建；
- `verify_artifact.py` 可从最终 FD 解压 FVMAIN，并检查必要文件 GUID 和
  内嵌 FAT payload，同时拒绝包含 `UFSDxe` 的构建；
- 同一镜像完成两次实机 RAM 冷启动，均到达 UniXNU 菜单；
- 屏幕照片确认菜单和 `Return to firmware` 项可见，音量键可移动选择；
- 退出 RAM 启动后原厂 Android 正常恢复。

当前有效构建产物：

```text
out/SILICIUM_UEFI.fd
4,194,304 bytes
021a2a65db9ea5d2254604a2f81cea15fa70436f61b3591f25c056f5bcb7e37e

out/elden-phase1.img
2,686,976 bytes
b56ef4b7e5a71382b8c279c4ee1560764fabd126ba37ac0fd6e495c80b9ec6e1
```

首次实机测试使用的旧镜像已被否决，不得继续启动：

```text
SILICIUM_UEFI.fd
bde4355d21c20177b2478c957e0a8d409f54b450db8616fb5269010f44993c13

elden-phase1.img
91d86d6d68f6a7f54e202d2596a8a5e7ef4e1c26066b5492b2ef93db1c908d97
```

旧镜像已经被新构建覆盖；上表旧哈希只用于识别和避免误用。

## 首次实机结果

设备开始显示 UEFI 调试文本后没有进入 UniXNU 菜单，最终停在异常输出：

```text
Data abort: Translation fault, second level
ESR: EC 0x25  IL 0x1  ISS 0x00000005
Recursive exception occurred while dumping the CPU state
```

屏幕照片中的多层 `PC` 位于 `UFSDxe.efi`，之后才进入 `DxeCore.efi`。因此
系统在到达 `ELDEN-PAYLOAD: OK`、`UNIXNU: config: loaded` 和
`UNIXNU: menu: shown` 之前已经被厂商 UFS 驱动打死。

阶段 1 不需要 UFS。菜单所用的 FAT payload 由 `EldenRamDiskDxe` 发布，再由
`DiskIoDxe`、`PartitionDxe` 和 `FatDxe` 绑定。

## 本次交接前修改

已移除以下三处活动引用，并保留说明注释：

- `third_party/mu_wide_platforms/Platforms/PakalaPkg/Device/lenovo-y700g4/APRIORI.inc`
- `third_party/mu_wide_platforms/Platforms/PakalaPkg/Device/lenovo-y700g4/DXE.dsc.inc`
- `third_party/mu_wide_platforms/Platforms/PakalaPkg/Device/lenovo-y700g4/DXE.inc`

预编译的 `UFSDxe.efi` 文件仍保留在第三方目录中，但没有进入新构建的组件表、
FDF 或 APRIORI，因此不会被派发。

## 新会话构建

在项目根目录执行：

```sh
cd UNIXNU_elden
source .venv/bin/activate
export PATH="/opt/local/libexec/llvm-20/bin:/opt/local/bin:/opt/local/sbin:$PATH"

python scripts/build_phase1.py \
  --skip-submodules \
  --crypto-path "$PWD/.cache/phase1/basecrypto"
```

构建入口依次生成 FAT payload、BootShim、EDK II FD、Android v3 镜像并运行
产物检查。构建输出写入 `out/phase1-build.log`，哈希写入
`out/build.json`。

构建成功后独立复核：

```sh
python scripts/verify_artifact.py \
  --fd out/SILICIUM_UEFI.fd \
  --image out/elden-phase1.img
```

预期检查项：

- Android 头为 v3、大小 1580、无 ramdisk；
- gzip 内容等于 BootShim + 4 MiB FD；
- 最终 FD 可解压出 FVMAIN；
- `EldenRamDiskDxe`、`UniXNU`、`UniXNUDxe`、`DarwinBoot` 和 payload GUID
  全部存在；
- `UFSDxe` 的 GUID 不存在；
- 卷内 FAT payload 与生成的 `payload.img` 完全一致。

## 已完成的设备测试

1. 设备所有者两次执行 `fastboot boot out/elden-phase1.img`。
2. 两次均未出现 `UFSDxe.efi` 异常，并进入 UniXNU 菜单。
3. 屏幕照片确认菜单项和输入状态可见，音量键可移动选择。
4. 退出 RAM 启动后原厂 Android 正常启动。

阶段 1 验收镜像 SHA-256：

```text
b56ef4b7e5a71382b8c279c4ee1560764fabd126ba37ac0fd6e495c80b9ec6e1
```

## 已知风险

- `linux-y700g4.dtb` 仍是 6 字节 `dummy` 占位文件，不是有效设备树。阶段 1
  菜单设计上不依赖它，但 DT 功能不能视为已验证。
- 新内层 FVMAIN 只剩 920 字节，仍接近容量上限；后续增加模块前需要调整
  FV 布局。
- 大小写不敏感工作区仍不能同时保留 `PmicDxeLA.efi` 和 `PmicDxeLa.efi`。
- UFS 移除后若出现新的早期异常，仍需按相同方式读取最后一段屏幕调用栈，
  不要用刷写操作进行试探。

## 安全边界

- 只允许 `fastboot boot <image>` RAM 启动。
- 禁止 `fastboot flash`、`set_active`、`erase`、`format`、分区或 GPT 修改。
- 构建脚本不调用 `fastboot`。
- 卡死时由设备所有者长按电源键退出，然后确认原厂 Android 正常启动。

## 后续

阶段 2 从 [`PHASE2-HANDOFF.md`](PHASE2-HANDOFF.md) 继续：先准备真实的
`elden` DTB、iPadOS 17.7.11 内核输入和 Apple 设备树生成器，再验证
DarwinBoot 到 XNU 入口。阶段 1 的镜像只包含阶段 1 菜单项，不包含可启动
的 `xnu` 载荷。

