# 阶段 2.5 状态：XNU 入口检查点与两个平台依赖

更新时间：2026-11-01

状态：**内核侧目标达成（v51）。** 内核 console 在设备上打通，越过
`arm_init`、`kernel_bootstrap_thread` 与 `_bsd_init`，装载完 kext、跑到 BSD
阶段，最后进入根设备等待循环——屏幕上反复出现
`Waiting on <dict …>IOProviderClass…IOMedia…Apple_HFS…</dict>` 且**不再
panic**。这证明 XNU 已跑到用户态之前的最后一步，剩下的是缺 UFS/APFS 驱动
（阶段 3）。

沿途清掉的两个 AMFI 关卡（都是 Apple 的策略路径，不是硬件描述缺失）：
v49 卡在 `AMFI: not booted with security-mode-change-enabled`，v50 带上
`security-mode-change-enable=1` 后变成 `AMFI: No PMGR?`（developer-mode
latch 需要 `ApplePMGRNub`），v51 用一处 poke 让该 latch 直接返回。

本阶段仍不改变 `board.stage = 1` 或 `kernel.status = "phase-2-pending"`：
ArmCpu/GIC/timer 还没有各自命名的日志行，显示（`initialize_screen` 的
正式映射）与存储（UFS/APFS）仍无内核侧证据，而且 console 是镜像内
`--poke` 得到的，不是固件或驱动的正式修法。

之前"死在 stage 16"的结论已被 v49 推翻：那几次 `冻结` 是没有 console 的
panic，而不是 `kernel_startup_initialize_upto` 没返回。

阶段 2.4 的交接镜像与 `out/phase2.3/` 证据未被覆盖；所有探针镜像都写在
`out/phase2.4/<版本>/`，每个目录带自己的 `verify.json`。

## 结论摘要

1. **XNU 入口真的执行了。** 入口首条 `b` 被改成跳向探针段，探针在
   `boot_args->Video[0..5]` 上画中线蓝带。设备出现了整宽蓝带（v3：中线
   64 行），并在约 2 秒后按 PSCI `SYSTEM_RESET` 自行重启——蓝带与重启
   同时证明入口指令与复位通道都成立。
2. **`arm_init` 的唯一拦路石是 Apple iBoot 的 video console 交接区。**
   `_PE_create_console` 在 `0xfffffff007941e34` 读取物理地址 `0x3C0F0000`
   的 magic；本设备没有 iBoot 写过的这块内存，该读取触发外部异常并 panic
   （当时 console 还没建立，所以屏幕上看不到任何东西）。把它的首指令改成
   `ret` 之后，`arm_init` 一路走到 `_machine_startup`（v31 复位）。
3. **（已被 v49 推翻，保留作过程记录）曾以为卡点在 `kernel_bootstrap_thread` 内。**
   该线程依次调用 `idle_thread_create`、`sched_startup`、
   `thread_daemon_init`、`kernel_startup_initialize_upto(…)`、`thread_bind`、
   `mapping_adjust`、`clock_service_create`、`device_service_create`、
   `phys_carveout_init`、`kdp_init`、`alternate_debugger_init`、
   `bootprofile_init`、`early_random`、`PE_init_iokit`，最后在
   `0xfffffff007985f60` 调 `bsd_init`。复位点 `0x985d44`（`PE_init_iokit`
   之后）已到达，`0x985d54` 未到达：**死在第 16 号
   `kernel_startup_initialize_upto` 调用（`0x985d50`，参数 `w0 = 0x10`）
   内部，且该调用没有返回。** v49 打开 console 后证明这一次调用是正常返回的：
   内核一路跑到 `_bsd_init`、kext 装载与 BSD 初始化，说明 v45/v46 的"冻结"
   其实是 panic 之后无声停住（panic 文本因为 kprintf 被关掉而没上屏）。
