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
  `*_*_AARCH64_CC_FLAGS = -DELDEN_INITRD_HANDOFF=1` 和
  `*_*_AARCH64_PP_FLAGS = -DELDEN_INITRD_HANDOFF=1` 追加（CC 给 C，PP 给
  `.S` 的预处理；漏掉 PP 时 `mov x19,x0` 不会编译进 PrePi）。

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
| `out/phase2.3/SILICIUM_UEFI.fd` | 4,194,304 | `f8c35ca26d539c630191c169357c5029f19918e622a645397ef0756a4db6ac56` |
| `out/phase2.3/payload.img` | 58,720,256 | `b2c96e08f71bbd3f8a84018024b1dc048994b72c2a81b56789686e503da82f80` |
| `out/phase2.3/probe.img` | 8,388,608 | `3183ca2b5943ba08574afaac8386eb903cc12733ac2cc5d020cda8aaa49ba4c3` |
| `out/phase2.3/kernel-probe.gzip` | 2,680,729 | — |
| `out/phase2.3/kernel-probe-v4.gzip` | 2,680,729 | — |
| `out/phase2.3/kernel-boot.gzip` | 2,680,729 | — |
| `out/phase2.3/elden-phase2-probe.img` | 11,075,584 | `2284d1cc944eaa7fe671cc791cb78b6368b97c8b048b28f017e63f2d2ab3aa02` |
| `out/phase2.3/elden-phase2-probe-v4.img` | 11,075,584 | `2f9c9e3d7c72e10727d72f43837d9691df26d3db5a38861591b7ae5b2cc16ce0` |
| `out/phase2.3/elden-phase2-boot.img` | 61,407,232 | `d25c08d49e56f5de9b2613873b14883c49581c5269eb9f0b74904a509fa736f1` |

2026-10-31 深夜为 v4 判别重建了一次：撤销临时诊断后干净重建，所以 FD 与三个
镜像的哈希都变了。提交 `4d98c60` 记录的 `dc8a97dc…`、`9ea0174c…`、`d52dd8e3…`
是同一代码路径的首次构建，作为历史证据保留在提交说明中。

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

## 2026-10-31 复查与决策：initrd 通道判定

两次设备 `fastboot boot` 都只进入 built-in 菜单：`x19` 交接与
`BuildGuidDataHob` 已编译进 PrePi（HOB GUID 出现在 FD 0xb000），但
`UniXNURamDiskDxe` 连一条诊断行都没有输出，说明 UEFI 根本没有拿到可用的
initrd，而不是驱动读到了错误的 FDT。

对照 unixnu.com 上同 SoC 的三台设备，现象与它们记录的平台限制一致：

| 设备 | 通道 | 关键事实 |
| --- | --- | --- |
| OnePlus 13T（PKX110） | embedded payload + BootPayload HOB | ABL 在 `fastboot boot` 时用 `init_boot` 的通用 ramdisk；v4 头、空 ramdisk、约 160 MiB FAT |
| erhai（一加平板 2 Pro） | `[bootimg] embed_payload = true` | 一加 ABL 会**整体替换**传入 ramdisk；payload 追加在固件后一起 gzip 进 kernel 字段，BootShim→SEC→payload HOB→`BootPayloadDxe` 发布只读 Block I/O |
| hummer（一加 Ace 5 Pro） | embedded payload + native UFS 根卷 | v4 头、160 MiB FAT32、`build-native-ufs.py`、6 核、真根卷到 Hello；UFS 是后续阶段 |

结论：**elden 的 initrd 假设在本机 ABL 上大概率不成立**。继续修
`linux,initrd-start/end` 桥接的收益很低；先做一次 v4 判别，仍失败就转
embed_payload。UFS 路线暂缓：阶段 1 已因 vendor `UFSDxe` 崩溃而移除它，native
UFS 根卷的工程量远大于本阶段。

### 立即执行：Android v4 判别

