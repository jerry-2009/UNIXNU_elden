# 阶段 2.3 状态：大载荷 RAM 通道（主机侧）

更新时间：2026-10-31

状态：**阶段 2.3 的主机出口已完成。56 MiB FAT 载荷、8 MiB 探针卷、独立阶段 2
固件和两种 Android v3 启动镜像均已生成并通过静态校验；尚未执行实机 RAM
启动，initrd 落点、ABL 的 `/chosen/linux,initrd-start/end` 和传入 `x0` 仍需
设备所有者用探针镜像确认。**

本阶段不改变 `board.stage = 1` 或 `kernel.status = "phase-2-pending"`。阶段 1
的固件、启动镜像和 `out/` 基线没有被覆盖；阶段 2 候选全部位于 `out/phase2.3/`。

## 固定输入

| 输入 | 固定值 |
| --- | --- |
| kernel.macho | 54,050,816 字节 / `65a3e799e1eb7f631a3b146dfc890ef5a8147c8fc613ee383a1665b398fb1ef9` |
| kernel.macho.adt | 13,152 字节 / `b038ecd7c539ef6577a57153d581735948e6234f919cbfa6b2704c4f66a6b4ec` |
| UniXNU 共享驱动 | `16e592abee8a550dec8154ed1f38b5ebc4f16213` 的 `UniXNURamDiskDxe` |
| BootShim | 112 字节，FD 基址 `0xFF300000`，大小 `0x00400000` |
| 固件 DSC | `Platforms/PakalaPkg/PakalaNoSb.dsc`，CLANGPDB、DEBUG |

`kernel.macho.adt` 使用 `unique-chip-id=1` 的主机结构检查值，并含随机 64 字节
seed；它不是设备身份，最终 ADT 必须由所有者提供唯一 chip ID 后重新生成。

## 固件改动

阶段 2 候选通过两个编译期宏与阶段 1 路径隔离：

- `ELDEN_PHASE2`：由 `scripts/build_phase2_firmware.py` 传给 EDK II；
- `ELDEN_INITRD_HANDOFF`：由 DSC 的
  `*_*_AARCH64_CC_FLAGS = -DELDEN_INITRD_HANDOFF=1` 追加。

未定义宏时，DSC/FDF 不进入任何新分支，阶段 1 的模块集合与构建入口保持不变。

具体改动：

1. `patches/overlays/mu_wide_platforms/Platforms/AndromedaPkg/PrePi/` 新增
   `PrePi.c`、`PrePi.h`、`PeiUniCore.inf` 和 `AArch64/ModuleEntryPoint.S`。
   SEC 入口在第一条指令把 `x0`（BootShim 保留的 ABL FDT 指针）存入 `x19`，
   `_PrepareArguments` 把它作为 `CEntryPoint` 的第二个参数传入；`PrePiMain`
   在 `BuildCpuHob` 之后、`PlatformPeim` 之前，用 `BuildGuidDataHob` 写入
   HOB GUID `DAEE82E6-8090-4E72-BFB9-78C13CD4E359`（值为 `UINT64` FDT 地址）。
   首次进入的指针优先，避免调度器重入覆盖。
2. `patches/overlays/UniXNU/package/UniXNUPkg/Driver/UniXNURamDiskDxe/` 原样
   引入共享驱动，只做一处兼容：pinned `MU_BASECORE` 只有 `FdtGetProperty`
   而没有 `FdtGetProp`，因此增加 `EldenFdtGetProp` 包装并替换两处调用。
3. `DXE.dsc.inc` / `DXE.inc` / `APRIORI.inc` 在 `ELDEN_PHASE2` 下移除阶段 1 的
   `EldenRamDiskDxe` 和内嵌 `payload.img`（FILE GUID
   `6A6B6F43-2AE5-4A7E-9C4E-7C9A9136D2B0`），加入 `UniXNURamDiskDxe`；后者
   在模块级覆盖 `FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf`，因为
   `EmbeddedPkg` 的 FdtLib 不导出 `FdtCheckHeader` 等 API。
4. FD 仍为 4 MiB，BootShim 基址仍为 `0xFF300000`；FatPkg、DiskIoDxe、
   PartitionDxe 和 EnglishDxe 沿用阶段 1 已包含的实例。

阶段 2 固件刻意不包含内嵌 FAT 卷，因此 UniXNU 的配置发现只会命中 initrd 卷，
不会出现两个 `EFI/UniXNU/unixnu.toml` 来源竞争。

## 主机产物

| 产物 | 字节 | SHA-256 |
| --- | ---: | --- |
| `out/phase2.3/SILICIUM_UEFI.fd` | 4,194,304 | `dc8a97dcf1369066114f0d10e50f0b163876b78a37796c29d7d468a7f6d9d9bf` |
| `out/phase2.3/payload.img` | 58,720,256 | `b2c96e08f71bbd3f8a84018024b1dc048994b72c2a81b56789686e503da82f80` |
| `out/phase2.3/probe.img` | 8,388,608 | `3183ca2b5943ba08574afaac8386eb903cc12733ac2cc5d020cda8aaa49ba4c3` |
| `out/phase2.3/kernel-probe.gzip` | 2,680,700 | — |
| `out/phase2.3/kernel-boot.gzip` | 2,680,700 | — |
| `out/phase2.3/elden-phase2-probe.img` | 11,075,584 | `9ea0174c275e7ebb42d9727c770b7a06ae09a6d44df9e36657a667c8de7e051b` |
| `out/phase2.3/elden-phase2-boot.img` | 61,407,232 | `d52dd8e37fa0ef87c44b2b15207497e93ac6285ca874cf20e5a668c4226ecf99` |