4. **console 已经可用，而且不需要改内核源码。** `PE_init_iokit`
   （`0x985d40`）里的 `PE_init_printf(TRUE)` → `vcattach()` 会设置
   `vm_initialized` 并在 `gc_graphics_boot == FALSE` 时执行
   `initialize_screen(NULL, kPEAcquireScreen)` → `gc_enable(TRUE)`，把
   video console 真正打开。v49 只做了三件事：强制映射物理帧缓冲
   `0xFC800000`、跳过 iBoot 交接区读取、把 console 模式强制成
   `kPETextMode`；再加上打开 `kprintf` 闸门的两处数据补丁。设备屏幕上随后
   出现了完整的内核日志。
5. **当前真正的卡点是 AMFI 的 developer-mode 策略。** 设备屏幕最后一行是
   `panic(cpu 0 caller …): "AMFI: not booted with security-mode-change-enabled" @ConfigurationSettings.cpp`，
   前面还打印了 `Waiting on <dict …><key>IOProviderClass</key>…<string>IOMedia</string>…<string>Apple_HFS</string>`。
   也就是说：平台代码、`bsd_init`、IOKit、APFS、Skywalk、NVRAM、IOSurface
   都已经跑起来，挡住启动的是 Apple 的安全策略开关（boot-arg），而不是
   elden 的硬件描述。
6. **boot-arg 通道是通的。** payload 配置 `package/phase2.5-unixnu.toml` 的
   `args` 字段经 UniXNU → DarwinBoot `Request->BootArgs` 原样写入
   `boot_args->CommandLine`，所以 `security-mode-change-enable=1` 与
   `amfi_get_out_of_my_way=1` 直接可用；v50 就是带这两个参数的镜像。

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
- **任意 32 位写入**（v49 起）：`--poke ADDRESS=WORD` 或 `--poke SYMBOL=WORD`
  在指定虚地址写入一个 32 位字，代码段与数据段都可以；脚本会打印
  `旧值 -> 新值` 和所在段名，写进 `probe.json` 便于审计。console 试验
  只靠这种写入，不注入任何新代码。

reset stub 先读 `CNTFRQ_EL0` 算出 2 秒的 tick 数，再在 `CNTPCT_EL0` 上
忙等；随后 `mov x0,#0x84000009; movk x0,#0x8400,lsl#16; smc #0`。
ADT 的 `psci` 节点声明 `arm,psci-1.0` 且 conduit 为 `smc`，与调用一致。
复位失败时 `b .`，不会掉回内核。

判读规则：出现绿条（DarwinBoot 面包屑）后约 2 秒自行重启 = 到达检查点；
一直冻结 = 没到。

## 为什么屏幕上一直没有内核文字

探针镜像从来没有打出过一行内核文字，原因有两道互相独立的闸门，缺一不可：

1. **`kprintf` 本身被关掉。** `pexpert/arm/pe_kprintf.c:101` 的整个函数体
   包在 `if (!disable_serial_output && !disable_kprintf_output)` 里，两个
   `SECURITY_READ_ONLY_LATE(bool)` 初值都是 `true`；`PE_init_kprintf_config`
   只有在 boot-arg 里带 `debug=0x…`（`DB_KPRT`）时才清第一个，第二个只在
   `DEBUG` 构建或 DEVELOPMENT 的 `-enable_kprintf_spam` 下才清。所以即使
   console 完全就绪，`kprintf` 也一个字都不输出。
2. **video console 没有被启用。** `vcputc_options` 只在
   `gc_initialized && gc_enabled` 时画字，而 `gc_enabled` 只由
   `gc_enable(TRUE)` 置位；`gc_enable` 只由 `initialize_screen(…,
   kPEAcquireScreen)` 调用，而 `PE_create_console` 用的是
   `kPEGraphicsMode`，那条路径只把 `gc_graphics_boot` 置 `TRUE`、不做
   `gc_enable`。

