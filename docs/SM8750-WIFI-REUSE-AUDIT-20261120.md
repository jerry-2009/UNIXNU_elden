# SM8750 Wi-Fi 成功参考审核（2026-11-20）

已审核官方目录的11个机型／23条仓库入口。本轮选择 lenzhang/piano：记录了真实扫描、WPA2、DHCP、公网和睡眠／固件崩溃后重连。
缺乏联网实证的仓库只作为研究参考。5个404及1个API403仍列为未完整审核。

| 项目 | 本轮 HEAD | 网络完成层次 |
| --- | --- | --- |
| [xiaoan919/UniXNU-ace6](https://github.com/xiaoan919/UniXNU-ace6) | 8de1723e196d | 未发现已完成网络路径 |
| [7Night-kqx/UniXNU-dada](https://github.com/7Night-kqx/UniXNU-dada) | 81981cdf6796 | 未发现已完成网络路径 |
| [moeshin/UniXNU-dada2](https://github.com/moeshin/UniXNU-dada2) | 8cbbe69e2a0c | 未发现已完成网络路径 |
| [Nanawwa/UniXNU-dada2](https://github.com/Nanawwa/UniXNU-dada2) | 未取得 | 当前请求失败：HTTP Error 404: Not Found |
| [Biaogo/UniXNU-dodge](https://github.com/Biaogo/UniXNU-dodge) | e9f298d0c6b6 | 明确尚未实现网络 |
| [lihenggui/UniXNU_dodge_SM8750](https://github.com/lihenggui/UniXNU_dodge_SM8750) | 6a527866e437 | transport archive／host 检查，未真机联网 |
| [jerry-2009/UNIXNU_elden](https://github.com/jerry-2009/UNIXNU_elden) | 85478174b22e | 较早 Elden 分支；Wi-Fi 未联网 |
| [TAY0123/UNIXNU_elden](https://github.com/TAY0123/UNIXNU_elden) | fdd0265b7504 | host-only，运行栈未完成 |
| [zenkernelsam/UniXNU_elden](https://github.com/zenkernelsam/UniXNU_elden) | 1b0e0a7f5603 | 本主线；固件／控制服务已运行，BSS0 |
| [wally001012-cyber/UniXNU-erhai](https://github.com/wally001012-cyber/UniXNU-erhai) | 48cf00a7a97f | 未发现已完成网络路径 |
| [xingxing19035/UniXNU-erhai](https://github.com/xingxing19035/UniXNU-erhai) | 未取得 | 当前请求失败：HTTP Error 404: Not Found |
| [zczyh0922/UniXNU-erhai](https://github.com/zczyh0922/UniXNU-erhai) | 未取得 | 当前请求失败：HTTP Error 404: Not Found |
| [2426120557/UniXNU-hummer](https://github.com/2426120557/UniXNU-hummer) | 596d9dcdf59b | 未发现已完成网络路径 |
| [lengxi233/UniXNU-hummer](https://github.com/lengxi233/UniXNU-hummer) | b168b80213f1 | 未发现已完成网络路径 |
| [Nanawwa/UniXNU-miro](https://github.com/Nanawwa/UniXNU-miro) | 70450a8d2644 | 未发现已完成网络路径 |
| [darkplace/UniXNU-Odin3](https://github.com/darkplace/UniXNU-Odin3) | 6d58c09d1529 | 未发现已完成网络路径 |
| [IssacL04/UniXNU-Pagani_SM8750](https://github.com/IssacL04/UniXNU-Pagani_SM8750) | a84204eccb9b | 源码／host-only，未真机联网 |
| [Shad0w23333/UniXNU-Pagani_SM8750](https://github.com/Shad0w23333/UniXNU-Pagani_SM8750) | 25b110978fec | 源码／host-only，未真机联网 |
| [code002-2/piano-macos-unixnu](https://github.com/code002-2/piano-macos-unixnu) | e9ff4f0a8dc5 | firstboot，未发现联网实证 |
| [code002-2/UniXNU-piano](https://github.com/code002-2/UniXNU-piano) | 未取得 | 当前请求失败：HTTP Error 404: Not Found |
| [donyanchen/UniXNU-piano](https://github.com/donyanchen/UniXNU-piano) | 961371c3613a | 未发现联网实证 |
| [lenzhang/UniXNU-xiaomipad8pro](https://github.com/lenzhang/UniXNU-xiaomipad8pro) | 2438556c77c9 | 实机 WPA2／DHCP／公网／睡眠和崩溃后重连 |
| [xiaomi-pad-8-pro-development/android_device_xiaomi_piano-unixnu](https://github.com/xiaomi-pad-8-pro-development/android_device_xiaomi_piano-unixnu) | d4f160c8ee60 | 当前请求失败：HTTP Error 403: rate limit exceeded |

成功证据：
- [docs/results-2026-11-13.md](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/results-2026-11-13.md)，SHA256 `72589a5cec50e061b634f81107bc0c71d89dec3da17fdba3346d1800ff00f526`。
- [docs/results-2026-11-14.md](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/results-2026-11-14.md)，SHA256 `ea6654baee3b5306359825cab569f307e7bc1479747b82205f100e362fc27c0d`。
- [docs/results-2026-11-17.md](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/results-2026-11-17.md)，SHA256 `21d68154f8180c678c244179a24db5ac2ce1fa410b23d6ebbdf9b3cada066ad6`。
- [docs/drivers/wifi.md](https://github.com/lenzhang/UniXNU-xiaomipad8pro/blob/2438556c77c90c22c7b76e57eb8b40c44b35f1af/docs/drivers/wifi.md)，SHA256 `29d63f258eec4d4a186deb99836d209b898aa5a2ab1b23f62eec0674f504e9b0`。

新克隆：`research/UniXNU-xiaomipad8pro-lenzhang`。固定选中版本见正式仓 `drivers/EldenWifi/portable/upstream/source.json`。
下一步：移植完整 portable CE/HTC/WMI/HTT 功能链，接在已核本机原厂固件初始化之后；先真实扫描/BSS，再关联、iPadOS17服务与流量。
