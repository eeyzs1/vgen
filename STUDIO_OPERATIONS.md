# vgen 本地工坊操作手册

2026-11-01。P0–P3 的代码路径和离线验收已落实。用户已确认本轮按软件实现验收、继续暂缓实测。没有下载生成模型、启动真实 ComfyUI 或执行 GPU 推理；测试启动的服务是独立 HTTP 桩。生成画质、角色一致性、动作执行、真实推理速度和目标剪辑软件兼容性仍属于独立实机验收，不作为本轮软件验证结果。

## 安装、配置与检查

在 Python 3.12 下安装独立工具依赖，不改 ComfyUI 环境：

```powershell
python -m pip install --target .studio/python_packages -r requirements-studio.txt
python scripts/studio.py check --project examples/minimal
python scripts/studio.py capabilities --destination .studio/capabilities.json
python scripts/studio.py snapshot
```

`requirements-studio.txt` 固定工具及传递依赖版本。FFmpeg/ffprobe 应在 PATH，或写入配置。默认客户端依赖从 `.studio/python_packages` 加载。ComfyUI 仍使用其独立 Python，不自动升级。

复制 `studio.example.json` 为 `studio.local.json` 后修改。优先级为默认值 < JSON < CLI。`--config` 或 `VGEN_CONFIG` 指定配置文件；默认位置在本仓库。相对配置路径和输入媒体路径以 root 为基准。项目内声明的媒体路径以项目目录为基准。服务端 output 必须与客户端 output 一致。

```powershell
scripts/start_comfy.ps1 -Config studio.local.json
scripts/stop_server.ps1 -Config studio.local.json
scripts/gen.ps1 -Events dog_alert -Variants 3 -Config studio.local.json
```

这些命令会启动/停止真实服务，不属于离线检查。服务仅管理 localhost；响应正常的外部服务会保持共享状态，不取得其所有权。停止时核对 PID、启动时间、可执行文件和命令行。旧 logs/comfy.pid 不构成新所有权证明。后台启动关闭继承句柄，日志写入配置的 state。

`capabilities` 用源代码静态扫描及文件存在性列出缺失节点/权重；ready_for_live_validation 仅表示可以进入实机验证，不代表已经通过质量或推理验证。运行生成时还会查询实时 object_info，检查接口、连接和模型文件。

## 生成、修改和镜头控制

旧 CLI 参数和 IAOD 风格拼装保留，图像图已迁移到本机当前插件注册的节点；保留原来 50 步和 ER-SDE/simple 参数。这个迁移尚未进行 GPU 回归，不保证与历史图逐像素相同。

```powershell
python scripts/run_batch.py --events dog_alert --variants 3 --dry-run
python scripts/run_batch.py --prompt "complete project prompt" --name keyframe --variants 1 --dry-run
python scripts/run_batch.py --image-mode reference --source-image out/source.png --prompt "change the hat" --name edit --dry-run
python scripts/run_batch.py --image-mode mask --source-image out/source.png --mask out/mask.png --prompt "replace the hat" --name mask_edit --dry-run
python scripts/run_video.py --image out/batch_0/dog_alert_s1.png --last-image out/end.png --prompt "dust drifting" --name shot --recipe base --fit pad --dry-run
```

- `--dry-run` 不连接 ComfyUI，不提交生成；可能创建输入预览和项目清单。输出包含依赖清单，不代表缺失能力可用。
- 首尾帧先等比裁切（crop，默认）或补边（pad），预览保存在 `.studio/prepared`，不拉伸源图。
- 图像 reference/mask 使用 REF2VA 权重；缺失时明确报告，不回退为文生图。
- mask 是“参考编辑后遮罩合成”：白色区域采用新图，黑色区域保留已拟合源图，支持灰度羽化。它不是遮罩条件扩散；修改服从性待实测。遮罩和原始源图必须同尺寸。
- `--reference-image` 可重复添加，最多八张额外参考。reference/mask 模式与纯文生图明确分开。
- `--recipe base` 不加载 Turbo，默认 50 步；turbo 默认 8 步，按当前插件标注的 FL2VA 配方使用 euler/simple 和独立 sigma shift。FL2VA Turbo 禁止配合 REF2VA。
- `--audio` 解码原生声音，视频带声并另外保存 FLAC/WAV；未安装音频 VAE 时拒绝生成。
- `--continue-from previous.mp4` 使用上一视频尾帧，只用于同镜延长。新镜头使用独立首帧或参考资产。
- 视频帧数向上对齐 17k+5，限定 124–362 帧。1344×768 是生成默认值；最终 1080p 是后期输出规格。

