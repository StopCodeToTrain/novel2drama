# novel2drama - 小说转广播剧系统

将中文小说自动转换为多角色广播剧，支持 LLM 剧本分析、角色音色分配、TTS 语音合成和音频混音。

## 功能特性

- **自动剧本生成**：LLM 分析小说文本，提取角色、解析对话、标注情感，生成结构化广播剧剧本
- **多角色声音设计**：按性别/年龄段自动分配音色，支持旁白与对话分离
- **双 TTS 引擎**：Edge-TTS 在线引擎（开箱即用）和 CosyVoice2 本地声音克隆（可选）
- **多 LLM 后端**：LM Studio SDK / OpenAI 兼容 API / Ollama / llama-cpp-python 本地推理
- **缓存机制**：TTS 逐句缓存，中断后可断点续传
- **完整 GUI**：PyQt6 深色桌面应用，实时进度、剧本树预览、音频试听
- **CLI 支持**：命令行接口，适合脚本和批处理

## 流程架构

```
小说 TXT
  │
  ├── Stage 1: 文本分析与剧本化
  │     ├── 章节分割（正则匹配）
  │     ├── 角色提取（LLM）
  │     ├── 对话解析（LLM）
  │     └── 情感标注（规则 + LLM）
  │
  ├── Stage 2: 角色声音分配
  │     └── 按角色属性分配预设音色
  │
  ├── Stage 3: 逐句语音合成
  │     ├── Edge-TTS（在线）/ CosyVoice2（本地声音克隆）
  │     └── 逐句缓存，支持断点续传
  │
  └── Stage 5: 混音与导出
        ├── 句间/场景间停顿
        ├── 淡入淡出
        └── 输出 WAV 完整广播剧
```

> Stage 4（AI 音效/BGM 生成）为 Phase 2 规划，当前占位。

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.12+；CosyVoice2 本地 TTS 需 Python 3.10）
- [LM Studio](https://lmstudio.ai/)（推荐）或其他 LLM 后端
- [FFmpeg](https://ffmpeg.org/)（用于音频格式转换）

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/StopCodeToTrain/novel2drama.git
cd novel2drama

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 FFmpeg（Windows）
winget install ffmpeg

# 4. （可选）安装 CosyVoice2 本地 TTS
# git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
# cd CosyVoice && pip install -e .
# 下载模型到 models/CosyVoice2-0.5B/
```

### 配置 LLM 后端

**方式一：LM Studio（推荐）**

1. 下载安装 [LM Studio](https://lmstudio.ai/)
2. 加载 GGUF 模型（如 Qwen3-4B / Qwen2.5-7B）
3. 启动 Local Server（默认 `http://127.0.0.1:1234`）
4. 运行 `python gui.py`，在设置中选择 `lmstudio` 后端

**方式二：OpenAI 兼容 API**

在 GUI 设置中选择 `api`，填入 API 地址和模型名。

**方式三：Ollama**

```bash
ollama pull qwen3:4b
python gui.py
# 在设置中选择 `ollama` 后端
```

**方式四：本地 GGUF（CPU 推理，较慢）**

将 `.gguf` 模型文件放入 `models/` 目录，在设置中选择 `local` 后端。

### 使用

**GUI 模式**

```bash
python gui.py
```

1. 选择小说 `.txt` 文件
2. 点击「生成全部」或分步执行「分析剧本」→「语音合成」
3. 右侧可预览剧本树，双击试听音频片段

**CLI 模式**

```bash
# 完整生成
python main.py generate -i data/天可汗.txt

# 仅分析
python main.py analyze -i data/天可汗.txt

# 仅合成（需要已有剧本）
python main.py synthesize -s output/天可汗_script.json

# 启动 GUI
python main.py gui
```

## 项目结构

```
novel2drama/
├── gui.py                     # PyQt6 GUI 主程序
├── main.py                    # CLI 命令行入口
├── pipeline.py                # 端到端流水线编排
├── config.py                  # 全局配置
├── requirements.txt           # Python 依赖
│
├── text_analysis/             # Stage 1: 文本分析
│   ├── llm_client.py          #   多后端 LLM 客户端
│   ├── script_generator.py    #   剧本生成编排
│   ├── chapter_splitter.py    #   章节分割
│   ├── character_extractor.py #   角色提取
│   ├── dialogue_parser.py     #   对话解析
│   └── emotion_tagger.py      #   情感标注
│
├── voice_design/              # Stage 2: 声音设计
│   └── voice_assigner.py      #   角色音色分配
│
├── tts_engine/                # Stage 3: TTS 引擎
│   ├── tts_base.py            #   TTS 抽象基类
│   ├── edge_tts_backend.py    #   Edge-TTS 在线后端
│   └── cosyvoice_backend.py   #   CosyVoice2 本地后端
│
├── audio_generation/          # Stage 4: 音效生成（Phase 2）
│   ├── sfx_generator.py       #   音效生成器（占位）
│   └── bgm_generator.py       #   BGM 生成器（占位）
│
├── mixer/                     # Stage 5: 混音导出
│   ├── audio_mixer.py         #   音频混音拼接
│   └── exporter.py            #   导出工具
│
├── utils/                     # 工具模块
│   ├── text_utils.py          #   文本读写/清洗
│   ├── audio_utils.py         #   音频处理
│   └── cache.py               #   JSON 缓存
│
├── data/                      # 输入小说文本
├── models/                    # LLM/TTS 模型文件
├── output/                    # 输出剧本和音频
└── .cache/                    # TTS 缓存
```

## 支持的模型

| 模型 | 参数量 | 推荐用途 |
|------|--------|----------|
| Qwen3-4B | 4B | 轻量高效，中文理解好 |
| Qwen2.5-7B-Instruct | 7B | 更高质量，需更多显存 |

## Roadmap

- [ ] Stage 4: AI 音效 & BGM 生成（Stable Audio Open）
- [ ] 多角色并行合成，大幅提速
- [ ] Web UI 替代桌面 GUI
- [ ] 更多 TTS 引擎支持（ChatTTS, GPT-SoVITS）
- [ ] 视频输出（字幕 + 音频 + 插画）

## License

MIT License
