# 阶段 2.5 状态：XNU 入口检查点与两个平台依赖

更新时间：2026-11-01

状态：**进行中。XNU 入口执行已由设备证据确认；内核在 `arm_init` 之后
停在 `kernel_bootstrap_thread` 的第 16 号启动里程碑内部。** 本阶段仍不改变
`board.stage = 1` 或 `kernel.status = "phase-2-pending"`：ArmDTPlatform、
boot CPU、显示与存储都还没有内核侧证据。

阶段 2.4 的交接镜像与 `out/phase2.3/` 证据未被覆盖；所有探针镜像都写在
`out/phase2.4/<版本>/`，每个目录带自己的 `verify.json`。

## 结论摘要

1. **XNU 入口真的执行了。** 入口首条 `b` 被改成跳向探针段，探针在
   `boot_args->Video[0..5]` 上画中线蓝带。设备出现了整宽蓝带（v3：中线
   64 行），并在约 2 秒后按 PSCI `SYSTEM_RESET` 自行重启——蓝带与重启
   同时证明入口指令与复位通道都成立。
2. **`arm_init` 的唯一拦路石是 Apple iBoot 的 video console 交接区。**
   `_PE_create_console` 在 `0xfffffff007941e34` 读取物理地址 `0x3C0F0000`
   的 magic；本设备没有 iBoot 写过的这块内存，该读取触发外部异常，内核在
   console 建立之前静默挂死。把它的首指令改成 `ret` 之后，`arm_init`
   一路走到 `_machine_startup`（v31 复位）。
3. **下一个卡点在 `kernel_bootstrap_thread` 内。**
   该线程依次调用 `idle_thread_create`、`sched_startup`、
   `thread_daemon_init`、`kernel_startup_initialize_upto(…)`、`thread_bind`、
   `mapping_adjust`、`clock_service_create`、`device_service_create`、
   `phys_carveout_init`、`kdp_init`、`alternate_debugger_init`、
   `bootprofile_init`、`early_random`、`PE_init_iokit`，最后在
   `0xfffffff007985f60` 调 `bsd_init`。复位点 `0x985d44`（`PE_init_iokit`
   之后）已到达，`0x985d54` 未到达：**死在第 16 号
   `kernel_startup_initialize_upto` 调用（`0x985d50`，参数 `w0 = 0x10`）
   内部，且该调用没有返回。**

## 探针机制

`scripts/make_entry_probe_kernel.py` 现在支持三种改动：

- **入口段**（v1–v3）：在旧 `Kernel.End` 之后追加一条 r-x
  `LC_SEGMENT_64`，入口首条 `b` 改指探针；探针画带后跳回原目标。
- **原地 reset**（v4 起）：把目标函数开头约 48 字节替换成
  `等 N 秒 → PSCI SYSTEM_RESET → b .`。原地补丁位于 `__TEXT_EXEC`，
  换页表后仍可执行；追加段的探针（v6/v9）在
  `arm_vm_prot_init` 之后不可执行，会给出"没到"的假象，因此后续全部
  改用原地补丁。
- **跳过函数**（v31 起）：`--ret-at ADDRESS` 把目标首指令写成 `ret`
  （`0xD65F03C0`），用来排除已知的 Apple 平台依赖。

reset stub 先读 `CNTFRQ_EL0` 算出 2 秒的 tick 数，再在 `CNTPCT_EL0` 上
忙等；随后 `mov x0,#0x84000009; movk x0,#0x8400,lsl#16; smc #0`。
ADT 的 `psci` 节点声明 `arm,psci-1.0` 且 conduit 为 `smc`，与调用一致。
复位失败时 `b .`，不会掉回内核。

判读规则：出现绿条（DarwinBoot 面包屑）后约 2 秒自行重启 = 到达检查点；
一直冻结 = 没到。

## 设备证据

所有镜像 12,738,560 字节、v4 头，`scripts/verify_phase2_artifact.py` 全部
`artifact: OK`。除 v3 外都带 `ret@_PE_create_console`（跳过 iBoot console）；
v45/v46 另外跳过 `initialize_screen`。

