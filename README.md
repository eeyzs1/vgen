> 2026-11-01 工程更新：P0–P3 已补齐到本地生成控制、任务管理、音频后处理和场景级剪辑交付。当前操作入口见 [STUDIO_OPERATIONS.md](STUDIO_OPERATIONS.md)，逐项证据见 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)。下文为历史测量和用法记录；新的图像节点与视频配方尚未进行 GPU 质量回归。

# IAOD 生成工坊 —— ComfyUI + MiniMax 本地插画/音乐/音效生产线（视频线待激活）

> **写给谁：** 需要批量生成美术插画、音乐或音效的**项目 AI 或人类**。本文自包含：照着做就能出图/出曲/出音效，无需其他上下文。
> **维护历史：** 2026-10-03 建成插画管线（全验收）；同日增补 Music 3 音乐管线与 MOSS-SoundEffect-v2 音效管线（验收样 `out\music_0\`、`out\sfx_0\`）；2026-10-04 视频线完成预备（§3.6，按主创指令暂缓下载与生成）。

---

## 0. 一句话能力

本地 RTX 5090 Laptop 24GB 上运行的**三管线**：

- **插画**：MiniMax-H3 文生图，横版 3:2，**14 秒/张**（50 步）
- **音乐**：MiniMax Music 3 文生曲（器乐/歌曲皆可），**~55 秒/首**（60s 曲、30 步），FLAC 自动转 WAV
- **音效**：MOSS-SoundEffect-v2.0 文生音效（Apache-2.0），48kHz 单声道 0.1-30s，**~85 秒/条**（100 步；固定按 30s 去噪再裁切，短音效不省时），FLAC 自动转 WAV

## 1. 环境事实（勿改动的部分）

| 项 | 值 |
|---|---|
| GPU | RTX 5090 Laptop 24GB（Blackwell sm_120） |
| ComfyUI | v0.38.0，源码 `E:\workflow\ComfyUI`，独立 venv 在其 `.venv\`（Python 3.12.9 + torch 2.13.0+cu130） |
| 模型挂载 | `E:\workflow\ComfyUI\extra_model_paths.yaml` → 指向本目录 `models\`（改模型只动 `G:\vgen\models\`） |
| H3 插件 | `E:\workflow\ComfyUI\custom_nodes\ComfyUI-MiniMax-H3-Image-Studio`（节点 `H3StudioModels / H3StudioGenerate / H3StudioRender`） |
| 输出目录 | `G:\vgen\out\<批次名>\`（服务启动参数 `--output-directory` 已固定） |
| Shell | Windows PowerShell 5.1 —— **脚本文件只准 ASCII**（无 BOM 的 UTF-8 中文注释会按 GBK 误读炸语法） |

## 2. 模型清单（合计 ~64GB，sha256 已验证，基准在 `models\SHA256SUMS`）

| 文件 | 体积 | 管线 |
|---|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 21.0GB | 插画 |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15.7GB | 插画 |
| `minimax_h3_video_vae_int8_convrot.safetensors` | 2.8GB | 插画 |
| `minimax_music3_dit_fp16.safetensors` | 4.9GB | 音乐 |
| `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` | 9.2GB | 音乐 |
| `minimax_music3_dav.safetensors` | 0.2GB | 音乐 |
| `moss-sfx/MOSS-SoundEffect-v2.0/`（DiT+TE+VAE 全套） | 10.4GB | 音效 |

版权更正（2026-11-01）：H3 与 Music3 使用各自社区许可证，不能视为 Apache-2.0 或无条件商用；MOSS 单独核对 Apache-2.0。以对应版本原始许可证和授权记录为准，详见 STUDIO_OPERATIONS.md。

## 3. 怎么生成（消费方入口）

### 3.1 IAOD 事件插画（带 IAOD 风格锚）

```powershell
# 前提：为每个事件写一个场景描述文件 G:\vgen\prompts\<event_id>.txt（英文，一段场景词即可）
G:\vgen\scripts\gen.ps1 -Events dog_alert,false_beacon -Variants 3 -Batch batch_1
```

- `gen.ps1` 自动：**检测/启动** ComfyUI（等待就绪）→ 逐张生成 → 落盘 `out\<Batch>\<event>_s<k>.png`
- prompt 自动拼装：`_style_anchor.txt` + `<event_id>.txt` + `. Strictly avoid: ` + `_negative.txt`（风格锚由代码强制统一，**不要**把锚词写进事件文件）
- 首张含模型加载约 1-2 分钟，之后 14 秒/张

### 3.2 任意项目 / 任意风格（一次性 prompt）

```powershell
& E:\workflow\ComfyUI\.venv\Scripts\python.exe G:\vgen\scripts\run_batch.py `
    --prompt '你的完整英文prompt，自带风格词（不会注入IAOD锚）' `
    --name my_asset --variants 3 --steps 50 --batch proj_x --width 1216 --height 832