多时间点、参考视频/声音及 ControlNet 使用 `--controls controls.json`。示例：

```json
{
  "audio": true,
  "guides": [{"frame": 68, "image": "out/middle.png"}],
  "references": [],
  "control": {"path": "out/depth.mp4", "model_patch": "minimax_h3_fun_controlnet_union_2.0_pruned_bf16.safetensors", "strength": 1.0}
}
```

`references` 元素为 `{kind: image|video|audio, path, include_audio?}`，最多 9 张图、3 段视频、3 段独立声音。REF2VA 镜头用 guides 定位关键帧，不同时传 first/last image。参考视频限制 5 帧至 15 秒，非 24fps 输入另存 24fps 副本。control.path 必须是预先计算好的 pose/depth/edge 控制视频，不自动把 RGB 视频当成深度。所有控制权重均单独检查，不自动下载。模板在 `workflows/templates`。

## 任务、恢复和审阅

```powershell
python scripts/studio.py tasks
python scripts/studio.py review --task TAKE_ID --status approved --select
python scripts/studio.py reconcile --task TAKE_ID
python scripts/studio.py report --destination .studio/job_report.json
python scripts/studio.py scan
python scripts/studio.py contact-sheet
python scripts/studio.py proxies
```

任务位于 `.studio/studio.sqlite`。每次生成使用独立 take；输出加 `_t<take前缀>`。数据库保留原始参数、工作流、实际提交图、模型哈希清单、环境、服务 ID、媒体规格、内容哈希、耗时和 GPU 采样峰值。显存指标为可见 GPU 总占用，包含其他应用，不冒充单模型独占占用。

相同输入及环境已完成时，重新执行会检查内容哈希和解码，再跳过。`--retry-failed` 重试明确失败的任务并保留历史；`--new-take` 主动创建新候选。响应丢失、连接中断或超时记为 unresolved；恢复先查询 queue/history，不盲目重复提交。旧 take 未核清时，改变输入也不会悄悄提交另一份。服务历史丢失后须核对实际队列再主动 new-take。

单 GPU 默认串行、按模型族调度；工坊进程锁拒绝同时提交。外部 ComfyUI 用户不受该锁约束。free-gpu 在 finally 中处理，但服务仍有排队/运行任务时推迟卸载。MOSS 错误不自动重启共享服务。

审阅状态为 pending/approved/rejected，只能选用已完成且通过的 take。同一镜头的选用版本会取消原选择，但 timeline 中固定的 take_id 不随重跑变化。历史 scan 不移动媒体、不自动通过；旧 approved 人工交付方式继续适用。

## 项目接口与时间线

接口规范位于 `schemas`；参考 `examples/minimal`。三个文件均为 schema_version=1。

- project.json：id、整数 fps（1–60）、width、height、color_space（bt709）、style、assets。默认交付为 24fps、1920×1080 SDR。
- assets：ID 到 `{path, kind, role, conditioning}` 的映射。role 可标注角色、服装、道具、场景、光线、风格、声线、动作、运镜；conditioning=false 仅参与追溯。
- shots.json：id、scene_id、mode、prompt、seed、steps、variants、target_duration、references。图像支持 image_mode/source_image/mask；视频支持 first_frame/last_frame/continue_from/controls/recipe。
- timeline.json：clips 指定 shot_id、显式 path 或固定 take_id、track、in_frame、out_frame、start_frame；out_frame 为不包含的末端。时间值使用项目帧率的整数帧。视频为单画面轨，声音可重叠，支持 dialogue/music/sfx/ambience。