| 版本 | 检查点 | 结果 | 镜像 SHA-256 |
| --- | --- | --- | --- |
| v3 | 入口蓝带 + 2 秒复位 | 蓝带（中线 64 行，整宽）+ 约 2 秒重启 | `4388868c1e2a187e810eb890061b103fe07d7aeaa780e5a0d5f4664e0b3a5d41` |
| v4 | `_arm_vm_init` 入口 | 重启 | `1a38262a2fd67c0b6152ba12b2213a81fa8a6433e683d12c2fa2e7374d4900f8` |
| v12 | `_pmap_bootstrap` 入口 | 重启 | `df71f70478528ac8fa00c640b4ddd1afc811265e2ad038fc9da5aac9ecd8bc0c` |
| v14 | `_patch_low_glo_static_region` 入口 | 重启 | `0ffafceed52fad4e9ad2a700989bf0acdd32b1d1c762719b5a6e1789fd3a32c3` |
| v10 | `_serial_init` 入口 | 重启 | `6a9bb44e191517c7ef87e2405cb45121b14543b4d0c14f06dcacc2979576d3c0` |
| v11 | `_PE_create_console` 入口 | 重启（只证明被调用） | `d8105aabbf0155021157c9706aaf8de411f5c1232900ab8f5dbe0067b1afe3dd` |
| v22 | `arm_init` 内 `0x9b6238` | 冻结 | `0fd998f62b4d4dd0cf10bf7f7e62c304eaaa4bc10b59b81e99932f1516f5ca31` |
| v27 | `arm_init` 内 `0x9b61fc` | 冻结 | `b515c64f…` |
| v28 | `_PE_create_console` 内 `0x941e10` | 重启 | `5ccb138c…` |
| v30 | `_PE_create_console` 内 `0x941e34`（magic 读取前） | 重启 | `1b73f57b…` |
| v29 | `_PE_create_console` 内 `0x941e80`（magic 判断后） | 冻结 | `8765e3e5…` |
| v31 | 跳过 console + 复位在 `_machine_startup` | 重启 | `eee4efb7dec42056626c873dc78885a16897a75764784ba8bb63f103f0e34cfe` |
| v33 | `_kernel_bootstrap` 入口 | 重启 | `b21fffdbd896178e808bb3982790ac648789d780f311b8c97638252c723e1011` |
| v34 | `_kernel_bootstrap_thread` 入口 | 重启 | `392dea18d46dc51cb6e56c0a12237ba965dcfd4f31930bc5b9541180beb40e2a` |
| v35 | `0x985f64`（`bsd_init` 调用返回后） | 冻结 | `a8904bc99c60be66a54c6b6d18ee6f318637716eba2a6a2c7c43729eba5fe5fd` |
| v32 | `_bsd_init` 入口 | 冻结 | `72309703633975c74fad2637f6846038032701f2df947fd6af8db01425dd5367` |
| v37 | `0x985c48`（`phys_carveout_init` 返回） | 重启 | `a19ab539721de2d20ee15d5418e46e4c66bc931b22ab5e45506a188baa095ff6` |
| v40 | `0x985c84`（`alternate_debugger_init` 返回） | 重启 | `ec5967a746b579231ce59cf8215990eacefab34024d8fafb088c8ed066f32e6e` |
| v39 | `0x985cc8`（`early_random` 之后） | 重启 | `eb3ceacc4cec01d778cbb05bd5208adf557a081ebcd67ae7ff98069578dcf526` |
| v41 | `0x985d44`（`PE_init_iokit` 返回） | 重启 | `d84712c575eadc2ff26c693679d8e8a448462fbd86a67c638470cbeca19368c2` |
| v45 | 跳过 console 与 screen，复位 `0x985d68` | 冻结 | `49049b816d71652a52611a729240f7eb793fcfe85033b37b8c067692f229534a` |
| v46 | 跳过 console 与 screen，复位 `0x985d54` | 冻结 | `47865160c2b8bce1ce937aa17763d534f901bdd6818c6b56114c679837516626` |

v45 冻结说明 `0x985d64` 的 `initialize_screen` 没有被执行到；v46 冻结说明
第 16 号 `kernel_startup_initialize_upto`（`0x985d50`）没有返回。二者把卡点
夹在这一次调用内部。

## 关键反汇编

`_PE_create_console`（`0xfffffff007941dec`）：

```
0x7941dec  ml_io_map_wcomb(0x3C0F0000, 0x4000)
0x7941e10  ldr w8, [x0]        ; 读 iBoot 交接区 magic
           CRBT / CSHM / KNUF 比较
0x7941e80  initialize_screen(0, 4)
```

