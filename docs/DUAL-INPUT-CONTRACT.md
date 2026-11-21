# TB322FC 双口控制接口核对 · 2026-11-15

本轮没有找到可用于独立选择短口供电的、已核实的 Android/XNU 控制接口。
下面是对固定原厂固件、HAL 和四代 Linux 来源的只读核对，不是双口充电修复。
不据此发送未支持的 UCSI 命令、复用升压控制或改写充电寄存器。

## 固件接口

| 路径 | 实际行为 | 对移植的意义 |
| --- | --- | --- |
| `0x6003fdc0..0x6003fe60` | 按已经选中的输入分发限流写入 | 旧分析中的“selected-input-setter”不是选口器 |
| `0x6003fb40` | 读取 `0x270b` bit4 判断当前输入 | 状态读取不改变输入选择；USB property5 / battery_id 也不提供独立选口 |
| UCSI 主分发表 `0x60262a4c` | command 减2后只接受无符号值0..17，部分表项仍是默认错误路径 | `0x14` 和 `0x1c SET_SINK_PATH` 均越界；新版 Linux 头中的常量不证明原厂支持 |
| `0x60098850..0x60098b64` | USB 与第二输入分别有 suspend 参数，值2表示该输入不修改 | 找到的独立组合调用属于 external boost / haptics boost，不是可直接使用的上层选口协议 |

UCSI 即时分发表也有同一上界，默认路径返回 `0x202`。已有 v139 日志报告
`version=110 buffer=48 connectors=2`；不能据此套用新版 UCSI 的 sink-path 控制。
原厂内部存在单路暂停能力，不等于已经找到了安全、可调用的主机接口。

## Lenovo HAL 与“旁路”的边界

固定 HAL 的成员偏移 `0x178` 指向
`/sys/class/power_supply/battery/bypass_setting`。setter/getter 分别调用普通文件
写入/读取助手 `0x9850` / `0x8e94`；日志中的 `to bypass-battery command`
不是已证明的 shell fallback。

本轮 Android 只读记录确认机型 TB322FC；该 sysfs 节点不存在，`charging_enable=1`。
所以通用 HAL 内含这个字符串，不能证明本机系统导出了对应功能。
现有命令名 `bypass` 的实机证据是充电许可关闭并回读成功，恢复 stock 后许可为1。
**真实系统供电旁路、电池电流行为和双口选择仍需独立验收。** 命令名称保留兼容，
但不把“暂停充电”扩大为已经证明电池隔离或由适配器独立供电。

固定四代 Linux 的 `qcom_smbx.c` 仅定义 `INPUT_PRIORITY_BIT`，所查文件无使用处。
该旧直接 PMIC 驱动不是本机 PMIH 寄存器映射证据，不能猜测平移到 `0x2962` 写入。

## 四代参考与原厂对照（2026-11-22）

- ArmadaOS `0903` 通过 `BATTMGR_BAT_PROPERTY_SET`（`0x31`）写入
  `BATT_CHG_CTRL_LIM`（10），并读取 10／11。补丁描述把电池恒流设为 0 的旁路用法。
  本机原厂运行的是 `qti_battery_charger`，两个对应 sysfs 文件权限均为只读，实读
  6,500,000／13,000,000 µA。原厂源码的内部写路径会施加温控和限制策略，
  sysfs 可写的 start/end threshold 是另一条接口。复制 Linux 写法前需要证明原厂固件
  如何聚合恒流限额、恢复后是否保留温控限制，以及系统负载是否确由适配器承担。
  [ArmadaOS 0903](https://github.com/ArmadaOS-Freedom/armadaos-freedom/blob/d4c3b13a96c5fca9899368e141da2620e9b42e98/packages/kernel/patches/0903-power-supply-qcom-battmgr-expose-the-charge-current-limit.patch) · [原厂实录](evidence/charge-stock-contract-20261122.json)
- 四代 Linux 的 `162315e856e3c` 实机区分手柄、PC 和纯电源伙伴，令无 USB 能力的
  电源伙伴释放数据 mux。`bf96c3d404897` 把共享 DWC3 数据角色切换移入工作队列，
  保留长边数据优先。其作用范围是数据角色与共享 PHY/mux。短边输入是否承担系统负载
  仍需测量。[四代实机记录](https://github.com/h0cheung/tb322fc-linux-kernel/commit/162315e856e3c12f9b606139700c562670d45d8d)
- 四代 `ucsi/psy.c` 用 PD RDO 的工作电流实现 `current_now`。原厂满电快照的
  第二连接器报告 5 V／3 A，聚合 USB 报 SDP／500 mA 限额，电池为 0 mA。
  三者分别用于判断合同、输入限额和电池端状态。Sheng 也将原厂 ADSP、USB 电源
  与电池读数分别采集，其 CDP 实录只用于核对采集结构。
  [Sheng 充电记录](https://github.com/UniXNU/UniXNU-sheng/blob/c477570bb91b2971f90919f3e59d0f056cf0a1de/reports/sheng-linux-charge-734.json)

## 证据与复现

[核对结果](evidence/dual-input-contract.json)保存完整输入 SHA、12 个指令检查、
18 项分发表、函数范围/字节摘要、HAL 路径和已有 Android/UCSI 记录。
Linux 固定为 `6f97250ead155fc3b980856323e99a4623dae73d`，沿 ArmadaOS 四代
README 指向的 SM8750 来源；不使用 TB321FU/SM8650 寄存器。

使用 `tools/analysis/audit_dual_input_contract.py --help` 查看显式输入参数。
该工具只读取原厂 ADSP ELF、其完整反汇编、原 HAL、固定 Linux Git 对象与可选日志；
三份二进制/反汇编均有固定 SHA 检查，输出必须是新目录，不访问设备。
工作台 `lab/records/dual-input-bypass-20261115/audit3` 是最终输出；初次路径长度
检查失败保留在 `audit`，中间通过结果保留在 `audit2`。最终输出使用明确 UTF-8/LF，
文件摘要与实际输出字节一致。

后续只在找到具体原厂上层协议和供电保护前提后准备新候选；现阶段保留双口、净充电、
完整保护周期等缺口，不重复已否定的写口试验。充电总状态见 [CHARGING-STATUS.md](CHARGING-STATUS.md)。