`payload.img` 是 56 MiB FAT16（卷标 `ELDENRAM`，序列号 `53484e47`），含：

- `EFI/UniXNU/unixnu.toml`（`timeout = -1`、`default = "reset"`、条目
  `ELDEN 2.3 INITRD 56M`，XNU 参数沿用阶段 2.2）；
- `EFI/UniXNU/Payloads/kernel.macho`（54,050,816 字节）；
- `EFI/UniXNU/Payloads/kernel.macho.adt`（13,152 字节）。

载荷总占用 54,064,363 字节，剩余 3,734,016 字节。UniXNU CLI 生成后只把
`default = "xnu"` 改为 `default = "reset"`，保证无输入时不会自动进入尚未完成的
XNU 启动。

`probe.img` 是 8 MiB FAT16（卷标 `ELDENPROBE`），只含一个配置：菜单显示
`ELDEN 2.3 PROBE - initrd FAT`，动作为 `reset`，没有 XNU 条目。它用于先用小卷
确认 FDT/initrd/HOB/磁盘栈通道，再换 56 MiB 终版。

两种启动镜像都由 `scripts/build_phase2_image.py` 复用
`Platforms/PakalaPkg/PythonLibs/mkbootimg.py` 打包：v3 头、1580 字节头、
4 KiB 分页、`kernel = gzip(BootShim + FD)`、ramdisk 为上面的 FAT 卷。

## 主机校验

`scripts/verify_phase2_artifact.py` 对两种镜像分别执行：

- Android v3 头、`header_size = 1580`、`ramdisk_size > 0`；
- 从页偏移 4096 解压 kernel，必须逐字节等于 `BootShim + FD`；
- 从 `4096 + align(kernel_size, 4096)` 取出 ramdisk；
- 解压 FVMAIN 的 LZMA guided section，遍历 section stream 找到 FV image，
  校验 `_FVH` 与长度；
- FD 必须包含 `UniXNU`、`UniXNUDxe`、`DarwinBoot`、`UniXNURamDiskDxe`，
  且不包含 `EldenRamDiskDxe`、阶段 1 内嵌 payload 和 `UFSDxe`；
- 用 mtools 校验卷标，读回 `unixnu.toml` 确认 `timeout = -1`、
  `default = "reset"` 和标题；终版还比对 `kernel.macho` 的字节数与 SHA-256。

两个镜像均返回 `artifact: OK`，结果写入 `out/phase2.3/verify.json`。

阶段 2 FVMAIN 解压流的首个 section 是 4 字节空 RAW，FV image section 在其后；
校验器按 section 链遍历，不假设固定的 8 字节前缀。

## 阶段 1 回归

用同一套 overlay 重新执行阶段 1 构建：模块集合、必需 FV 文件和禁止项仍全部
通过，但重建 FD/镜像与已验收基线的哈希不同。差异来自构建时间戳与阶段 1
`make_payload.py` 用 `mcopy` 写入 FAT 时的时间字段，重建不可字节复现。因此：

- 重建产物保存在 `.cache/phase1-regression-rebuild/` 作为证据；
- `out/SILICIUM_UEFI.fd`、`out/elden-phase1.img`、`out/build.json` 和
  `third_party/.../Payload/payload.img` 已恢复为已验收基线
  （`e5420517…`、`94b6a631…`、`8ccacc18…`），`scripts/verify_artifact.py`
  再次通过。

## 设备验证步骤（所有者执行）

先探针、后终版，每次都用 RAM 启动，不写入任何分区：

```sh
fastboot boot out/phase2.3/elden-phase2-probe.img
```

期望：进入 UniXNU 菜单，看到 `ELDEN 2.3 PROBE - initrd FAT`。选择该条目后设备
重启回 Android。连续两次冷启动都成功，才继续终版：

```sh
fastboot boot out/phase2.3/elden-phase2-boot.img
```

期望：菜单显示 `ELDEN 2.3 INITRD 56M`。**不要选择该条目启动 XNU**：DarwinBoot
和 XNU 入口尚未验证，失败会停在黑屏/重启。确认菜单与卷可读后选择 `Restart`。

若探针镜像没有菜单或没有探针条目，说明 `x0` 不是 FDT、ABL 没写 initrd 字段、
或 initrd 落在不可用内存；此时停在 2.3，先修 SEC/FDT 桥接，不进入 2.4。

## 限制与后续

- initrd 是否仍落在 `Kernel` 保留区 `[0xA8000000, 0xB8000000)`、ABL 是否对
  v3 ramdisk 写 `/chosen/linux,initrd-start/end`、传入 `x0` 是否为 FDT，
  均未在设备上确认。
- 未集成 `AdvancedLogDxe`/二维码日志导出；本阶段取证依赖屏幕菜单与串口。
- 阶段 2 固件不包含内嵌阶段 1 卷，不能用于阶段 1 回归启动；阶段 1 继续使用
  `out/` 基线。
- 主机仍缺完整 Xcode/iPhoneOS SDK，ADT 仍是主机候选。

下一步：设备所有者完成探针与终版各两次 RAM 冷启动后，进入阶段 2.4
（DarwinBoot）。若探针失败，先修 FDT/initrd/HOB 桥接。
