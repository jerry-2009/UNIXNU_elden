# TB322FC 的 HTT 请求与 TCL 元数据

小米 Pad 8 Pro 的实机 10f-c 在 legacy PHY/TID 0 下收到 EAPOL message 3，完成 WPA2 和密钥安装。两个 EAPOL 完成项来自固件，随后 10g 实测取得 DHCP 租约并访问网关。Elden 也用 legacy PHY，已收到 message 1 并提交 message 2，TCL 消费 1，WBM 完成 0。[Pad 8 Pro 实录](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/drivers/wifi.md#88-the-batched-tablet-test-list) · [Elden 实录](../../../../docs/evidence/wifi-station-tx-priority-hardware-20261121.json)

原厂 `qca_cld3_peach_v2.ko` SHA256 为 `33869cd650843656e216b092809b9cd7327865abb1b6b9dfcd55399abd600d76`。`htt_soc_attach_target` 在 `0x6804` 至 `0x6824` 填充一个 32 位零请求。`dp_tx_vdev_attach` 在 `0x54b44` 和 `0x54b84` 将 VDEV 从 bit 2、目标 PDEV 从 bit 10 编码。`wma_vdev_start_resp_handler` 在 `0x3ab424` 至 `0x3ab434` 根据 `use_pdev_id` 处理 VDEV 响应中的 PDEV，并依据响应计算逻辑 MAC。实机 VDEV 0 的成功响应报告目标 PDEV 1。原厂 `convert_host_pdev_id_to_target_pdev_id()` 在未使用 PDEV map 时把 host PDEV 0 映射成目标 PDEV 1；所以 VDEV_CREATE 继续用 PDEV 0 表示 SoC 级，不能把目标 `1` 填进 VDEV_CREATE。只在 TCL 元数据中使用响应确认的目标 PDEV 1。ArmadaOS-Freedom 的 WCN7860 HW2.0 条目确认单 PDEV 模式。候选据此把元数据由 `0x0001` 改为 `0x0401`，TCL PMAC 保持逻辑 MAC 0。[原厂转换实现](../../../../../../Patch/Y700-Elden/lab/records/wifi-station-tx-20261121/oem-audit/wmi_unified_tlv.c) · [ArmadaOS TB322FC 源码入口](https://github.com/ArmadaOS-Freedom/armadaos-freedom/blob/main/devices/lenovo-tb322fc/README.md#源码与来源)

派生只接入 station 对象。匹配当前 VDEV、启动阶段、请求类型、成功状态及目标 PDEV 1 后，现有发送队列才启用。沿用已验收的 PMK 就绪逻辑、OEM WMI 命令格式、原厂固件、DMA、TCL/WBM 环和实机回程。

在 CiscoMac 用 PMK 就绪 `runtime2` 构建。

~~~sh
python tools/build_wifi_station_tx_priority.py --oem-metadata \
  --parent-build TESTED_READY_RUNTIME --llvm LLVM_BIN --output NEW_RUNTIME
~~~

随后按 [完整 station](README.md) 链接整核并运行资格检查。CiscoMac 输出 ARM64 绑定 `bfe30098`、内核 `ce445c6a`、签名 boot `3f8f74e1`。21 项错误组合被拒绝，30 个原始 Apple 执行区及入口返回通过审查。下一次实机先确认本轮发送元数据和 WBM 来源，再通过 message 3/4、密钥、授权及 DHCP 和流量判定连通。

用 Apple clang 运行了 `TestProfileReady.cpp` 的 `ELDEN_TEST_OEM_METADATA` 分支，直接包含生成的 station 源码。它核对 4 字节请求，确认 PDEV 2 不能启用当前单 PDEV 发送路径，使用 PDEV 1 启用后实际入环的描述符第 3 字为 `0x04010000`、第 5 字保持 TID 0。寄存器与 DMA 在这项测试中由宿主模型提供。

原厂 `send_setup_install_key_cmd_tlv` 的固定体为 100 字节，与现有 donor 的 25 字匹配。密钥、计数器和完成事件状态的位置也已按原厂函数核对。

单字 HTT 候选实测在第二轮扫描前退回。新的发送候选使用八字节 HTT 和原 TCL 元数据，在已有 EAPOL 控制端口发送路径提交 critical flow override 与 semi-hard notify。Legacy 保持 TID 0，WMM 仍用 TID 7。分类来自当前站点发送队列，范围为 EAPOL，原厂通用 critical 分类仍由其上层决定。

用 `--oem-eapol-critical` 从同一 profile-ready 父构建，再按 station 路径合成和审查。测试执行真实队列到 TCL 发送函数，核对 legacy、WMM 和后续普通数据，并确认 HTT 长度及 TX 元数据保持。该测试用宿主 MMIO/DMA。签名实测候选为 `60ca685d`，会话 `e29fe911571aa175`。

单 PDEV bank 对照在 `--oem-eapol-critical` 上加 `--single-pdev-bank`。原厂模块
`dp_vdev_attach_be` 在 `0x3e7c8c` 清除 vdev 偏移 `0xa3c9` 的布尔值；
`dp_tx_get_bank_profile` 在 `0x3ef10c` 读取同一偏移，随后在 `0x3ef158`
至 `0x3ef15c` 把它编码到 bit 14。ArmadaOS 四代内核的 HAL 对该位定义相同。
此对照把实测的 `0x4a04` 改为 `0x0a04`，保留八字节 HTT、VDEV 关联与描述符 ID、
既有索引／地址查找设置及 EAPOL 描述符。原厂 index-search 分支另有组播策略，
该分支的适用条件与当前 VDEV 状态仍待确认。

CiscoMac 的实际发送路径测试验证了 bank 写值和普通帧行为。完整 ARM64 链接及
20 项拒绝用例通过，签名候选 `c9427d2f` 的会话是 `6f87a81d1e1da868`。
