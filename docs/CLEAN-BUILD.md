# 从新克隆构建 GUI / 蓝牙分支

入口是 `tools/build_clean.py`。它不需要旧 v99 构建目录、Patch 工作台、旧内核、
2026-11-18空输出复测发现蓝牙基线误从当前仓读取已更新的WcnPower.c，导致原指纹拒绝。
现在该基线只读仓内固定源码快照，字节来自89b31f6599068d63792c3b124f775fcac0f6c2da，
仍保持原feb9fefa…指纹；当前共享电源实现不改动。来源见
[固定输入证据](../profiles/current-build/frozen/source-proof.json)，新空输出验证继续进行。

入口不需要
旧对象或旧驱动归档。`--variant gui` 对应8GiB交互v109；`--variant bluetooth`
对应v121蓝牙诊断分支（6GiB），具有真实HCI初始化和退出/stderr观察，蓝牙用户态
尚未连接成功。两者保持独立，不把它们冒称为已实机合并的配置。

本轮新克隆下已从源码重建全部基础对象、蓝牙30个/GUI10个变化单元、两个内核、
UEFI、加载器、Data种子和两个签名boot，完成静态核验。两个分支的统一命令均已从
空输出目录完整运行通过。旧目录受sandbox禁止读取时，蓝牙30个单元通过；GUI的
9个单元通过，另一个汇编输入预检查漏点被抓出并修正，修正后也通过。构建成功不等于这两份
新像已实机验证。保留旧profile作为实验记录，不要求先跑全部历史轮次。

## 环境

- macOS、完整 Xcode 和 iPhoneOS SDK。验证工具链：Apple clang17、SDK26.2、LLVM20。
- Python3.12，`python3.12 -m venv .venv`，然后 `.venv/bin/pip install -r requirements-build.txt`。
- Git、make、macOS codesign/hdiutil/diskutil/fsck_apfs。firmware构建需要其固定Mu源与子模块。
- 完整boot的固定Data种子要求UID501或root；内核目标不受此限制，入口会提前检查。
- 当前原生编译/签名使用 macOS 工具；**不宣称 WSL 原生构建已实现**。生成的boot可交给
  Windows设备工具刷写，但这条构建命令不调用WSL或任何平板。

FAT16由仓库自己的写入器产生，已用独立fsck.fat核验，不依赖mtools/dosfstools。
验证命令使用LLVM路径中的clang；不存在固定D盘或某位开发者实际home目录的输入。

## 外部输入

复制 `config/clean-build.inputs.example.json` 到自己的配置位置，填写路径。
四组常见缺失输入的来源、准确目录层级和校验方法见[CLEAN-INPUTS.md](CLEAN-INPUTS.md)。
相对路径以该JSON所在目录为基准。原版系统和固件是合法自备输入，不能以历史构建
产物替代，也不提交Git。不要将签名私钥、个人userdata或设备备份交进源码仓。

| 输入 | 来源/约束 |
| --- | --- |
| original_agent | 原21H461系统中的iconservicesagent，SHA256 dd01b74e4413e0bb72de4a62f3f7675deb5026cad79d376fde6570abd0d012f8 |
| original_kernelcache | 原21H461 KernelCache解包/解压结果，准确SHA见profiles/v91/image-build/plan.json；原Apple组件来自它 |
| os_image | 原21H461 OS裸镜像，Data种子清单核SHA和所需文件；不是旧Data分区 |
| nvt_firmware | TB322FC原厂novatek_ts_csot_3k_fw.bin，253952B/SHA413216d0…；生成完整头文件 |
| wcn_firmware | 目录下包含qca/brhbtfw20.tlv、qca/brhperifw20.tlv、qca/brhperinv20.bin、qca/tmel_peach_20.elf、qca/lenovo/tb322fc/brhbtnv20.bin；全SHA在profiles/v110-bt-fifo/plan.json |
| crypto | Microsoft Project Mu CryptoBin v1.1.3的解压根目录；先运行 `python3 tools/fetch_basecrypto.py --output ../inputs/basecrypto`，填入其输出的绝对路径。官方链接和994件核验见CLEAN-INPUTS.md |
| mu_repository | mu_wide_platforms Git源和初始化子模块，必须包含firmware-build/plan.json的mu_commit及子模块Git对象；builder只导出固定对象，不拿工作树修改 |
| unixnu_repository | 官方UniXNU Git源，包含固定unixnu_commit与drivers/DarwinBoot子模块对象；同样只导出固定对象 |
| stock_boot / parent_vbmeta | 本项目准确stock签名模板，供不抬升floor的审核/打包；不是待重编内核 |
| avbtool / signing_key | 自备签名工具及匹配测试签名材料，输出仍检查1738713600/footer0/parent3 |

普通XNU、corecrypto源码、libpthread、libdispatch、libplatform、XnuPrelink由入口按
公开URL和固定完整commit获取到**本轮输出的dependencies目录**，不检查或改动别人的
工作树。Mu/UniXNU固件源可用以下配套命令获取，再把两个目录填入JSON：

```sh
.venv/bin/python -B tools/fetch_clean_firmware_sources.py --output /path/to/fresh/research
```

它只创建新克隆并固定递归子模块，拒绝覆盖已有目录；也可直接提供含相同固定Git对象
的已有源仓。不要用早期 `bootstrap_third_party.py` 的默认pin代替这里的构建版本，
缺少子模块时也不能用旧UEFI产物替代。

