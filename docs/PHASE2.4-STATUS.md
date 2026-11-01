# 阶段 2.4 状态：DarwinBoot 交接与内核入口探针

更新时间：2026-11-01

状态：**阶段 2.4 已在设备上通过两次 RAM 冷启动验证。DarwinBoot 接受阶段
2.3 的内核与 ADT，打印 ARM64/视频/退出 boot services 三行后交出控制权并
画出绿色面包屑；同一镜像第二次冷启动复现同一画面。阶段 2.5 的入口探针与
后续检查点见 [阶段 2.5 状态](PHASE2.5-STATUS.md)：XNU 入口执行已确认，
内核现停在 `kernel_bootstrap_thread` 内部。**

本阶段不改变 `board.stage = 1` 或 `kernel.status = "phase-2-pending"`：XNU
入口、平台专家和 boot CPU 仍未取得设备证据。阶段 1 基线与 `out/phase2.3/`
证据未被覆盖。

## 固定输入

| 输入 | 固定值 |
| --- | --- |
| kernel.macho | 54,050,816 字节 / `65a3e799e1eb7f631a3b146dfc890ef5a8147c8fc613ee383a1665b398fb1ef9` |
| kernel.macho.adt | 13,152 字节 / `b038ecd7c539ef6577a57153d581735948e6234f919cbfa6b2704c4f66a6b4ec` |
| 固件 FD | 4,194,304 字节 / `20b4b370d599aee9b081a283bd62faffe6ee66005d0de32967284d7d53adf245` |
| 阶段 2.3 终版镜像 | 12,738,560 字节 / `3dc8ae9611ec899ff14d50032ecd0ce2dd1035b3af9f9d3183bbab6cd41bcd93` |
| 阶段 2.3 探针镜像 | 2,695,168 字节 / `d40537f5a752d306e57d5d7672f1bd2ca3706b933b356f0e4d9b2c1af796ff7e` |

## 设备证据

2026-11-01，所有者手动 `fastboot boot` 阶段 2.3 终版嵌入载荷镜像
`3dc8ae96…`，在 UniXNU 菜单选择 `xnu` 条目。设备屏幕（照片）显示顶部 1/16
的绿色色带与以下三行：

```
DARWINBOOT: ARM64 va=0xFFFFFFF00427C000 pa=0xB927C000 args=0xBDB58000 entry=0xBC3ED488 owned=0x10000000
DARWINBOOT: video base=0xFC800000 display=1 row=7616 width=1904 height=3040 depth=32
DARWINBOOT: inputs validated; exiting boot services
```

同一镜像第二次冷启动复现同一画面（所有者确认）。这两条记录满足
`docs/PHASE2-HANDOFF.md` 对 2.4 的要求：

- `ARM64` 行只会在异常级别检查通过后打印（`DarwinBoot.c` 在
  `DarwinCurrentEl () != 4` 时改印 `unsupported inputs or exception level;
  firmware retained`），因此该次运行处于 EL1；
- 256 MiB 内存窗口在 `0xB927C000` 分配成功，`AllocateWindow` 的
  `NO WINDOW` 失败路径没有出现；
- `inputs validated` 之后调用 `ExitBootServices` 并进入 `DarwinEnter`；
- 绿色色带由 `Entry.S` 的 `DarwinEnter` 在跳转前绘制（`0xFF00FF00`），
  代码取消 MMU/cache 后 `br x1`。

**绿色色带只证明 `Entry.S` 执行，不证明 XNU 入口执行。** 交接后没有出现
任何内核输出；`panic_screen = false` 且内核串口未接线，因此当前无法区分
"内核在入口处挂住" 与 "入口立即异常"。这正是阶段 2.5 需要入口探针的原因。

## 入口探针设计

`scripts/make_entry_probe_kernel.py` 从阶段 2.3 载荷卷中抽出内核与 ADT，做三
处修改后生成新的 `kernel.macho`：

1. 在旧 `Kernel.End`（`0xFFFFFFF008586000`）之后按 0x4000 对齐追加一条
   `LC_SEGMENT_64`（`__ELDEN_PROBE`，r-x），文件偏移同样 0x4000 对齐；
2. 把入口（`0xFFFFFFF0073ED488`，`__TEXT_EXEC` 内）的首条 `b` 指令改为跳向
   新段（`0xFFFFFFF008588000`）；
3. 探针在末尾用一条 `b` 跳回原入口指令的目标（`0xFFFFFFF0073EF05C`）。

探针在 MMU/cache 关闭状态下运行：从 `x0` 指向的 `boot_args` 读取
`Video[6]`（`BootArgs.h` 偏移 0x28：帧缓冲基址、行字节、宽、高、位深），在
屏幕中线画四条整宽蓝色色带（BGRA `0xFF0000FF`），`dsb sy` 后跳回内核。
只使用 x9-x17，x0-x7 保持内核入口时的值。

DarwinBoot 的段映射是 `pa = 窗口基址 + (段 VA - Kernel.Base)`，段内容按
`FileOffset` 复制，因此新段落在 `0xBD58C000`；`Kernel.End` 随之后移，boot
args/ADT 仍由 DarwinBoot 放在新 `Kernel.End` 之后，互不覆盖。探针本身不需要
内核页表：它在内核启用 MMU 之前执行完毕。