```

- `--name`：输出文件名前缀（`out\<batch>\<name>_s1..s<k>.png`）
- 宽高可改（32 的倍数），步数可降（`--steps 20` 快测）
- 种子规则：`--base-seed N` → 实际 seed = N+1..N+k；同 seed 同图

### 3.3 参数基线（插画，已验收，勿轻动）

| 参数 | 值 | 说明 |
|---|---|---|
| sampler/scheduler | `er_sde` / `simple` | 插件/Fizgig 官方静帧配方 |
| steps | 50 | 无 LoRA 基线；快测可 20 |
| 分辨率 | 1216×832 | 3:2 横版；构图重心提示词里写 `main subject placed center-left` |
| 首次验收数据 | 21.7s 冷启 / 14.4s 连续 / 0 重载 | `workflows\P0_batch0_params.json` 有完整存档 |

**H3 无负 prompt 槽**（flow-matching 架构）：规避词以 `Strictly avoid: ...` 尾句并入正向 prompt。若成品出现文字/水印/赛博紫泄漏，改写 `_negative.txt` 措辞或加强场景词，不要堆砌否定词。

### 3.4 音乐生成（MiniMax Music 3）

```powershell
# 前提：ComfyUI 服务在跑（gen.ps1 会自动拉起；音乐直接用 run_music.py）
& E:\workflow\ComfyUI\.venv\Scripts\python.exe G:\vgen\scripts\run_music.py `
    --caption 'instrumental ambient, sparse low-saturation strings, dusty wind textures, slow tempo' `
    --name explore_theme --duration 60 --batch music_1 --variants 3 --free-gpu
```

- **caption** = 风格标签串（乐器、情绪、节奏、质感）；**lyrics** 留空 = 纯器乐，填词（支持 `[Verse]/[Chorus]` 段落标记）= 歌曲有人声
- **duration 是上限不是定值**：模型会在乐句自然处收束（验收例：请求 60s 实出 31.7s）
- **时长经验（2026-10-04 实测，重要）**：
  - 纯器乐（lyrics 空）无论 duration 给多大（实测 240s）都只出 **20~55s**——模型行为，不是参数问题
  - **拉长钥匙 = lyrics 哼唱结构**：caption 带 `wordless vocalise humming` + lyrics 填 `[Verse] mm...[Chorus] ooh...` 无实义音节 → 实出 **78~168s**（music_2 批次全验）；`--duration 180~200` 配合
  - Music 3 **不适合做 UI 音效**：caption 写 `no music, one hit` 也出连续音乐（波形实测 54%~81% 窗口活跃）——离散短音效走程序合成或专门 SFX 模型
- 输出：`out\<batch>\<name>_s<k>.flac` + **自动转换的 .wav**（44.1kHz PCM16，UE 可直接导入）
- 参数基线（官方蓝图复刻）：KSampler 30 步 / cfg 1.7 / euler+simple / 负条件用 ConditioningZeroOut；首曲约 2 分钟（含模型加载），后续 ~55s/首
- IAOD 曲目方向参考 `G:\IAOD\briefs\07_AUDIO.md`：探索=低饱和弦乐+风尘、母港=钢琴碎片+远港广播、抬宝=低鼓变奏；**忌史诗铜管/射击 BGM**
- 无缝循环：AI 生成曲首尾不保证无缝，入 UE 后用淡入淡出或剪辑点处理；要严格无缝循环请在 DAW 后期

### 3.5 音效生成（MOSS-SoundEffect-v2.0，2026-10-04 增补）

```powershell
# 前提：ComfyUI 服务在跑（gen.ps1 会自动拉起）
& E:\workflow\ComfyUI\.venv\Scripts\python.exe G:\vgen\scripts\run_sfx.py `
    --prompt 'a light crisp wooden tap on a board game grid, single knuckle knock on polished hardwood, close microphone, dry and subtle' `
    --name grid_tap --seconds 2 --variants 3 --batch sfx_1 --base-seed 4000