```powershell
python scripts/studio.py generate --project PROJECT_DIR --shot SHOT_ID --dry-run
python scripts/studio.py continue --project PROJECT_DIR
python scripts/studio.py render --project PROJECT_DIR
```

项目提示词不注入 IAOD 锚。每个镜头仅跟踪其声明的参考资产哈希；修改未引用资产不会让其他镜头失效。单 GPU 串行执行，失败即停止。音频/视频实际生成长度与最终剪辑使用区间分开。

剪辑支持硬切、显式 fade_in/fade_out（帧数，淡至/淡出黑场）、间隙黑场、增益、字幕及分轨混音。v1 不接受画面重叠；需要叠化的项目应在外部剪辑器处理。scene_id 必须在画面时间线上形成连续块。声音跨场景时保持原有包络和采样级位置，不重复淡入。

输入色彩用 clip.input_color_space 显式指定 srgb/bt709；默认静帧 srgb、视频 bt709。输出统一 bt709 SDR。grade 支持 brightness/contrast/saturation。提高位深或放大不被记为恢复生成细节。

输出在 `out/PROJECT_ID/delivery`：ProRes 422 HQ 母版 master.mov、H.264/AAC review.mp4、四条 48kHz float WAV 分轨、规范化 mix.wav、SRT 字幕、timeline.otio、基础视频 EDL、delivery.json 和 archive.json。OTIO 保留剪辑区间及效果/增益元数据；EDL 仅承载画面硬切。OTIO 读写回环已测，目标剪辑器对效果和字体的导入需另验。

画面和声音都按场景缓存，缓存记录哈希并重新核查。只修改一个场景时复用其他场景中间件；最终总片和混音重新组合。archive.json 记录交付文件、源媒体和哈希，不代替源媒体备份。

新交付先写入项目下 .delivery-staging-*，全部验证通过后才替换 delivery；旧交付保存在 delivery_history。失败时保留暂存目录供检查，上一份完整交付不受影响。禁止把将被替换的 delivery 内文件作为源素材；应引用独立 take 或历史版本。固定 take_id 与显式 path 同时给出时必须匹配内容哈希。字幕不能超出总时间线。

## 音频后处理与对白

```powershell
python scripts/studio.py audio --source out/source.flac --destination out/edited.wav --options examples/audio_options.json
```

支持静音检测、起止裁切、首尾静音修剪、淡入淡出、峰值与响度分析、可选响度规范化。原始文件保留，影视工作副本为 48kHz float WAV；原 runner 的游戏导出仍为 PCM16。loop 生成三遍试听和样本区间，seamless_verified 默认为 false，不能自动宣称无缝。

对白先以音频文件进入 dialogue 轨。`workflows/extensions.json` 保留本地 TTS/声线和口型的输入输出契约，当前 disabled，不伪造已安装模型。

## 环境、许可证和验证

`snapshot` 保存实际推理 Python 的版本、pip freeze、ComfyUI 提交和补丁、插件源码哈希及 ZIP。没有独立 Git 的插件记录 unversioned，不能借用父仓库提交号。可对照 `workflows/environment.lock.json` 重建；备份 `.studio/source_archives` 和模型权重，pip 的本地 CUDA 轮子继续保留在 downloads。快照操作不修改共享环境。

`licenses/manifest.json` 固定当前取得证据的仓库 revision、来源和哈希；H3/Music3 保存许可证原文，MOSS 保存模型卡中的 Apache-2.0 声明（上游模型仓库没有独立 LICENSE 文件）。历史权重只有 SHA256，不能据此证明与本次许可证 revision 完全对应；当前没有商业授权记录。

显式验证模型：`scripts/verify_models.ps1`。显式激活视频依赖：`scripts/seq_dl_video.ps1`。它们不由生成命令自动调用；下载器检查 HTTP Range、字节数和可选 SHA256，不结束任何外部下载进程。

离线测试：`python -m unittest discover -s tests -v`。可复现的 CPU 示例：`python scripts/create_demo.py`；交付在 `out/offline_demo/delivery`。真实质量验收顺序和记录要求见 ACCEPTANCE.md。没有通过实机验收的能力始终保留 gpu_validated=false。