## 主机验证

`scripts/darwinboot_preflight.py` 逐条复刻 `DarwinBoot.c` 的
`ParseKernel`/`AdtNode`（含 `MAX_SEGMENTS 64`、256 MiB 窗口、2 MiB 对齐、
可选占位符与 `.trustcache`/`.gpuaddon` 匹配规则），对探针内核与 ADT：

```
kernel: OK segments=16 base=0xfffffff00427c000 end=0xfffffff00858c000 entry=0xfffffff0073ed488 span=0x4310000
adt: OK tree=13152 bytes window=0x10000000 ramdisk=absent trustcache=absent gpuaddon=absent
```

载荷卷内 `Payloads/kernel.macho` 与 `kernel.macho.adt` 与
`out/phase2.4/probe/` 的文件逐字节一致；`scripts/verify_phase2_artifact.py`
以 v4 头、FAT12/16、`shim 128 + FD 4 MiB + payload 56 MiB` 通过，必需 FV
模块齐全、禁用模块缺席。

| 产物 | 字节 | SHA-256 |
| --- | ---: | --- |
| `out/phase2.4/probe/kernel.macho` | 54,050,912 | `a8f04b455996a4656a3055254c127e42f0676187c9550aa0b5fa57bbbe94e2d9` |
| `out/phase2.4/probe/kernel.macho.adt` | 13,152 | `b038ecd7c539ef6577a57153d581735948e6234f919cbfa6b2704c4f66a6b4ec` |
| `out/phase2.4/payload.img` | 58,720,256 | `065282a20ab92c60196916ddc2d61cffb3d7b23d4e93e387893e9fbdf7a4c26a` |
| `out/phase2.4/shim-boot-embed.bin` | 128 | — |
| `out/phase2.4/kernel-boot-embed.gzip` | 12,733,746 | — |
| `out/phase2.4/elden-phase2.4-probe-boot.img` | 12,738,560 | `a4ad1fc74abef35da9f947c350ff5763f2b8dea61da5adeee72aefcd0a67abf7` |

## 复现命令

```sh
python3 scripts/make_entry_probe_kernel.py
python3 scripts/make_phase2_payload.py \
  --output out/phase2.4/payload.img \
  --kernel out/phase2.4/probe/kernel.macho \
  --adt out/phase2.4/probe/kernel.macho.adt \
  --kernel-bytes 54050912 \
  --kernel-sha256 a8f04b455996a4656a3055254c127e42f0676187c9550aa0b5fa57bbbe94e2d9
python3 scripts/build_phase2_image.py --kind boot \
  --fd out/phase2.3/SILICIUM_UEFI.fd \
  --payload out/phase2.4/payload.img \
  --output out/phase2.4/elden-phase2.4-probe-boot.img \
  --embed-payload --work out/phase2.4
python3 scripts/verify_phase2_artifact.py --kind boot \
  --image out/phase2.4/elden-phase2.4-probe-boot.img \
  --fd out/phase2.3/SILICIUM_UEFI.fd \
  --shim out/phase2.4/shim-boot-embed.bin \
  --report out/phase2.4/verify.json \
  --embed-payload --payload out/phase2.4/payload.img \
  --expect-kernel-bytes 54050912 \
  --expect-kernel-sha256 a8f04b455996a4656a3055254c127e42f0676187c9550aa0b5fa57bbbe94e2d9
```

## 设备步骤与判读

所有者手动 RAM 启动 `out/phase2.4/elden-phase2.4-probe-boot.img`
（`a4ad1fc7…`），在菜单中选择 `xnu`。判读规则：

| 画面 | 含义 | 下一步 |
| --- | --- | --- |
| 绿色色带 + 中线蓝色色带 + 内核文本（或内核崩溃画面） | `Entry.S` 与 XNU 入口都执行了 | 进入 2.5：按 `arm_init` → `ArmDTPlatform` → `cpu_init` 逐级加探针 |
| 绿色色带 + 中线蓝色色带，之后无输出 | 内核入口执行，随后挂住或异常 | 用第二、第三个探针定位到具体阶段 |
| 只有绿色色带（无蓝色） | 入口 `b` 未被取指/执行 | 检查入口字、缓存维护与窗口内存；必要时改为段内跳板 |
| DarwinBoot 拒绝信息或 `NO WINDOW` | 新段或窗口不合法 | 读屏幕文本并按 `darwinboot_preflight.py` 修正 |

同一探针镜像至少两次冷启动结果一致后，才把入口证据记入 `porting.toml`。

## 限制

- ADT 仍是主机候选：`unique-chip-id = 1`、64 字节随机 seed；它不是设备身份，
  阶段 2.5 之后的内核检查若依赖真实 chip ID，需要所有者本地重新生成。
- 菜单标题仍为 `ELDEN 2.3 INITRD 56M`，本次只改内核与载荷，未改配置文本。
- `scripts/make_phase2_payload.py`、`scripts/verify_phase2_artifact.py` 和
  `scripts/build_phase2_image.py` 新增了探针内核身份与 `--work` 参数；默认值
  仍是阶段 2.3 的固定内核，因此旧命令行为不变。
