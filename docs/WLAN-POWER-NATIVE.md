# WLAN原生供电接入：组件已编译，尚未上机

2026-11-22：Wi-Fi network-17 的 Bluetooth 消失原因已定位为候选启动参数
`mode=0`，不是 QcaBluetooth 源码被删除。`BatteryAdmissionSource.wcn()` 继续
使用共享 WCN owner，并增加只读的 `elden_wifi_battery_available()` 门。只有经
shared-owner 资格标记的候选菜单才加入 `elden-wcn-power=4`。变更保持电池、GLINK、
WLAN 和 Bluetooth 共用同一 owner。host 回归通过，整核与实机验收仍未完成。

冷启动顺序更正：现区分预期板级身份取得供电与上电后实读端点身份，后者确认前QMI不准入。
见[PCIe冷启动组件](../drivers/EldenPcie/README.md)；旧文中的“先验证实际端点再上电”不适用于断电芯片。

后续：准确Linux QMI回调桥接已完成，见[QMI供电接入](../drivers/EldenWifi/QMI-POWER.md)。
与125个Wi-Fi对象及两供电对象的可重定位链接通过；实际PCIe/MHI caller、整核和硬件仍未完成。

2026-11-15已把[共享WCN核心](WCN-SHARED-POWER.md)接到原生物理回调，新增独立WLAN
取得/检查/CPR/停止入口，并把蓝牙入口迁移到同一平台owner。**本轮到ARM64组件编译，
还没有整核链接、boot镜像、真实WLAN供电或联网验收。** 现有v156/stock候选不变。

## 本机来源与实现

来源仍为ArmadaOS TB322FC→h0cheung `6f97250ead155fc3b980856323e99a4623dae73d`。
已逐文件核Git blob：`sm8750-lenovo-elden.dts`、`pinctrl-sm8750.c`、`pinctrl-msm.c`。
WLAN_EN是GPIO16，GPIO模式、16mA、上拉；不是TB321FU/SM8650配置。

| 字段 | 来源确定的值 |
| --- | --- |
| 每GPIO页跨度/CTL/IO/IRQ配置偏移 | 0x1000 / 0 / 4 / 8 |
| mux/pull/drive/OE字段 | bit2起4位 / bit0起2位 / bit6起3位 / bit9 |
| 输入/输出锁存位 | bit0 / bit1 |
| eGPIO存在/本地owner位 | bit11 / bit12 |
| 本机GPIO输出配置低10位 | 0x3c3：16mA、GPIO、上拉、OE |

`WlanGpio.h`先置低锁存，再使能输出，并核回读。非GPIO复用、已有IRQ、远端eGPIO
ownership、首次输入已高均拒绝；不抢占未知消费者。随后只改本GPIO输出锁存，保留
其他位，输入最多等待1ms。它不访问PERST、WAKE、SW_CTRL、其他GPIO或充电选路。
初始读错误不做写入；事务已开始后的不确定结果由共享owner保留至复位。

`SharedNativeSource.py`以已归仓的v116源和现有AdmissionTraceSource为输入，保留其
SPMI总线门、QMP/RPMh错误处理、HCI启动和固件路径。它只把供电资源生命周期移到
平台owner，并加入WLAN回调；旧冻结源不改写。

- 平台Context只初始化/映射一次，公布后由平台持有至复位。WLAN无需准备蓝牙固件，
  蓝牙退出不释放WLAN仍使用的映射或票。
- GPIO/供电事务串行，最长等待门1秒且受回程剩余期限限制；没有重发硬件命令。
  新原子lease查询可在另一设备的事务期间继续报告原有有效会话，停止/故障则撤销。
- WLAN入口需要显式`elden-wlan-power=1`、既有恢复/Data/用户态准入、provider、
  PCI17cb:110e、RID100、SID1401及quiesce回调。PCIe驱动须先实读验证这些身份；
  入口参数本身不构成PCIe枚举证据。
- provider身份与单调epoch绑定，旧token不能发送CPR或停止新会话。CPR返回真实
  共享提供者结果，不绕过QMP失败。
- 停止先撤销WLAN后续请求，再调用设备提供者的DMA quiesce，成功且未超时才拉低
  WLAN_EN。quiesce失败/迟到不写GPIO、不释放映射。恢复入口关闭全局准入，并将
  原9秒回程等待期限传给WLAN阶段；设备回调必须遵守同一单调微秒期限。

## 验证结果及范围

共享核心最终335场景/53892检查，ASan/UBSan通过，包含上一版130旧实现差分和1000轮
“WLAN取得期间蓝牙lease仍有效”并发查询。实际原生helper/export函数和GPIO函数的
38场景/141检查通过：两种启动顺序、独立停止、旧provider拒绝、禁用/准入拒绝、
映射失败、quiesce失败/迟到、eGPIO/IRQ/复用拒绝、每个GPIO读取失败、卡住输入。
内核服务与物理传输均为host模型；未执行完整原蓝牙worker，也不算真机验收。

ARM64/iOS17两个实际对象：

- 共享WcnPower：`64c5c8b9dcf50c8ae3f79a2c2022fb393e117eef3feefcf7c46e8d2163a0eb65`。
- 原生WcnPowerNative：`cae33bea2c14de22519b3cdb33e91b3bc5742001a4e064a402ae75aa002f3cea`。

原生对象保留原导出并增加4个WLAN入口，5个共享provider导入真实存在；旧BT-only
acquire/stop/finish导入已移除。无FP/SIMD或自动初始化。原生仍有1条既有
`boot_manufacturer`整数转换警告，表达式与冻结源相同，未宣称零警告。
共享对象17导出、零警告；还没有完整链接验证这些对象与其余内核的组合。

复现（各输出必须是新目录）：

```powershell
py -3.12 tools/test_wcn_shared_power.py --wsl-distro Ubuntu --output C:/Users/Public/wcn-owner-new
py -3.12 tools/test_wlan_power_native.py --wsl-distro Ubuntu --output C:/Users/Public/wlan-native-test
```

```sh
python3 tools/build_shared_wcn_cpr.py --llvm /path/to/llvm/bin --output /new/core
python3 tools/build_wlan_power_native.py --clean-build /path/to/source-built/unified --llvm /path/to/llvm/bin --output /new/native
```

`--clean-build`是正式`build_clean.py`的源代码构建输出，用其已核SDK/编译命令，不依赖
v99留存二进制。源码输入与overlay逐项核对；最终生成源SHA为
`2412f3beda4375c8fb6292fc74f84b91e78fcf2620a7cf14a9545d6aa04782a1`。
结构化[证据](evidence/wlan-native-20261115.json)绑定全部输入。
Mac `lab/wlan-native-20261115/{core1,native2}`；工作台`edl_work/wlan-native-20261115`
及`lab/records/wlan-native-20261115/{core2,host3}`。早期编译和测试保留，未清理。

## 下一步

1. 将实际Linux `pwrseq_qcom_wcn_set_ol_cpr`消费者绑定到本机provider/epoch，使用
   `include/linux/pwrseq/qcom_wcn.h`的准确32字节pin/16参数格式，返回真实错误。
   当前尚未提供该Linux符号，不得用无条件成功补链接。
2. 接上真实PCIe/MHI提供者及有期限的DMA停止回调；加入当前整核源码构建，并同时
   替换共享WcnPower与WcnPowerNative。新旧owner不能并行操作同一硬件。
3. 完成整核/入口/原Apple执行区/自动回程审计后，才安排一次有判据的硬件窗口。
   仍要保留充电优先级；扫描、关联、DHCP和流量尚未完成，不把上电当网络可用。