好消息是第 2 道闸门有一条现成通路：`PE_init_iokit()`
（`pexpert/arm/pe_init.c:267`）第一句就是 `PE_init_printf(TRUE)` →
`vcattach()`，发生在 `0x985d40`，也就是第 16 号里程碑之前，并且 v41 已
证明它返回。`vcattach` 会置 `vm_initialized = TRUE`（否则
`vc_render_font` 直接返回）、并且在 `gc_graphics_boot == FALSE` 时执行
`initialize_screen(NULL, kPEAcquireScreen)` → `gc_enable(TRUE)`（分配行
缓冲、渲染字体、`gc_enabled = TRUE`、`disableConsoleOutput = FALSE`），
最后把 ring buffer 里积压的 kprintf 全部刷到屏幕上。

所以只要让 `PE_create_console` 走 **text** 模式（`gc_graphics_boot`
保持 `FALSE`）并把帧缓冲映射好，console 就会在 stage 16 之前自动亮起来，
不需要改 XNU 源码、不需要重编内核。v49 就是按这个思路做的纯 `--poke`
镜像（8 处 32 位写入，全部可逆）：

| 地址 | 原值 → 新值 | 作用 |
| --- | --- | --- |
| `0xfffffff0073bdf24` | `0x370000b5` → `0x14000005` | `initialize_screen` 强制走 `makeMapping`，把物理 `0xFC800000` 映射进内核 |
| `0xfffffff007941e0c` | `0x97eac134` → `0x1400001d` | 跳过 `ml_io_map_wcomb(0x3C0F0000)` 与 iBoot magic 读取，直接落到模式选择 |
| `0xfffffff007941e90` | `0x1a941681` → `0x52800041` | `cinc w1,w20,eq` → `mov w1,#2`，即 `kPETextMode`，保住 `gc_graphics_boot == FALSE` |
| `0xfffffff0071fd970` | `0x00000101` → `0x00000000` | 清掉 `disable_serial_output`/`disable_kprintf_output`，打开 kprintf |
| `0xfffffff0071fd978/7c` | `0` → `0xfffffff0073bb01c` | `PE_kputc` 预置成 `console_write_unbuffered`，避免 KPRINTF 阶段之前的 kprintf 空指针调用 |
| `0xfffffff0071652a4` | `0` → `1` | `startup_debug = STARTUP_DEBUG_VERBOSE`，逐条打印启动条目 |
| `0xfffffff007053aac` | `0x000a2970` → `0x000d2970` | 条目打印格式串结尾的 `\n` 改成 `\r`，只覆盖同一行、不滚动（行缓冲已分配，滚动一次要搬 16 MB） |

上表后两行只在"要读 stage-16 逐条轨迹"时才有意义。v49 的屏幕证明了真正
需要的是**普通内核日志**，所以 v50 只保留前六行 pokes（映射、跳过交接区、
`kPETextMode`、两个闸门标志、`PE_kputc`），去掉 `startup_debug` 与格式串
补丁，让日志自己换行滚动。

## 设备证据

所有镜像 12,738,560 字节、v4 头，`scripts/verify_phase2_artifact.py` 全部
`artifact: OK`。v3–v46 带 `ret@_PE_create_console`（跳过 iBoot console），
v45/v46 另外跳过 `initialize_screen`；v48–v50 改用 `--poke`，不再需要 `ret`。

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
| v46 | 跳过 console 与 screen，复位 `0x985d54` | 冻结（v49 判定：无 console 的 panic，不是没返回） | `47865160c2b8bce1ce937aa17763d534f901bdd6818c6b56114c679837516626` |
| v49 | console 试验：8 处 `--poke`，无复位 | **console 点亮**；内核打印到 kext 装载，最后 `AMFI: not booted with security-mode-change-enabled` @`ConfigurationSettings.cpp` panic | `0e3648192f2c2f3b1d6d01f75efa99b83b5f4d91fbcd06c07bd8790865fb41f9` |
| v50 | v49 的 6 处 `--poke`，payload 换成 `package/phase2.5-unixnu.toml`（`security-mode-change-enable=1 amfi_get_out_of_my_way=1`） | **console 与 boot-arg 双通**：AMFI 的 `security-mode-change` 通过，panic 变成 `AMFI: No PMGR?` @`ConfigurationSettings.cpp:235`（`ApplePMGRNub` 查不到）；根设备等待文本与 panic 同屏 | `d12b56ecd6e3e53fb23982ab09fbd0a26820501b8cb8d8edf1eacfa95e0cae70` |
| v51 | v50 的 6 处 console `--poke` + `0xfffffff004aaecfc: mov x0,x21 → b 0xfffffff004aaec4c`（AMFI 的 developer-mode latch 直接返回） | **不 panic 了**：反复打印 `Waiting on <dict ID="0"><key>IOProviderClass</key><string ID="1">IOMedia</string><key>Content</key><string ID="2">Apple_HFS</string></dict>`，停在根设备等待循环 | `cc739804217c3277bb07e4ce967381d5e1dd970eb46e9bb6637ebb83c5c668be` |