已生成并校验：`out/phase2.3/elden-phase2-probe-v4.img`（11,075,584 字节，
`2f9c9e3d7c72e10727d72f43837d9691df26d3db5a38861591b7ae5b2cc16ce0`），基于
干净重建的固件（`f8c35ca2…`，已撤销临时诊断）。内容与 v3 探针镜像完全相同，
只把头部改成 Android v4（`header_size = 1584`、`header_version = 4`、空 boot
signature）。目的只有一个：区分“ABL 完全不看 ramdisk”与“ABL 只接受 v4 头”。

```sh
fastboot boot out/phase2.3/elden-phase2-probe-v4.img
```

- 菜单出现 `ELDEN 2.3 PROBE - initrd FAT`：ABL 接受 v4 ramdisk，问题只在头部
  版本，保留 initrd 路线并补 v4 打包；
- 仍是 built-in：确认 ABL 替换/忽略 ramdisk，按下节转 embed_payload。

### 若 v4 仍失败：embed_payload（下一实现）

1. `board.toml` 增加 `[bootimg] embed_payload = true`，ramdisk 留空；
   kernel 字段 = `gzip(BootShim + FD + payload.img)`，BootShim 的 ARM64 头
   `image_size` 改为 `FD_SIZE + payload` 字节，并新增
   `-DEMBEDDED_PAYLOAD_SIZE=<payload 字节数>`。
2. `BootShim.S` 在跳转前把 payload 地址（`_Payload + FD_SIZE`）与长度放进
   `x2`/`x3`；`PrePi` 在 `HobConstructor` 后把它们写成 payload HOB（与阶段 1
   的 `EldenRamDiskDxe` 解耦）。
3. 新增 `BootPayloadDxe`：读 payload HOB，按 512 字节块发布只读
   `BlockIo` + `DevicePath`（复用 `UniXNURamDiskDxe` 的发布代码，去掉 FDT
   依赖）；`UniXNU` 即可从该 FAT 卷读 `EFI/UniXNU/unixnu.toml`。
4. 复用现有 56 MiB FAT 载荷与校验脚本；`payload.img` 不再受 4 MiB 内嵌 FV
   限制，也不需要 `x0`/FDT 交接。
5. 设备验证仍先探针、后终版，各两次 RAM 冷启动。

在 v4 判别结果出来前，不修改已提交的 initrd 固件与镜像；判别镜像只存在于
`out/phase2.3/`。


## 2026-11-01 结果与实施：embed_payload

设备所有者启动 v4 判别镜像后仍是 built-in 配置（"还是不行"），initrd 通道正
式关闭。按上一节的兜底方案实现 embed_payload：

- `patches/overlays/mu_wide_platforms/BootShim/BootShim.S`：定义
  `EMBEDDED_PAYLOAD_SIZE` 时 ARM64 头的 `image_size` 为 `UEFI_SIZE + payload`
  （不再是 `UEFI_SIZE`），复制循环只搬运 FD，`_Entry` 把 payload 基址/长度放进
  `x2`/`x3` 后跳 `UEFI_BASE`。不定义该宏时输出与阶段 1 的 112 字节 shim 完全
  一致（已用 `verify_artifact.py` 复核阶段 1 镜像）。
- `Platforms/AndromedaPkg/PrePi`：入口第一条指令把 `x2`/`x3` 保存到 `x20`/`x21`
  （先于任何函数调用），`_PrepareArguments` 以 `x0=MpId, x1=payload base,
  x2=payload size` 调 `CEntryPoint`；`PrePiMain` 在 `BuildStackHob` 后写
  GUID `5E1D9C3A-7B24-4F0E-9A6D-2C8F1B4E7D10` 的 payload HOB。