## 命令

[2GiB稀疏Data](../profiles/data-capacity-2g-key/README.md#clean-build)提供当前空间修复的完整命令，
`--data-capacity-2g`同时重编实际KeyStore适配器并启用PackedRAMDisk；不加选项仍生成512MiB。
新组合的空输出整链验收仍待运行，已有组件/实机证据见该profile。

充电旁路退出修订的完整选项链见
[charge-window-handoff](../profiles/charge-window-handoff/README.md#build)。
恢复系统亮度服务时再加 `--backlight-service`，见[该配置的实机记录](../profiles/backlight-service/README.md)。
PD确认后进行功耗试验使用 `--pd-power-trial`，见[独立试验配置](../profiles/pd-power-trial/README.md)；它不是普通GUI日用配置。
需要PD初始化与正常系统亮度服务共同运行时使用 `--pd-gui`，见[GUI整合配置](../profiles/pd-gui/README.md)。
下方不加额外选项的命令仍构建冻结基础版本，不自动等同于最新实验功能。

```sh
git clone https://github.com/zenkernelsam/UniXNU_elden.git
cd UniXNU_elden
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-build.txt
# 编辑自己的 inputs.json，填入上表原始输入与工具链。
.venv/bin/python -B tools/build_clean.py --variant gui --inputs /path/to/inputs.json --output out/clean-gui --target boot --jobs 4
# 蓝牙诊断分支（不与GUI分支混装）：
.venv/bin/python -B tools/build_clean.py --variant bluetooth --inputs /path/to/inputs.json --output out/clean-bluetooth --target boot --jobs 4
```

只构建内核可用 `--target kernel`，无需OS.raw、UEFI源、Crypto、stock模板或签名键；
GUI分支也不要求蓝牙固件输入。
输出必须新建。`--resume`仅复用本轮已完成且记录一致的阶段；它不会删除失败阶段目录，
失败阶段需要保留诊断后另用新输出继续。目前不对任意中断位置承诺自动恢复。

成功时 `build-state.json` 为complete，`boot/audit.json` 的完整FAT/entry/AVB审核通过。
输出 `boot/boot-signed.img`；工具不访问或刷写设备。原始日志在logs/。

## 为什么清单还可看到旧路径

`profiles/current-build/plan.json` / `profiles/gui-build/plan.json` 中的 `@VROOT@`、历史文件名和调试源文件名是编译器
VFS键，用于保持 `__FILE__` 和字符串合并顺序。实际内容只来自仓库、重新生成的载荷、
固定Git依赖与SDK；Clang使用 `fallthrough:false` 的闭合虚拟文件系统。它不会因为
名字里有某个 `/Users/.../lab` 而读取那个真实目录。

汇编例外已专门处理：Clang驱动在VFS前会检查输入文件存在，所以 `start.s` 先写到
本轮实际目录，再映射其原始源文件名。该漏洞是在禁止旧目录读取的测试中发现并修复的。

与之相对，历史 `build_wcn_kernel.py` / `build_bt_native17_kernel.py` / UART逐轮工具
依赖指定旧产物，是实验增量入口。当前从零构建不调用它们。变化单元直接与
新生成的基础对象/归档组合，最终核对已记录的装载段、地址、符号和原Apple代码区。

不同主机/工具链版本的实测覆盖，以及这两份新生成boot的硬件回归仍未完成。
不要把源码重建通过扩大为新像已上机或全部外围已修复。

蓝牙后续候选可显式添加 `--bt-exit-stack --software-keystore`，参见
[EldenKeyStore](../drivers/EldenKeyStore/README.md)。这两个阶段只消费本次源码
构建的输出，不恢复历史v99依赖；software-keystore目前要求exit-stack同时启用。
当前已分别执行完整基础构建和两个后续阶段，尚未重新执行含这两个选项的全量空目录命令。

v124另加 `--bluetool-launch`，只处理准确自有助手的已观察启动限制失败。
它的源码增量阶段已执行，实机后续USB中断，故仅作为诊断候选；不是新稳定基线。

v125追加 `--bt-transport-trace`，记录有上限的bootstrap与H4回调阶段；两对象来源
和其余链接输入逐项检查。独立阶段已构建并上机，组合全量命令尚未从空输出重跑。

v127在此链上添加 `--bluetool-lifecycle`，从声明的原OS镜像生成四字段修改的
签名缓存，并编译进RAM挂载阶段。不要同时选择更细的 `--bt-syscall-trace`。
缓存挂载与完整回读已实机通过，后续蓝牙/USB停顿仍待修复。

当前蓝牙实验v130还包含registry、助手阶段记录和进程引用修复，可从同一源码入口生成：

```sh
python3 tools/build_clean.py --variant bluetooth --bt-exit-stack \
  --software-keystore --bluetool-launch --bt-transport-trace \
  --bluetool-lifecycle --bt-registry --bt-helper-trace --bt-process-lifetime \
  --inputs inputs.json --output NEW --target boot --jobs 4
```

完整基础构建与这些后续阶段均已执行并生成实测像；这一组完整选项尚未重新从空
输出跑一遍。v130修复了H4连接时的内核引用panic，已有真实收发，但尚未完成配对。