v45/v46 当时被读成"第 16 号 `kernel_startup_initialize_upto`（`0x985d50`）
没有返回"。v49 推翻了这个读法：同一条路径在 console 打开后完整跑过 stage 16
并进入 BSD。因此 v45/v46 的"冻结"是一次 panic 之后停住——panic 文本经过
`kprintf`，而当时 `disable_serial_output`/`disable_kprintf_output` 仍为 `1`，
所以屏幕上什么也没有。**复位探针只在"确实返回到该地址"时才重启，panic 会让
它永远等不到；这正是把 panic 误判成挂死的机制。**

已生成、但还没有设备结果的镜像（不计入证据）：

| 版本 | 内容 | 镜像 SHA-256 |
| --- | --- | --- |
| v48 | 跳过 console 与 `0x985d64`，复位在第 7 个 stage-16 条目 `_set_awl_scratch_exists_flag_and_subscribe_for_pm`（stage-16 假设已被 v49 推翻，留作对照） | `cab3f3f8e6e7840b7e4c70fcffcbe6b0132c262dda9d5a7429d3c9ddce3afbfc` |

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

`kernel_startup_initialize_upto` 遍历的表在
`__BOOTDATA,__init_entry_set`（本内核 VA `0xfffffff007b4c000`，96,144 字节，
4,006 条），元素是 24 字节的
`{u32 subsystem; u32 rank; void (*func)(const void *); const void *arg;}`。
`startup.c:281` 用 `qsort` + `startup_entry_cmp`（先比 `subsystem` 再比
`rank`，相等返回 0）排序，底层是 `bsd/kern/qsort.c` 的实现，**不稳定**，
所以运行时顺序不能按链接顺序猜。在主机的 `/tmp/qs_harness` 上用同一份
`qsort.c` 和同一个比较函数重放排序，得到的 stage 16（EARLY_BOOT）实际
执行顺序是：

```
_socd_client_set_primary_kernelcache_uuid      rank 0
_procinit                                       rank 0
_ulock_initialize                               rank 0
_source_pthread_bootstrap                       rank 1
_pgz_init                                       rank INT_MAX
_iotrace_init                                   rank INT_MAX
_set_awl_scratch_exists_flag_and_subscribe_for_pm  rank INT_MAX
_cs_text_fixup_init                             rank INT_MAX
_telemetry_init                                 rank INT_MAX
_vm_pageout_create_gc_thread                    rank INT_MAX
_kmem_crypto_init                               rank INT_MAX
_exe_boothash_salt_generate                     rank INT_MAX
_lockdown_mode_init                             rank UINT_MAX
```

逐条打印的格式是 `"%s[%d, rank %d]: %p(%p)\n"`，而且只在
`(startup_debug & STARTUP_DEBUG_VERBOSE) && startup_phase >= 4` 时才打；
`startup_debug` 默认 0，所以正常启动下这一行也不出现。v49 同时打开了
`startup_debug` 和 console，屏幕上就会依次显示这些行。

## 下一步

阶段 2.5 的内核侧到这里就结束了：v51 停在根设备等待，不再有 Apple 策略
panic。继续往前需要换筹码——补硬件驱动，而不是继续 poke。