```

- **prompt 要物理化、具体化**：写材质+动作+环境+距离感（"heavy wooden door slamming shut in a stone corridor, deep resonant thud" 远好于 "door sound"）；时序词有效（"engine struggles, then catches, then rumbles"）
- **seconds 只是裁切长度**：模型固定按 30s 去噪再裁（2s 和 30s 耗时相同，~85s/条 @100 步）；首条含 DiT 编译约 2.5 分钟，且**失败重试前先确认 worker 进程已死**（图报错时 Unload 节点不执行，worker 变僵尸——重启服务即可清理）
- 默认负向 `music, speech, vocals, singing`（防止漂成音乐/人声）
- 输出：`out\<batch>\<name>_s<k>.flac` + **自动转 .wav**（48kHz PCM16 单声道，UE 直接可用）
- **显存自动管理**：图内置 Unload 节点，跑完即杀 worker 还 ~11GB——批量结束无需额外操作；参数：bfloat16 / vram auto
- IAOD 音效需求对照 `G:\IAOD\briefs\07_AUDIO.md` §3-4（走格叩击/揭雾气流/失谐短音/耳鸣床）；验收样在 `out\sfx_0\`
- 架构注记：节点推理跑在 `custom_nodes\comfyui-moss-soundeffect-v2\.venv\`（独立环境，torch 2.13.0+cu130 本地轮复用 + triton-windows 3.8）；**必须** `start_comfy.ps1` 启动（其 UTF-8 环境变量是 worker 存活的前提，手动裸启服务会导致 GBK 编码死锁）

### 3.6 视频生成（MiniMax H3 I2V，**预备完成、待激活**）

> 2026-10-04 状态：按主创指令**暂缓**——未下载增效件、未跑生成。核心三件（DiT/编码器/视频 VAE）本就在盘，激活只需一条命令。

```powershell
# ① 激活（下载 2.5GB 增效件：音频 VAE 0.6GB + 8 步 turbo LoRA 2.0GB；哈希与字节数已写入脚本并自动登记进 SHA256SUMS）
G:\vgen\scripts\seq_dl_video.ps1
# ② 生成（首帧建议用 approved 插画；脚本已写好但未实测，首跑可能需按蓝图微调接线）
& E:\workflow\ComfyUI\.venv\Scripts\python.exe G:\vgen\scripts\run_video.py `
    --image out\batch_0\dog_alert_s1.png --prompt 'the dog stares at the rubble slope, dust drifting, tense stillness' `
    --name dog_alert_motion --frames 124 --batch video_0 --seed 101
```

- **单镜规格**：1344×768 @24fps，帧数 17k+5 网格，训练区间 124-362 帧 = **5.2~15.1 秒**（更长未测试）；8 步 turbo 配方（无 LoRA 则 ~50 步）
- **自带同步音轨**：激活音频 VAE 后 H3 生成带现场声的视频（风声/脚步）；当前脚本先出无声片，音频解码接线按官方蓝图 `E:\workflow\ComfyUI\blueprints\Image to Video (MiniMax H3).json` 补
- **长视频**：本地当前工作流未验证分钟级单条；标准做法 = 分段 + 尾帧续接（上镜尾帧 = 下镜首帧），角色一致性后续可上 REF2VA（盘外 21GB）或 OmniChar（.char 跨模型复用）
- **质量定位**（[品玩同题横评](https://www.pingwest.com/a/316102)）：H3 与 Seedance 2.5 **同一梯队、性格互补**——H3 强在成片质感/空间稳定/角色一致/音画同步（错法是"少做"），Seedance 强在精密运镜执行/原生 30s（错法是"做错"，如货船落水泥地）。游戏素材场景（微动效/氛围镜）恰好吃 H3 的强项。注意我们跑 int8 量化，较 API 满血有小折损
- **导演工作流路线图**（已规划，见 `workflows\Video_pipeline_plan.json`）：Phase 1 单镜验收 → Phase 2 `director.py`（分镜表 shots.json → 关键帧/镜头/BGM/音效三管线自动调度 + ffmpeg 合成，目标 60-90s 短片）→ Phase 3 一致性套件。同类先例：[aeon-radio-drama](https://github.com/AEON-7/aeon-radio-drama)（音频版全流程，同配置 5090 机器）
- `run_video.py` **未实测**（写自官方蓝图，标注于脚本头）；首次激活预期需小修


## 4. GPU 释放（用完必做）

```powershell
# 方式A：批量结束就释放（模型卸载、清 VRAM，服务保留）
... run_batch.py ... --free-gpu        # 或 gen.ps1 -FreeGpu

