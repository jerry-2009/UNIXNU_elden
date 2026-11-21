# TB322FC 的 HTT 请求与 TCL 元数据

小米 Pad 8 Pro 的实机 10f-c 在 legacy PHY/TID 0 下收到 EAPOL message 3，完成 WPA2 和密钥安装。两个 EAPOL 完成项来自固件，随后 10g 实测取得 DHCP 租约并访问网关。Elden 也用 legacy PHY，已收到 message 1 并提交 message 2，TCL 消费 1，WBM 完成 0。[Pad 8 Pro 实录](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/drivers/wifi.md#88-the-batched-tablet-test-list) · [Elden 实录](../../../../docs/evidence/wifi-station-tx-priority-hardware-20261121.json)

原厂 `qca_cld3_peach_v2.ko` SHA256 为 `33869cd650843656e216b092809b9cd7327865abb1b6b9dfcd55399abd600d76`。`htt_soc_attach_target` 在 `0x6804` 至 `0x6824` 填充一个 32 位零请求。`dp_tx_vdev_attach` 在 `0x54b44` 和 `0x54b84` 将 VDEV 从 bit 2、目标 PDEV 从 bit 10 编码。`wma_vdev_start_resp_handler` 在 `0x3ab424` 至 `0x3ab434` 根据 `use_pdev_id` 处理 VDEV 响应中的 PDEV，并依据响应计算逻辑 MAC。Elden 现有 WMI 设置为 `use_pdev_id=1`，实机 VDEV 0 的成功响应报告目标 PDEV 1。ArmadaOS-Freedom 的 WCN7860 HW2.0 条目确认单 PDEV 模式。候选据此把元数据由 `0x0001` 改为 `0x0401`，TCL PMAC 保持逻辑 MAC 0。[ArmadaOS TB322FC 源码入口](https://github.com/ArmadaOS-Freedom/armadaos-freedom/blob/main/devices/lenovo-tb322fc/README.md#源码与来源)

派生只接入 station 对象。匹配当前 VDEV、启动阶段、请求类型、成功状态及目标 PDEV 1 后，现有发送队列才启用。沿用已验收的 PMK 就绪逻辑、OEM WMI 命令格式、原厂固件、DMA、TCL/WBM 环和实机回程。

在 CiscoMac 用 PMK 就绪 `runtime2` 构建。

~~~sh
python tools/build_wifi_station_tx_priority.py --oem-metadata \
  --parent-build TESTED_READY_RUNTIME --llvm LLVM_BIN --output NEW_RUNTIME
~~~

随后按 [完整 station](README.md) 链接整核并运行资格检查。CiscoMac 输出 ARM64 绑定 `bfe30098`、内核 `ce445c6a`、签名 boot `3f8f74e1`。21 项错误组合被拒绝，30 个原始 Apple 执行区及入口返回通过审查。下一次实机先确认本轮发送元数据和 WBM 来源，再通过 message 3/4、密钥、授权及 DHCP 和流量判定连通。
