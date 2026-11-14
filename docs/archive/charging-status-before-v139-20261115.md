# 充电状态与电池界面 · 2026-11-13

11月15日：v137延后PC连接的蓝牙测试在WCN供电准备stage1返回-19，未进入固件下载。
该错误不能据现有日志归因于具体rail、PLL或充电。v138保留所有原检查，新增拒绝时只打印
已保存的准入快照（未读槽可为0），不增加寄存器读取/写入；本轮通过且未触发该错误日志。
这不是双口充电或完整保护周期验收，也不证明瞬态电源问题已经消除。

11月14日后续：SPMI共用事务锁已在v111整核实测，54次双口ADC读取成功、温控武装、
WCN电源通过，v113/v114也未再记录ADC/SPMI失败。此前“仅组件”记录由此更新。
这是共享总线与温控稳定性进展，双口输入选择、净充电、完整旁路/阈值周期仍未完成；
不能把温控运行或高SOC下电流当作快充验收。

11月14日复核：v109已合并真实电池界面与8GiB/触控，不再是仅v96的独立候选。
双口选择/净充电/完整保护周期仍未完成，失败GLINK/AP写口未重试。ArmadaOS固定
885fd1f的四代README同样列充电/双USB为未完善项，没有新成功实现可直接搬。
参考同步20261113-191046核45仓无远端新提交，两既有失效远端保持。

蓝牙v110两轮在初次GPIO读取返回SPMI0x9时，ADC第二端口读取同样失败，温控未武装。
同板Linux将0x9解释为DONE+transaction-dropped，且按总线锁包围整个事务；当前ADC与
WCN各自资源锁未覆盖共享bus0/EE0事务。新[EldenSpmi](../drivers/EldenSpmi/README.md)
已完成真实读函数并发/错误测试及四个native组件编译，**尚未整核/实机**，因此不能
说它已解决充电或证明0x9只来自并发。下一次同时检查两个端口温控与WCN，不绕过保护。

充电驱动尚未完整验收。原厂固件、UCSI事件/合同、保护模式和回程已有实证；
双口取电、净充电能力及完整保护周期仍有缺口。GPU最后，扬声器启用前先讨论保护。
用户11月13日已恢复无人值守真机授权。v96电池发布功能已验证并恢复Android，
原11月12日离线证据及冻结镜像保留。

本轮62次发布从cycle5开始：初始化默认值先被拒绝，两次合格采样后才注册。
状态栏原尺寸238×96回读全部行与CRC通过，明确显示96%，与驱动一致；
末次4.380V、30.70°C，末10轮有符号电流中位−413.5mA，显示未充电是正确的。
日志5431844B、drop28；同步RPC、fastboot实枚举及stock完整SHA恢复均通过。
这完成当前接线下的单位/发布/UI验证；高96%SOC和端口2的5V/3A合同不能证明快充功率。
见[本轮证据](evidence/v96-battery-live-20261113.json)。

## 实证与缺口

| 功能 | 已有证据 | 未完成 |
| --- | --- | --- |
| 原厂充电通信 | ADSP/GLINK、DA65通知/ACK、9V合同及输入暂停恢复通过 | 所有插拔、源切换与失败回退 |
| 短边单口PD | 11月11日iPadOS内用户两轮读表约14.87/15.65W | 电池稳态净充电、峰值功率与兼容性 |
| 原生双口 | 长边PC接回后短边读表约0W；原厂报告优先级/撤票条件已追到精确固件 | 保持长边数据且由短边PD供电的安全实现 |
| 旁路/80%/40–60% | 原厂28/29属性、五阶段读回及stock恢复通过 | 正常UI负载旁路、完整阈值循环、设置持久化 |
| 电池显示 | v96双FG准入、62次真实发布、状态栏96%通过 | 链路失败/重连、插拔及完整保护周期下的UI仍需验收；尚未与v100合并 |

不得把9V合同、online或输入功率当成电池净充电。两口的隔离/反灌保护仍由原厂控制，
不能因为长边优先就强写GPIO/FET或提高SDP预算。原GLINK WRITE status1与AP写FIFO外部异常
已经否定的路径不重复尝试，也不以debug override撤销固件投票。

工作台原始证据为 `archive/research-notes/HANDOVER-PD-DISCONNECT-20261111.md`、
`lab/records/charge-control-route-20261111/`、`edl_work/charge-modes-input-fix-20261109/`。
最新v94电源观察与候选身份见[电池候选记录](evidence/v96-battery-ui.json)。

## 原厂online属性的准确语义

进一步对精确原ADSP固件完成19处锚点复核，结果见
[电源报告映射](evidence/oem-power-report-map.json)。USB GET0x32由platform3回调
`0x600684c0`读取context+0x724+4×property；WLS GET0x34由`0x60068850`
读取context+0x758+4×property。这些是软件报告字段，不是逐口硬件测量地址。