`ml_io_map_wcomb` 本身只是 `b _io_map`（w2=6、w3=3、w4=0），映射是成功的
（v28 返回）。失败的只有读取 `0x3C0F0000` 那一条指令——这一页在 UEFI 侧
从未被映射成设备内存。

`kernel_bootstrap_thread`（`0xfffffff007985ab4`）到 `bsd_init` 的调用点：

```
0x985d40  PE_init_iokit
0x985d48  cbnz w0, 0x985f94     ; 中断已开则走另一分支
0x985d4c  mov  w0, #0x10
0x985d50  kernel_startup_initialize_upto(16)
0x985d58  ml_set_interrupts_enabled(1)
0x985d64  initialize_screen(0, 4)
0x985d68  vm_commpage_init
0x985d6c  vm_commpage_text_init
...
0x985f60  bl _bsd_init
```

`kernel_startup_initialize_upto` 遍历一张 `{stage, function, name}` 表，
按顺序调用 `stage <= 里程碑` 的条目，条目之间用 `kprintf` 打印
"Kernel startup, stage N: name"。因为 console 被跳过，这些打印在设备上
不可见——这也是下一个对话要先做 console 补丁的原因。

## 下一步

1. **把 console 接到 boot_args 的 GOP 描述上。** 在 `PE_create_console`
   里，iBoot 交接区读取失败时改用 `boot_args->Video[0..5]`
   （base/row/width/height/depth，阶段 2.4 已由 DarwinBoot 打印并验证），
   让 `kprintf` 能上屏。这一步之后所有后续检查点都能直接读屏幕，不必
   每个都做一次复位探针。
2. **解析 `kernel_startup_initialize_upto` 的 stage 表**，找出第 16 号
   里程碑里第一个没有返回的条目，用 `--reset-va` 在条目调用点二分。
3. 继续推进到 `_bsd_init`，再观察根文件系统挂载；本设备没有 UFS/APFS
   驱动，预期在那里出现 "no root device" 一类的 panic —— 那是阶段 2.5
   的终点与阶段 3 的起点。

## 复现

```sh
# 生成一个检查点内核（示例：跳过 console，复位在 _machine_startup）
.venv/bin/python scripts/make_entry_probe_kernel.py \
  --output-dir out/phase2.4/v31 \
  --reset-at _machine_startup \
  --ret-at 0xfffffff007941dec \
  --clang /opt/local/libexec/llvm-20/bin/clang

.venv/bin/python scripts/make_phase2_payload.py \
  --output out/phase2.4/v31/payload.img \
  --kernel out/phase2.4/v31/probe/kernel.macho \
  --adt out/phase2.4/v31/probe/kernel.macho.adt \
  --kernel-bytes <字节数> --kernel-sha256 <SHA-256>

.venv/bin/python scripts/build_phase2_image.py --kind boot \
  --work out/phase2.4/v31 --embed-payload \
  --payload out/phase2.4/v31/payload.img \
  --output out/phase2.4/v31/elden-phase2.4-probe-boot.img \
  --header-version 4

.venv/bin/python scripts/verify_phase2_artifact.py --kind boot \
  --image out/phase2.4/v31/elden-phase2.4-probe-boot.img \
  --fd out/phase2.3/SILICIUM_UEFI.fd \
  --shim out/phase2.4/v31/shim-boot-embed.bin \
  --embed-payload --payload out/phase2.4/v31/payload.img \
  --expect-kernel-bytes <字节数> --expect-kernel-sha256 <SHA-256> \
  --report out/phase2.4/v31/verify.json
```

探针内核不是可启动系统：它跳过 Apple 平台初始化并主动复位，只用于
定位检查点，不能作为阶段 2 的交付镜像。

## 限制

- 蓝带只能画在 MMU 打开之前：内核线性映射是
  `VA = VirtualBase + (PA − PhysicalBase)`，窗口 256 MiB，帧缓冲
  `0xFC800000` 相对窗口基址偏移 `0x43584000`，打开 MMU 后不在映射内。
- 复位探针证明"到达"，不证明"该函数做了什么"；它会把设备从 RAM 引导
  中复位，必须由所有者手动执行 `fastboot boot`。
- `serial=3` 没有对应串口硬件；在 console 补丁完成之前，内核日志不可见。