# 方式B：彻底停服（服务进程结束，GPU 全空）
G:\vgen\scripts\stop_server.ps1         # 结束进程并回报 nvidia-smi
```

验证：`nvidia-smi` 中 python 进程消失、显存占用回到基线（本机桌面基线约 1.3GB）。

## 5. 目录总览

```
G:\vgen\
  models\            十份权重（插画3 + 音乐3 + 音效4，~64GB）+ SHA256SUMS（含视频线待下载件的预登记哈希）
  prompts\           _style_anchor.txt / _negative.txt / <event_id>.txt 场景词
  workflows\         参数与规划存档（P0_batch0_params / Music3_params / MOSS_SFX_params / Video_pipeline_plan.json）
  out\<批次>\        生成输出；已验收样：acceptance、batch_0（图）、music_0（曲）、sfx_0（音效）
  approved\          ★ IAOD 交付区：主创筛过的成品，文件名 = 事件 id
  scripts\           gen.ps1 / run_batch.py / run_music.py / run_sfx.py / run_video.py(待实测)
                      seq_dl_video.ps1(视频激活) / start_comfy.ps1 / stop_server.ps1
                      pd.ps1（分块下载器）/ verify_models.ps1 / seq_dl*.ps1
  downloads\         轮子缓存（torch cu130 / triton-windows——重建 venv 时免下载，勿清）  logs\  服务日志与 pid
```

## 6. 故障排查

| 症状 | 处置 |
|---|---|
| `gen.ps1` 报服务 120s 未就绪 | 看 `G:\vgen\logs\comfy.err.log`；常见为端口占用（`netstat -ano | findstr 8188`，杀旧进程后重跑 gen.ps1） |
| 队列报模型文件校验失败 | 确认 `models\` 三文件未被移动；损坏重下：ModelScope `Comfy-Org/minimax-H3` → 用 `scripts\pd.ps1` 分块下 → `scripts\verify_models.ps1` 验哈希 |
| 生成变慢/显存涨 | 上批未释放：`run_batch.py --prompt x --name x` 不必要——直接 POST `http://127.0.0.1:8188/free` body `{"unload_models":true,"free_memory":true}`，或重启服务 |
| 要换风格/换项目 | 只动 `prompts\_style_anchor.txt`（或用 §3.2 一次性模式自带风格），模型与参数不用动 |
| MOSS 音效图报错后重试仍同错 | 旧 worker 僵尸（报错时 Unload 不执行）：重启服务（stop_server.ps1 → start_comfy.ps1）清掉再跑 |
| 音效节点 venv 损坏需重建 | `python -m venv .venv` 后装 `downloads\wheels\` 里的 torch cu130 + triton-windows 本地轮，再按 `custom_nodes\comfyui-moss-soundeffect-v2\requirements-runtime.txt` 装（tuna）；参照 `workflows\MOSS_SFX_params.json` 注记 |
| 下载大文件 | `scripts\pd.ps1 -Url <直链> -Dest <目标> -Expected <字节数> -N 6`；自带断点续传与分块校验；**先查 `SHA256SUMS` 类基准** |

## 7. 网络路线备忘（本机实测 2026-10）

- GitHub：SSH 可用（用户 eeyzs1）；HTTPS 走 `https://gh-proxy.com/https://github.com/...`（tarball 直下比 clone 稳）
- HuggingFace：`hf-mirror.com` 仅元数据快，**大文件会 302 到美国 xet 桥（1.8MB/s 慢）**
- 大模型权重首选 **ModelScope**（快时 19MB/s；傍晚偶有新连接慢启动，等 2-3 分钟或重启分块）
- PyPI：tuna 主 + 腾讯补缺（`mirrors.cloud.tencent.com/pypi/simple`）+ 官方兜底；torch 轮在 `download.pytorch.org/whl/cu130`（6 路分块 ~2MB/s）
- aliyun pytorch-wheels 有每日限速，勿依赖

## 8. IAOD 项目专属约定（其他项目可无视）

- 事件 id 与情境文本：`G:\IAOD\ue\IAOD\Content\Script\00_event_data.lua` 的 `text` 字段是画面素材
- 成品唯一交付物：`approved\<event_id>.png`（3:2、无文字、无负面清单元素）；IAOD 侧有现成入库管线
- 分批优先级与全部 46 个事件 id 清单：见 `G:\vgen\GEN_STUDIO_DEPLOY.md` §4.1