- `drivers/EldenPayloadDxe`：读 HOB，校验 512 字节对齐与 FAT 引导扇区
  `55 AA`，发布只读 `BlockIo`（512 字节块）+ RAM-disk `DevicePath`。只在
  `ELDEN_PHASE2` 下进入 DSC/FDF/APRIORI；阶段 1 仍用 `EldenRamDiskDxe` 与内嵌
  payload。阶段 2 固件同时移除了 `UniXNURamDiskDxe`，避免两个 FAT 卷争抢配置
  发现。
- 打包：`--embed-payload` 时 `kernel = gzip(BootShim + FD + payload)`，ramdisk
  为空，头部按 Android v4 重新标记；`scripts/verify_phase2_artifact.py
  --embed-payload` 校验空 ramdisk、shim 头 `image_size`、`shim+FD+payload`
  逐字节一致、HOB 驱动存在与阶段 1 卷/`UFSDxe` 不存在，并用 mtools 读回 FAT
  配置与 kernel。

主机产物（`out/phase2.3/`）：

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `SILICIUM_UEFI.fd` | 4,194,304 | `97f4ef9e2c24c6cb51d57ef1a93370dc2e630db1e6b058e29277622e173ebf9a` |
| `elden-phase2-embed-probe.img` | 2,695,168 | `132a7e55a32fb0afdf085e4661f8a31e9444e531775573e7fcc1f52c99cfe007` |
| `elden-phase2-embed-boot.img` | 12,836,864 | `0bead57045cecc24173cd919e89b96ad8d493e0335bdad8f2996783985f9df93` |

探针镜像内嵌 8 MiB `ELDENPROBE` 卷，只含一个 `probe` 条目；终版镜像内嵌
56 MiB `ELDENRAM` 卷（kernel.macho 54,050,816 字节、ADT 13,152 字节）。两者
均通过 `scripts/verify_phase2_artifact.py --embed-payload`，FD 内
`EldenPayloadDxe` 存在、`UniXNURamDiskDxe`/`EldenRamDiskDxe`/阶段 1 payload 均
不存在。

设备验收仍是两步：先 `fastboot boot out/phase2.3/elden-phase2-embed-probe.img`
两次，菜单出现 `ELDEN 2.3 PROBE - initrd FAT` 即证明 payload HOB → BlockIo →
FAT 通道成立；再启动 56 MiB 终版镜像，确认标题为
`ELDEN 2.3 INITRD 56M`，不要选择 `xnu` 条目。

## 2026-11-01 四色检查点（诊断）

设备连续两次在 embed_payload 镜像上进入 built-in 菜单，且串口/二维码日志尚未接入。为在不拍照的前提下定位失败层，`EldenPayloadDxe` 启动时在屏幕底部绘制 160 px 色带（GOP Blt，每 200 ms 重绘一次，持续 30 s），颜色含义：

| 颜色 | 含义 |
| --- | --- |
| 无色带 | 驱动没有执行（DSC/APRIORI 集成问题） |
| 红 | 驱动已执行，但没有收到 payload HOB（BootShim → PrePi 交接失败） |
| 黄 | 收到 HOB，但 payload 地址/大小/`55 AA` 校验失败 |
| 绿 | payload 有效且只读 BlockIo 已发布（问题在 PartitionDxe/Fat/UniXNU 配置发现） |

该色带只用于诊断，不改变启动流程；去掉 `EldenDrawIndicator`/`EldenStartIndicator` 调用即可移除。

产物（2026-11-01）：

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| `out/phase2.3/SILICIUM_UEFI.fd` | 4,194,304 | `20b4b370d599aee9b081a283bd62faffe6ee66005d0de32967284d7d53adf245` |
| `out/phase2.3/elden-phase2-embed-probe.img` | 2,695,168 | `574be59c2165fef3e4cbccbe9dd50d657e44446d66a6c818b18361587c6ca828` |

镜像为 Android v4、ramdisk 0，解压后为 128 字节 shim + 4 MiB 固件 + 8 MiB 探针 FAT 卷。