原报告循环先处理输入0；输入0在线时，输入1跳过USB报告更新。输入0离线时，
输入1仍会更新USB-online/type等字段，然后更新第二路报告。
所以当前ChargePolicy检查USB-online，**不等于只允许长边电脑口供电**。
尚无证据表明应把该门改成 `USB-online || WLS-online` 来修短边模式；本轮未做这项修改。
两口身份不能只从属性名推断，仍应结合原厂49/50、UCSI、输入选择与实际功率。

WLS GET包装函数`0x601ea930`会在底层返回错误后记录日志，并在合法参数路径返回0；
USB包装函数则保留底层返回码。协议应答成功只说明该层成功，不证明WLS数值已采样正确。
两组online还可能被固件状态8/9置零；这里没有给这两个状态猜名称。
保留现有双FG校验与原厂保护，不据此伪造数据、重试已拒绝WRITE或增加控制权限。

离线复核入口（只读私有输入，证据输出到新的lab目录）：

```text
python tools/analysis/audit_oem_power_reports.py --firmware STOCK_ADSP_MBN --assembly CHARGER_PD_DISASSEMBLY --output NEW_EVIDENCE_DIRECTORY
```

工具绑定原件与完整反汇编SHA，输出所用字段映射和每段原机器码SHA；没有执行固件。
下一项充电硬件证据仍是准确捕获切换后的逻辑online、合同/投票、实际功率和恢复，
不重复已否定的写接口。v94/v95/v96均未因参考更新换料。

11月13日上游b952733的电池改动保持已知online/status、处理合并的掉线/上线事件，
并为小米键盘属性0xe4排队；其新增部分只有host证据，作者明确未量出充电改善。
Elden已采用完整新鲜快照、epoch、双FG准入和unavailable路径，不重复移植未知值保护。
小米键盘属性与其默认SDP电流不能用于本机双口仲裁。最新官方power指南同样要求
保留固件充电所有权，并分别证明协议、测量和OS服务。

## 候选来源：v94 GUI菜单缺少电池发布

v94日志明确显示 `ELDEN_BATTERY qualified data-only; UI disabled`，启动菜单确实没有
elden-battery/profile/current三项。初始50%/4V/4A默认值被双FG校验拒绝，cycle5才进入合格状态；
不是应该解除校验门。最后10轮聚合电流仍为正的raw值，即净放电，不能宣称显示提速已解决供电。
这些是已有捕获数据，不是本轮对设备的新读取，也不用于估计现在的电量。

v96只恢复既有发布器：`elden-battery=1 elden-battery-profile=1 elden-battery-current=-1`。
使用完整同一v94内核、FD、loader、ADT、Data和trustcache，不含v95成对存储改动。
不改电流、功率协商、FET、保护阈值、模式请求或持久磁盘内容。

原v94主条目占1023字节。`battery_boot.py`将明确列出的34个数值1选项改成裸键，
不删除选项、不缩短回程或监控期限；两个安全相关参数保留原文。加入三项电池配置后共1020字节，
包含终止NUL仍适合1024字节字段。默认打包行为不变，必须显式传 `--battery-ui`。
审计器独立比较解析后的所有选项，只允许三项新增；其他条目和菜单设置必须一致。

参数语义使用该冻结XNU实际的 `pexpert/gen/bootargs.c`（SHA
`814d2f779300bfbf7ef13c8c830ae0f98ada271586518b808d43a019a7e7db3a`）做420项ASan/UBSan检查，
覆盖32/64位数值和字符串读取；另有菜单重复键、负电流符号、超长、热控、回程和fallback变更拒绝。
主机头文件只替代未使用的设备树接口，不修改解析器。Linux int64_t typedef导致未调用range函数的
两条指针类型警告保留；参数解析检查完成，没有sanitizer报错。

## 离线候选与复现

- 镜像：工作台 `edl_work/battery-ui-v96-20261112/candidate/boot-signed.img`
- SHA256：`1a9e76212c77fe2d6eb4f8e402804f313048774c3998631267612db2563372da`
- session：`30a09b6552dc35e4`
- 内核：`3fe39a54f2ff31683511dce6871a05853b6e6ad8aa487c290be497501bf8be60`，与v94相同
- floor：1738713600@footer0，父链3；独立FAT/资产/entry/AVB核验通过；11月13日已完成上述实机发布验证。

按[源码复现](REPRODUCIBILITY.md)使用已核v94 entry/kernel与build-result，
`build_v91_boot.py`及`audit_v91_boot.py`均在原参数上增加 `--battery-ui`。
主机菜单检查可用 `py -3.12 -B tools/test_battery_boot.py`。
实际解析器复核需重建XNU的原始文件与Linux GCC：
`python3 tools/test_battery_boot.py --parser-source PATH/pexpert/gen/bootargs.c --work NEW_SCRATCH_DIRECTORY`。
输出保留，不自动删除；脚本需要Python3.11+的tomllib。

本轮验证了两个合格采样前不发布虚假电量，之后显示真实SOC/温度/电流；
拔线或供电协议验证另按已记录的接线判据，不把状态栏图标当电气验收。
真实手指仍优先用原已验v94，避免将两个未验证因素混为一次触控结果。
