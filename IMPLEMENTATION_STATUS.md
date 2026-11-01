# 计划逐项落地与证据

日期：2026-11-01。最终离线测试：32 项通过（24.036 秒）；交付模块强化复核 5 项通过（13.490 秒）；所有 PowerShell 脚本通过语法和 ASCII 检查。这里区分软件实现、离线运行证据和独立实机质量验收。测试结果原件在 `.studio/test_results.txt`；软件验收不等于电影画质已达标。

| 计划项 | 当前实现 | 证据 |
|---|---|---|
| P0 公共配置、旧 CLI | studio_core / studio_cli；BOM、相对/绝对路径、CLI 覆盖；当前图像节点配方 | 配置/路径/旧入口离线测试 |
| P0 服务统一、UTF-8、进程身份 | 隐藏后台启动、关闭继承句柄、PID+启动时间+可执行文件核对；共享服务不接管 | Windows HTTP 桩服务启动/复用/停止、篡改身份和共享状态保护测试 |
| P0 正确成功判定 | 产物存在、解码、尺寸/帧率/帧数/音频规格；内容哈希；WAV 失败算失败 | HTTP 集成测试、空输出/转换失败/篡改产物测试 |
| P0 配方与恢复 | base/turbo 分离；节点 schema/连接校验；不确定提交先核对；失败保留历史 | graph 类型检查、HTTP 响应丢失后无重复提交、已知 ID 恢复测试 |
| P0 下载与模型完整性 | Range 精确检查、布局绑定来源、断点恢复、字节数及 SHA256；不终止全局进程 | 本地 HTTP Range/忽略 Range/哈希失败测试；10/10 现有权重 SHA256 重新核验通过 |
| P0 版本与许可 | Git、固定工具依赖；推理环境清单、ComfyUI 提交、插件源码 ZIP/哈希；版本化许可证证据 | workflows/environment.lock.json、.studio/source_archives、licenses/manifest.json |
| P1 项目接口 | 三个 JSON Schema；项目→场景→镜头；每镜声明的参考资产内容哈希 | examples/minimal 检查；项目 dry-run；schemas |
| P1 take、恢复和审阅 | SQLite、实际提交图、选用状态、独立 take、串行任务、重跑/继续；历史只读登记 | 版本/选用保留、进程锁、HTTP 协议集成测试；studio tasks/review/scan |
| P1 审片 | 联络表、视频首帧缩略图、代理；选用 take 固定到时间线 | contact-sheet / proxies 入口；历史产物不会自动通过 |
| P2 图像控制 | 独立文生图/参考编辑/遮罩合成；裁切/补边预览 | reference/mask 图结构和补边像素测试；缺失 REF2VA 明确列出 |
| P2 镜头控制 | 首尾帧、时点引导、图/视频/声音参考、同镜尾帧续接；ControlNet 已预处理输入接口 | guided/reference 图测试；capabilities 静态扫描；对应权重未装则阻止实际生成 |
| P2 原生声音 | 音频 VAE 解码接入视频，同时保留独立 FLAC/WAV | 双输出图测试；没有音频 VAE 时明确报告，不标为已可用 |
| P2 音频后期 | 静音、裁切、淡化、峰值/响度、48kHz float 工作副本、循环试听与区间 | 合成音频解码/格式/时长测试；loop 标志不冒充无缝 |
| P2 对白扩展 | 本地音频导入 dialogue 轨；TTS/口型接口契约显式 disabled | extensions.json；没有模型时不虚报能力 |
| P3 剪辑/混音 | 帧级硬切、黑场、淡化、字幕、色彩解释、调色参数、四音轨与混音 | 合成片实际输出；视频帧数、红色画面、黑场、声音延迟样本和字幕流断言 |
| P3 交换与交付 | OTIO、基础视频 EDL、SRT、ProRes 母版、H.264 审片、float WAV 分轨、交付/归档清单 | OTIO 官方库读取回环；媒体 ffprobe/完整解码；out/offline_demo/delivery；发布前验证、失败保留上一完整交付 |
| P3 长片结构 | 画面和声音场景级缓存、哈希校验、独立场景版本、总片组合、缺失媒体检测 | 改场景 A 后 B 的画面和声音缓存可复用；完整重渲染复用全部场景 |

## 可直接复查

```powershell
python -m unittest discover -s tests -v
python scripts/studio.py check --project examples/minimal
python scripts/studio.py capabilities --destination .studio/capabilities.json
python scripts/create_demo.py
python scripts/studio.py render --project .studio/offline_demo --dry-run
```

离线示例是 6 秒、24fps、三个场景的测试色块与音调，不是模型生成质量样片。完整交付包含 12 个文件；重复渲染已核对三个场景的画面和四条声音缓存均被复用。

## 按用户确认暂缓的独立验收

用户已确认“保持暂缓实测，当前按软件实现验收”。本轮完成范围是 P0–P3 软件实现与离线验证；实机质量验收另行开展。

真实 ComfyUI/GPU 推理、base/turbo 画质对照、固定角色多景别连续性、动作/运镜服从性、60–90 秒剧情短片人工审片、目标剪辑软件导入和长片规模实测尚未执行，门槛与记录方式在 ACCEPTANCE.md。

这不是缺失功能的替代证明：缺失的音频 VAE、REF2VA、ControlNet、Turbo 权重明确报告；TTS/口型按计划仅预留接口。没有下载这些模型，也未将相关能力标记为 GPU 已验收。历史权重的许可证 revision 对应关系未被 SHA256 清单证明，商业授权记录为空。