1. **先做阶段 3 的存储入口：UFS。** 根设备等待的 `IOMedia/Apple_HFS` 匹配
   表说明内核在等一个块设备；elden 的 UFS 控制器（SM8750，`1d84000.ufshc`
   一类地址）还没有驱动，`IOMedia` 永远不会出现。要在 UniXNU 里选一个 UFS
   组件并按 SM8750 的寄存器/PHY 描述接上，这是让"等待根设备"变成"挂载根
   卷"的唯一路径。
2. **把 console 变成正式修法。** 现在的输出靠镜像内 `--poke`（强映射帧缓冲、
   跳过 iBoot 交接区、强制 `kPETextMode` 并打开 kprintf 两个闸门）。正解是
   DarwinBoot 在 `Video[0]` 上带 bit0 物理地址标记（或 port 侧写 `/chosen`
   的描述），让 `initialize_screen` 自己建映射；这需要重编固件，属于阶段 3
   的固件条目。
3. **补 ArmCpu/GIC/timer 的显式证据。** 内核能跑到 BSD 说明这些平台模块
   在起作用，但日志里没有各自命名的行；用 `armcpu-diagnostics=1` 或
   `debug=0x14e` 里对应的位把中断/定时器一次性打印出来，才能把 CPU 区域的
   `completion` 判据逐条勾掉。
4. **硬件描述缺口要单独立项。** `ApplePMGRNub`（电源管理）、`AppleSEPManager`
   （安全协处理器）这类"缺 Apple 硬件"的检查目前靠 poke 绕过；阶段 3 之后
   若要走真实设备，需要分别为它们提供驱动或明确的端口策略。
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

v49（console 试验，无复位，纯 `--poke`）只把第一步换成：

```sh
.venv/bin/python scripts/make_entry_probe_kernel.py \
  --output-dir out/phase2.4/v49 \
  --poke 0xfffffff0073bdf24=0x14000005 \
  --poke 0xfffffff007941e0c=0x1400001d \
  --poke 0xfffffff007941e90=0x52800041 \
  --poke 0xfffffff0071fd970=0x00000000 \
  --poke 0xfffffff0071fd978=0x073bb01c \
  --poke 0xfffffff0071fd97c=0xfffffff0 \
  --poke 0xfffffff0071652a4=0x00000001 \
  --poke 0xfffffff007053aac=0x000d2970 \
  --clang /opt/local/libexec/llvm-20/bin/clang
```

后面的 payload / 镜像 / 校验三步与上面完全相同，只是把 `v31` 换成 `v49`、
把内核字节数与 SHA-256 换成新内核的值（54,050,920 /
`8a57a771b987477135692dc6b7a0c25c2a94587b8e0200e3a5934f284483de08`）。

## 限制

- 蓝带只能画在 MMU 打开之前：内核线性映射是
  `VA = VirtualBase + (PA − PhysicalBase)`，窗口 256 MiB，帧缓冲
  `0xFC800000` 相对窗口基址偏移 `0x43584000`，打开 MMU 后不在映射内。
- 复位探针证明"到达"，不证明"该函数做了什么"；它会把设备从 RAM 引导
  中复位，必须由所有者手动执行 `fastboot boot`。
- `serial=3` 没有对应串口硬件；内核日志只走 video console，靠的是
  DarwinBoot 已经交给内核的 GOP 帧缓冲描述，不依赖任何串口。
- v49–v51 的 console 与 AMFI 绕过都是**靠 `--poke` 在镜像里打补丁**得到的：强制映射帧
  缓冲、跳过 iBoot 交接区、把 console 模式改成 `kPETextMode`、并打开
  `kprintf` 的两个闸门标志。这不是最终形态——正式修法应当是 DarwinBoot 在
  `Video[0]` 里带上"这是物理地址"的 bit0 标记（或 UniXNU 在 port 侧写
  `/chosen` 的描述），让 `initialize_screen` 自己建立映射；那需要重编固件，
  留到阶段 3 之前处理。
- panic 文本经过 `vcputc` 会重复渲染（屏幕上看得到叠字），拍照取证时以
  内核字符串表交叉核对为准，不要逐字抄屏幕。
