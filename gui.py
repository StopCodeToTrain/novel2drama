#!/usr/bin/env python
"""novel2drama GUI -- PyQt6 小说转广播剧界面。

提供图形化界面完成以下流程：
  1. 打开小说文本文件
  2. 配置 LLM/TTS 参数
  3. 后台运行流水线（QThread，不阻塞 UI）
  4. 实时显示生成进度与日志
  5. 剧本树形浏览（章节 > 场景 > 台词行）
  6. 逐句音频预览（QMediaPlayer）
  7. 设置对话框（LLM 后端选择 / Ollama / API / 本地）
  8. TTS 语音测试对话框
"""

import os
os.environ["QT_LOGGING_RULES"] = "qt.text.font.db=false"

import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QComboBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QFileDialog,
    QPlainTextEdit, QProgressBar, QGroupBox, QLineEdit, QMessageBox,
    QSplitter, QSlider, QTabWidget, QDialog, QFormLayout, QTextEdit,
    QSpinBox, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer, QProcess
from PyQt6.QtGui import QFont, QColor, QDesktopServices
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import NovelToDramaPipeline
from config import (
    OUTPUT_DIR, TTSConfig, load_settings, save_settings,
    get_llm_config, DEFAULT_LLM_SETTINGS, RECOMMENDED_OLLAMA_MODELS,
    OLLAMA_DOWNLOAD_URL, MODELS_DIR,
)


# ═══════════════════════════════════════════════════════════════
#  QSS 深色主题样式表 (Catppuccin Mocha)
# ═══════════════════════════════════════════════════════════════

APP_QSS = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 10px;
    background-color: #181825;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #89b4fa;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #11111b;
}
QPushButton:disabled {
    background-color: #181825;
    color: #585b70;
    border-color: #313244;
}
QPushButton#btn_start {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}
QPushButton#btn_start:hover { background-color: #b4befe; }
QPushButton#btn_start:pressed { background-color: #74c7ec; }
QPushButton#btn_start:disabled {
    background-color: #313244;
    color: #585b70;
}
QPushButton#btn_cancel {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}
QPushButton#btn_cancel:hover { background-color: #eba0ac; }
QPushButton#btn_cancel:disabled {
    background-color: #313244;
    color: #585b70;
}
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px 10px;
    min-height: 20px;
}
QComboBox:hover { border-color: #585b70; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #cdd6f4;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    padding: 4px;
}
QTreeWidget {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    gridline-color: #313244;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}
QTreeWidget::item { padding: 4px 8px; }
QHeaderView::section {
    background-color: #313244;
    color: #a6adc8;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 6px;
    height: 22px;
    text-align: center;
    color: #cdd6f4;
    font-size: 12px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 6px;
}
QPlainTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 6px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}
QCheckBox {
    color: #cdd6f4;
    spacing: 6px;
    padding: 2px 0;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 2px solid #45475a;
    border-radius: 4px;
    background-color: #313244;
}
QCheckBox::indicator:hover { border-color: #89b4fa; }
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
    image: none;
}
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px 10px;
}
QLineEdit:focus { border-color: #89b4fa; }
QSlider::groove:horizontal {
    background: #313244;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: #b4befe; }
QSlider::sub-page:horizontal {
    background: #89b4fa;
    border-radius: 3px;
}
QScrollBar:vertical {
    background: #181825;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #181825;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #585b70; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QSplitter::handle { background-color: #313244; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }
QLabel { color: #cdd6f4; }
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}
QMessageBox { background-color: #1e1e2e; }
QMessageBox QLabel { color: #cdd6f4; }
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 6px;
    background-color: #181825;
}
QTabBar::tab {
    background-color: #313244;
    color: #a6adc8;
    padding: 6px 16px;
    border: 1px solid #45475a;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #181825;
    color: #89b4fa;
    font-weight: bold;
}
QTabBar::tab:hover:!selected { background-color: #45475a; }
"""

# 颜色常量
C_GREEN = QColor("#a6e3a1")
C_RED = QColor("#f38ba8")
C_GRAY = QColor("#a6adc8")
C_BLUE = QColor("#89b4fa")
C_YELLOW = QColor("#f9e2af")
C_PURPLE = QColor("#cba6f7")


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _subprocess_flags() -> int:
    """获取 subprocess 调用的 creationflags（Windows 下隐藏控制台窗口）"""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


# ═══════════════════════════════════════════════════════════════
#  后台工作线程
# ═══════════════════════════════════════════════════════════════

class PipelineWorker(QThread):
    """后台运行流水线的线程。"""

    # 信号
    progress = pyqtSignal(int, str, int, int, str)  # stage, stage_name, current, total, message
    log = pyqtSignal(str)
    script_ready = pyqtSignal(dict)
    segment_ready = pyqtSignal(str, str, dict)  # seg_key, audio_path, line
    finished_all = pyqtSignal(str)  # output_path
    error = pyqtSignal(str)

    def __init__(self, mode: str, input_path: str = "", script_path: str = "",
                 output_path: str = "", use_cache: bool = True,
                 llm_backend: str = "ollama", narrator_voice: str = "narrator_male"):
        """
        Args:
            mode: "generate" | "analyze" | "synthesize"
            input_path: 输入小说路径
            script_path: 剧本 JSON 路径
            output_path: 输出音频路径
            use_cache: 是否使用缓存
            llm_backend: LLM 后端（保留参数，实际后端由 settings.json 决定）
            narrator_voice: 旁白音色
        """
        super().__init__()
        self.mode = mode
        self.input_path = input_path
        self.script_path = script_path
        self.output_path = output_path
        self.use_cache = use_cache
        self.llm_backend = llm_backend  # 保留参数，但不再用于设置 LLMConfig.backend
        self.narrator_voice = narrator_voice
        self._cancel = False
        self._pipeline: Optional[NovelToDramaPipeline] = None

    def cancel(self):
        """请求取消"""
        self._cancel = True
        if self._pipeline:
            self._pipeline.cancel()

    def run(self):
        """执行流水线"""
        try:
            # LLMClient 自动从 settings.json 读取后端配置（get_llm_config()）
            # 不再设置 LLMConfig.backend
            self._pipeline = NovelToDramaPipeline(use_cache=self.use_cache)

            # 连接回调 -> 信号
            self._pipeline.on_progress = lambda stage, name, cur, tot, msg: self.progress.emit(stage, name, cur, tot, msg)
            self._pipeline.on_log = lambda msg: self.log.emit(msg)
            self._pipeline.on_script_ready = lambda script: self.script_ready.emit(script)
            self._pipeline.on_segment_ready = lambda key, path, line: self.segment_ready.emit(key, path, line)
            self._pipeline.on_finished = lambda path: self.finished_all.emit(path)
            self._pipeline.on_error = lambda err: self.error.emit(err)

            if self.mode == "generate":
                self._pipeline.run(
                    input_path=self.input_path,
                    output_path=self.output_path or None,
                    script_path=self.script_path or None,
                )
            elif self.mode == "analyze":
                self._pipeline.analyze_only(
                    input_path=self.input_path,
                    script_path=self.script_path or None,
                )
            elif self.mode == "synthesize":
                self._pipeline.synthesize_only(self.script_path)

        except Exception as e:
            self.error.emit(str(e))


class OllamaCheckWorker(QThread):
    """检查 Ollama 安装状态和已安装模型的线程。"""

    ollama_found = pyqtSignal(bool, list)  # (found, model_list)

    def run(self):
        """检查 ollama 命令是否存在并获取已安装模型列表"""
        try:
            ollama_path = shutil.which("ollama")
            if not ollama_path:
                self.ollama_found.emit(False, [])
                return

            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
                creationflags=_subprocess_flags(),
            )

            models = []
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split("\n")
                # 跳过表头行
                for line in lines[1:]:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if parts:
                        models.append(parts[0])

            self.ollama_found.emit(True, models)
        except Exception:
            self.ollama_found.emit(False, [])


class OllamaPullWorker(QThread):
    """拉取 Ollama 模型的线程。"""

    output = pyqtSignal(str)            # stdout/stderr 输出行
    pull_finished = pyqtSignal(bool)    # 拉取是否成功

    def __init__(self, model_name: str):
        super().__init__()
        self.model_name = model_name

    def run(self):
        """执行 ollama pull <model_name>"""
        try:
            process = subprocess.Popen(
                ["ollama", "pull", self.model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_subprocess_flags(),
            )

            if process.stdout:
                for line in process.stdout:
                    self.output.emit(line.rstrip())

            process.wait()
            self.pull_finished.emit(process.returncode == 0)
        except FileNotFoundError:
            self.output.emit("错误: 未找到 ollama 命令，请先安装 Ollama")
            self.pull_finished.emit(False)
        except Exception as e:
            self.output.emit(f"错误: {e}")
            self.pull_finished.emit(False)


class TtsTestWorker(QThread):
    """TTS 测试合成工作线程。"""

    synth_finished = pyqtSignal(str)   # 音频文件路径
    error = pyqtSignal(str)            # 错误信息
    log = pyqtSignal(str)              # 进度日志

    def __init__(self, text: str, reference_audio: Optional[str] = None,
                 reference_text: Optional[str] = None, emotion: Optional[str] = None,
                 speed: float = 1.0, tts_backend: str = "edge-tts",
                 voice: Optional[str] = None):
        super().__init__()
        self.text = text
        self.reference_audio = reference_audio
        self.reference_text = reference_text
        self.emotion = emotion
        self.speed = speed
        self.tts_backend = tts_backend
        self.voice = voice

    def run(self):
        """懒加载 TTS 后端并执行合成"""
        try:
            if self.tts_backend == "cosyvoice":
                self.log.emit("正在加载 CosyVoice2 引擎（首次加载可能较慢）...")
                from tts_engine.cosyvoice_backend import CosyVoiceBackend
                backend = CosyVoiceBackend()
                self.log.emit("TTS 引擎加载完成，开始合成...")
                audio_path = backend.synthesize(
                    text=self.text,
                    reference_audio=self.reference_audio or None,
                    reference_text=self.reference_text or None,
                    emotion=self.emotion,
                    speed=self.speed,
                )
            else:
                self.log.emit("使用 Edge-TTS 在线合成...")
                from tts_engine.edge_tts_backend import EdgeTTSBackend
                backend = EdgeTTSBackend()
                self.log.emit("开始合成...")
                audio_path = backend.synthesize(
                    text=self.text,
                    voice=self.voice,
                    emotion=self.emotion,
                    speed=self.speed,
                )
            self.log.emit("合成完成！")
            self.synth_finished.emit(audio_path)
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════════════════════════
#  设置对话框
# ═══════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """LLM 设置对话框 -- 配置后端、Ollama / API / 本地参数"""

    # 后端选项 -> settings 中的值
    _BACKEND_MAP = {0: "lmstudio", 1: "api", 2: "ollama", 3: "local"}
    _BACKEND_REVERSE = {"lmstudio": 0, "api": 1, "ollama": 2, "local": 3}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(620, 520)
        self._check_worker: Optional[OllamaCheckWorker] = None
        self._pull_worker: Optional[OllamaPullWorker] = None
        self._build_ui()
        self._load_settings()
        # 打开时检查 Ollama 安装状态
        self._check_ollama()

    # ── UI 构建 ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 后端选择 ──
        backend_layout = QHBoxLayout()
        backend_layout.addWidget(QLabel("LLM 后端:"))
        self.cmb_backend = QComboBox()
        self.cmb_backend.addItems([
            "LM Studio (本地推荐)",
            "API (云端/LM Studio HTTP)",
            "Ollama (本地)",
            "llama-cpp (本地GGUF)",
        ])
        self.cmb_backend.currentIndexChanged.connect(self._on_backend_changed)
        backend_layout.addWidget(self.cmb_backend, 1)
        layout.addLayout(backend_layout)

        # ── 标签页 ──
        self.tabs = QTabWidget()

        # ── Ollama 标签页 ──
        ollama_widget = QWidget()
        ollama_layout = QVBoxLayout(ollama_widget)
        ollama_layout.setSpacing(8)

        # Ollama 安装状态
        self.lbl_ollama_status = QLabel("正在检查 Ollama 安装状态...")
        ollama_layout.addWidget(self.lbl_ollama_status)

        # 下载按钮（未安装时显示）
        self.btn_download_ollama = QPushButton("下载 Ollama (打开浏览器)")
        self.btn_download_ollama.clicked.connect(self._on_download_ollama)
        self.btn_download_ollama.setVisible(False)
        ollama_layout.addWidget(self.btn_download_ollama)

        # Base URL
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("Base URL:"))
        self.le_ollama_url = QLineEdit("http://localhost:11434/v1")
        url_layout.addWidget(self.le_ollama_url, 1)
        ollama_layout.addLayout(url_layout)

        # 模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self.cmb_ollama_model = QComboBox()
        self.cmb_ollama_model.setEditable(True)
        for m in RECOMMENDED_OLLAMA_MODELS:
            label = f"{m['name']} - {m['description']}"
            self.cmb_ollama_model.addItem(label, m["name"])
        model_layout.addWidget(self.cmb_ollama_model, 1)
        ollama_layout.addLayout(model_layout)

        # 拉取 / 测试按钮
        btn_layout = QHBoxLayout()
        self.btn_pull_model = QPushButton("拉取模型")
        self.btn_pull_model.clicked.connect(self._on_pull_model)
        self.btn_test_ollama = QPushButton("测试连接")
        self.btn_test_ollama.clicked.connect(self._on_test_ollama)
        btn_layout.addWidget(self.btn_pull_model)
        btn_layout.addWidget(self.btn_test_ollama)
        btn_layout.addStretch()
        ollama_layout.addLayout(btn_layout)

        # 拉取输出区域
        self.txt_pull_output = QTextEdit()
        self.txt_pull_output.setReadOnly(True)
        self.txt_pull_output.setMaximumHeight(160)
        self.txt_pull_output.setPlaceholderText("模型拉取 / 连接测试的输出将显示在这里...")
        ollama_layout.addWidget(self.txt_pull_output)

        ollama_layout.addStretch()
        self.tabs.addTab(ollama_widget, "Ollama")

        # ── API 标签页 ──
        api_widget = QWidget()
        api_layout = QFormLayout(api_widget)
        self.le_api_url = QLineEdit("https://api.openai.com/v1")
        self.le_api_key = QLineEdit()
        self.le_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.le_api_key.setPlaceholderText("sk-...")
        self.le_api_model = QLineEdit("gpt-4o-mini")
        api_layout.addRow("Base URL:", self.le_api_url)
        api_layout.addRow("API Key:", self.le_api_key)
        api_layout.addRow("模型名:", self.le_api_model)
        self.tabs.addTab(api_widget, "API (云端)")

        # ── 本地标签页 ──
        local_widget = QWidget()
        local_layout = QVBoxLayout(local_widget)
        local_layout.setSpacing(8)

        # 模型文件路径
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("模型路径:"))
        self.le_local_model_path = QLineEdit()
        self.le_local_model_path.setPlaceholderText("选择 GGUF 模型文件")
        self.btn_browse_model = QPushButton("...")
        self.btn_browse_model.setFixedWidth(40)
        self.btn_browse_model.clicked.connect(self._on_browse_model)
        path_layout.addWidget(self.le_local_model_path, 1)
        path_layout.addWidget(self.btn_browse_model)
        local_layout.addLayout(path_layout)

        # 上下文长度
        ctx_layout = QHBoxLayout()
        ctx_layout.addWidget(QLabel("上下文长度:"))
        self.spin_ctx = QSpinBox()
        self.spin_ctx.setRange(1024, 131072)
        self.spin_ctx.setValue(8192)
        self.spin_ctx.setSingleStep(1024)
        ctx_layout.addWidget(self.spin_ctx)
        ctx_layout.addStretch()
        local_layout.addLayout(ctx_layout)

        # 安装说明
        note = QLabel(
            "注意: 需要先安装 llama-cpp-python\n"
            "pip install llama-cpp-python --extra-index-url "
            "https://abetlen.github.io/llama-cpp-python/whl/vulkan"
        )
        note.setStyleSheet("color: #f9e2af; padding: 8px;")
        note.setWordWrap(True)
        local_layout.addWidget(note)
        local_layout.addStretch()
        self.tabs.addTab(local_widget, "llama-cpp (本地GGUF)")

        layout.addWidget(self.tabs)

        # ── 保存按钮 ──
        btn_save_layout = QHBoxLayout()
        btn_save_layout.addStretch()
        self.btn_save = QPushButton("保存")
        self.btn_save.setObjectName("btn_start")
        self.btn_save.clicked.connect(self._on_save)
        btn_save_layout.addWidget(self.btn_save)
        layout.addLayout(btn_save_layout)

    # ── 加载 / 保存 ──

    def _load_settings(self):
        """加载当前设置到界面"""
        settings = get_llm_config()
        backend = settings.get("llm_backend", "ollama")
        self.cmb_backend.setCurrentIndex(self._BACKEND_REVERSE.get(backend, 0))

        self.le_ollama_url.setText(
            settings.get("ollama_base_url", "http://localhost:11434/v1")
        )
        ollama_model = settings.get("ollama_model", "qwen3:4b")
        idx = self.cmb_ollama_model.findData(ollama_model)
        if idx >= 0:
            self.cmb_ollama_model.setCurrentIndex(idx)
        else:
            self.cmb_ollama_model.setEditText(ollama_model)

        self.le_api_url.setText(
            settings.get("llm_api_base_url", "https://api.openai.com/v1")
        )
        self.le_api_key.setText(settings.get("llm_api_key", ""))
        self.le_api_model.setText(settings.get("llm_api_model", "gpt-4o-mini"))

        self.le_local_model_path.setText(settings.get("local_model_path", ""))
        self.spin_ctx.setValue(settings.get("local_n_ctx", 8192))

        self._on_backend_changed(self.cmb_backend.currentIndex())

    def _on_save(self):
        """保存设置并关闭对话框"""
        settings = load_settings()

        backend = self._BACKEND_MAP.get(self.cmb_backend.currentIndex(), "ollama")
        settings["llm_backend"] = backend

        settings["ollama_base_url"] = self.le_ollama_url.text().strip()
        ollama_model = self.cmb_ollama_model.currentData() or self.cmb_ollama_model.currentText()
        settings["ollama_model"] = ollama_model.split()[0] if ollama_model else "qwen3:4b"

        settings["llm_api_base_url"] = self.le_api_url.text().strip()
        settings["llm_api_key"] = self.le_api_key.text().strip()
        settings["llm_api_model"] = self.le_api_model.text().strip()

        settings["local_model_path"] = self.le_local_model_path.text().strip()
        settings["local_n_ctx"] = self.spin_ctx.value()

        save_settings(settings)
        self.accept()

    # ── 后端切换 ──

    def _on_backend_changed(self, idx: int):
        """后端切换时切换标签页"""
        if 0 <= idx < self.tabs.count():
            self.tabs.setCurrentIndex(idx)

    # ── Ollama 相关 ──

    def _check_ollama(self):
        """检查 Ollama 安装状态"""
        self._check_worker = OllamaCheckWorker()
        self._check_worker.ollama_found.connect(self._on_ollama_checked)
        self._check_worker.start()

    def _on_ollama_checked(self, found: bool, models: list):
        """Ollama 检查结果回调"""
        if found:
            self.lbl_ollama_status.setText(
                f"✓ Ollama 已安装（已安装 {len(models)} 个模型）"
            )
            self.lbl_ollama_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            self.btn_download_ollama.setVisible(False)

            # 将已安装的模型添加到下拉框
            if models:
                for m in models:
                    if self.cmb_ollama_model.findData(m) < 0:
                        self.cmb_ollama_model.addItem(f"{m} (已安装)", m)
        else:
            self.lbl_ollama_status.setText("✗ Ollama 未安装")
            self.lbl_ollama_status.setStyleSheet("color: #f38ba8; font-weight: bold;")
            self.btn_download_ollama.setVisible(True)

    def _on_download_ollama(self):
        """打开 Ollama 下载页面"""
        QDesktopServices.openUrl(QUrl(OLLAMA_DOWNLOAD_URL))

    def _on_pull_model(self):
        """拉取选中的 Ollama 模型"""
        model_name = self.cmb_ollama_model.currentData() or self.cmb_ollama_model.currentText()
        model_name = model_name.split()[0] if model_name else ""
        if not model_name:
            QMessageBox.warning(self, "提示", "请选择或输入模型名称")
            return

        self.txt_pull_output.clear()
        self.btn_pull_model.setEnabled(False)
        self.txt_pull_output.append(f"开始拉取模型: {model_name}\n")

        self._pull_worker = OllamaPullWorker(model_name)
        self._pull_worker.output.connect(self._on_pull_output)
        self._pull_worker.pull_finished.connect(self._on_pull_finished)
        self._pull_worker.start()

    def _on_pull_output(self, text: str):
        """拉取输出回调"""
        self.txt_pull_output.append(text)

    def _on_pull_finished(self, success: bool):
        """拉取完成回调"""
        self.btn_pull_model.setEnabled(True)
        if success:
            self.txt_pull_output.append("\n✓ 模型拉取成功！")
        else:
            self.txt_pull_output.append("\n✗ 模型拉取失败")
        # 重新检查已安装模型列表
        self._check_ollama()

    def _on_test_ollama(self):
        """测试 Ollama 连接"""
        model_name = self.cmb_ollama_model.currentData() or self.cmb_ollama_model.currentText()
        model_name = model_name.split()[0] if model_name else ""
        base_url = self.le_ollama_url.text().strip()

        if not model_name:
            QMessageBox.warning(self, "提示", "请选择或输入模型名称")
            return

        self.btn_test_ollama.setEnabled(False)
        self.txt_pull_output.append(f"\n正在测试连接 {model_name} @ {base_url} ...")

        try:
            from openai import OpenAI
            client = OpenAI(base_url=base_url, api_key="ollama")
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "你好"}],
                max_tokens=50,
            )
            reply = response.choices[0].message.content
            self.txt_pull_output.append(f"✓ 连接成功！回复: {reply}")
            QMessageBox.information(self, "成功", f"连接成功！\n模型回复: {reply}")
        except Exception as e:
            self.txt_pull_output.append(f"✗ 连接失败: {e}")
            QMessageBox.critical(self, "失败", f"连接失败:\n{e}")
        finally:
            self.btn_test_ollama.setEnabled(True)

    # ── 本地模型浏览 ──

    def _on_browse_model(self):
        """浏览选择 GGUF 模型文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 GGUF 模型文件", str(MODELS_DIR),
            "GGUF 模型 (*.gguf);;所有文件 (*)",
        )
        if path:
            self.le_local_model_path.setText(path)

    # ── 关闭事件 ──

    def closeEvent(self, event):
        """关闭时清理线程"""
        if self._pull_worker and self._pull_worker.isRunning():
            self._pull_worker.wait(3000)
        event.accept()


# ═══════════════════════════════════════════════════════════════
#  TTS 语音测试对话框
# ═══════════════════════════════════════════════════════════════

class TtsTestDialog(QDialog):
    """TTS 语音测试对话框 -- 测试语音合成效果（支持 Edge-TTS 和 CosyVoice2）"""

    # 情感选项
    _EMOTIONS = ["平静", "愤怒", "悲伤", "惊讶", "恐惧", "喜悦", "大笑", "温柔", "冷淡", "紧张"]

    # Edge-TTS 中文音色列表
    _EDGE_VOICES = [
        ("zh-CN-YunyangNeural",   "男声 - 新闻主播，沉稳大气"),
        ("zh-CN-YunxiNeural",     "男声 - 年轻清朗，活力"),
        ("zh-CN-YunjianNeural",   "男声 - 低沉厚重，阳刚"),
        ("zh-CN-YunxiaNeural",    "男声 - 少年音，稚嫩"),
        ("zh-CN-XiaoxiaoNeural",  "女声 - 温暖柔和，标准"),
        ("zh-CN-XiaoyiNeural",    "女声 - 活泼明亮，年轻"),
        ("zh-CN-liaoning-XiaobeiNeural", "女声 - 东北口音"),
        ("zh-CN-shaanxi-XiaoniNeural",   "女声 - 陕西口音"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("语音测试")
        self.setMinimumSize(560, 680)
        self._tts_worker: Optional[TtsTestWorker] = None
        self._audio_path: str = ""

        # 读取当前 TTS 后端设置
        from config import get_tts_config
        tts_config = get_tts_config()
        self._tts_backend = tts_config.get("tts_backend", "edge-tts")

        # 音频播放器
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)
        self._player.positionChanged.connect(self._on_player_position)
        self._player.durationChanged.connect(self._on_player_duration)
        self._player.playbackStateChanged.connect(self._on_playback_state)

        self._build_ui()
        self._on_tts_backend_changed()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── TTS 后端选择 ──
        backend_layout = QHBoxLayout()
        backend_layout.addWidget(QLabel("TTS 引擎:"))
        self.cmb_tts_backend = QComboBox()
        self.cmb_tts_backend.addItems(["Edge-TTS (在线，立即可用)", "CosyVoice2 (本地，需安装)"])
        self.cmb_tts_backend.currentIndexChanged.connect(self._on_tts_backend_changed)
        backend_layout.addWidget(self.cmb_tts_backend, 1)
        layout.addLayout(backend_layout)

        # ── Edge-TTS 音色选择 ──
        self.voice_group = QGroupBox("音色选择 (Edge-TTS)")
        voice_layout = QVBoxLayout(self.voice_group)
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("音色:"))
        self.cmb_voice = QComboBox()
        for voice_id, desc in self._EDGE_VOICES:
            self.cmb_voice.addItem(f"{desc} ({voice_id})", voice_id)
        voice_row.addWidget(self.cmb_voice, 1)
        self.btn_preview_voice = QPushButton("试听音色")
        self.btn_preview_voice.clicked.connect(self._on_preview_voice)
        voice_row.addWidget(self.btn_preview_voice)
        voice_layout.addLayout(voice_row)
        layout.addWidget(self.voice_group)

        # ── 参考音频（CosyVoice2 声音克隆）──
        self.ref_group = QGroupBox("参考音频 (CosyVoice2 声音克隆)")
        ref_layout = QVBoxLayout(self.ref_group)

        ref_audio_layout = QHBoxLayout()
        ref_audio_layout.addWidget(QLabel("参考音频:"))
        self.le_ref_audio = QLineEdit()
        self.le_ref_audio.setPlaceholderText("选择参考音频文件 (WAV, 16kHz)")
        self.btn_browse_ref = QPushButton("...")
        self.btn_browse_ref.setFixedWidth(40)
        self.btn_browse_ref.clicked.connect(self._on_browse_ref)
        ref_audio_layout.addWidget(self.le_ref_audio, 1)
        ref_audio_layout.addWidget(self.btn_browse_ref)
        ref_layout.addLayout(ref_audio_layout)

        ref_text_layout = QHBoxLayout()
        ref_text_layout.addWidget(QLabel("参考文本:"))
        self.le_ref_text = QLineEdit()
        self.le_ref_text.setPlaceholderText("参考音频对应的文本内容")
        ref_text_layout.addWidget(self.le_ref_text, 1)
        ref_layout.addLayout(ref_text_layout)
        layout.addWidget(self.ref_group)

        # ── 测试文本 ──
        layout.addWidget(QLabel("测试文本:"))
        self.txt_test_text = QPlainTextEdit()
        self.txt_test_text.setPlainText("你好，这是一段测试语音。今天天气真不错，我们一起出去走走吧。")
        self.txt_test_text.setMaximumHeight(80)
        layout.addWidget(self.txt_test_text)

        # ── 情感选择 ──
        emotion_layout = QHBoxLayout()
        emotion_layout.addWidget(QLabel("情感:"))
        self.cmb_emotion = QComboBox()
        self.cmb_emotion.addItems(self._EMOTIONS)
        emotion_layout.addWidget(self.cmb_emotion)
        emotion_layout.addStretch()
        layout.addLayout(emotion_layout)

        # ── 语速滑块 ──
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("语速:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(50, 200)
        self.slider_speed.setValue(100)
        self.lbl_speed = QLabel("1.0x")
        self.lbl_speed.setFixedWidth(40)
        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.slider_speed, 1)
        speed_layout.addWidget(self.lbl_speed)
        layout.addLayout(speed_layout)

        # ── 合成按钮 ──
        self.btn_synth = QPushButton("合成语音")
        self.btn_synth.setObjectName("btn_start")
        self.btn_synth.clicked.connect(self._on_synthesize)
        layout.addWidget(self.btn_synth)

        # ── 状态标签 ──
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #a6adc8; padding: 4px;")
        layout.addWidget(self.lbl_status)

        # ── 音频播放区 ──
        play_group = QGroupBox("音频播放")
        play_layout = QVBoxLayout(play_group)

        play_ctrl_layout = QHBoxLayout()
        self.btn_play = QPushButton("播放")
        self.btn_play.setFixedWidth(80)
        self.btn_play.clicked.connect(self._on_play)
        self.btn_play.setEnabled(False)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setFixedWidth(80)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        self.slider_audio = QSlider(Qt.Orientation.Horizontal)
        self.slider_audio.setRange(0, 1000)
        self.slider_audio.sliderMoved.connect(self._on_slider_moved)
        play_ctrl_layout.addWidget(self.btn_play)
        play_ctrl_layout.addWidget(self.btn_stop)
        play_ctrl_layout.addWidget(self.slider_audio, 1)
        play_layout.addLayout(play_ctrl_layout)

        # 时间显示
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #a6adc8; font-size: 12px;")
        time_layout = QHBoxLayout()
        time_layout.addStretch()
        time_layout.addWidget(self.lbl_time)
        play_layout.addLayout(time_layout)

        layout.addWidget(play_group)
        layout.addStretch()

    # ── TTS 后端切换 ──

    def _on_tts_backend_changed(self):
        """TTS 后端切换时显示/隐藏对应控件"""
        is_edge = self.cmb_tts_backend.currentIndex() == 0
        self._tts_backend = "edge-tts" if is_edge else "cosyvoice"
        self.voice_group.setVisible(is_edge)
        self.ref_group.setVisible(not is_edge)

    # ── 语速变化 ──

    def _on_speed_changed(self, value: int):
        speed = value / 100.0
        self.lbl_speed.setText(f"{speed:.1f}x")

    # ── 浏览参考音频 ──

    def _on_browse_ref(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择参考音频", "",
            "音频文件 (*.wav *.mp3 *.flac);;所有文件 (*)",
        )
        if path:
            self.le_ref_audio.setText(path)

    # ── 试听音色（快速合成一句固定示例）──

    def _on_preview_voice(self):
        """快速试听选中的 Edge-TTS 音色"""
        voice_id = self.cmb_voice.currentData()
        if not voice_id:
            return

        self.btn_preview_voice.setEnabled(False)
        self.lbl_status.setText(f"正在试听音色: {voice_id}...")
        self.lbl_status.setStyleSheet("color: #f9e2af; padding: 4px;")

        self._tts_worker = TtsTestWorker(
            text="你好，这是我的声音。很高兴认识你！",
            voice=voice_id,
            emotion="平静",
            speed=1.0,
            tts_backend="edge-tts",
        )
        self._tts_worker.log.connect(self._on_tts_log)
        self._tts_worker.synth_finished.connect(self._on_tts_finished)
        self._tts_worker.error.connect(self._on_tts_error)
        self._tts_worker.start()

    # ── 合成 ──

    def _on_synthesize(self):
        """执行语音合成"""
        text = self.txt_test_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请输入测试文本")
            return

        self.btn_synth.setEnabled(False)
        self.lbl_status.setText("正在合成...")
        self.lbl_status.setStyleSheet("color: #f9e2af; padding: 4px;")

        if self._tts_backend == "edge-tts":
            voice_id = self.cmb_voice.currentData()
            self._tts_worker = TtsTestWorker(
                text=text,
                voice=voice_id,
                emotion=self.cmb_emotion.currentText(),
                speed=self.slider_speed.value() / 100.0,
                tts_backend="edge-tts",
            )
        else:
            self._tts_worker = TtsTestWorker(
                text=text,
                reference_audio=self.le_ref_audio.text().strip() or None,
                reference_text=self.le_ref_text.text().strip() or None,
                emotion=self.cmb_emotion.currentText(),
                speed=self.slider_speed.value() / 100.0,
                tts_backend="cosyvoice",
            )

        self._tts_worker.log.connect(self._on_tts_log)
        self._tts_worker.synth_finished.connect(self._on_tts_finished)
        self._tts_worker.error.connect(self._on_tts_error)
        self._tts_worker.start()

    def _on_tts_log(self, msg: str):
        """TTS 进度日志"""
        self.lbl_status.setText(msg)

    def _on_tts_finished(self, audio_path: str):
        """TTS 合成完成"""
        self._audio_path = audio_path
        self.btn_synth.setEnabled(True)
        self.btn_preview_voice.setEnabled(True)
        self.lbl_status.setText(f"合成完成: {Path(audio_path).name}")
        self.lbl_status.setStyleSheet("color: #a6e3a1; padding: 4px;")
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)
        # 自动播放
        self._play_audio(audio_path)

    def _on_tts_error(self, error: str):
        """TTS 合成错误"""
        self.btn_synth.setEnabled(True)
        self.btn_preview_voice.setEnabled(True)
        self.lbl_status.setText(f"错误: {error}")
        self.lbl_status.setStyleSheet("color: #f38ba8; padding: 4px;")
        QMessageBox.critical(self, "错误", f"语音合成失败:\n{error}")

    # ── 音频播放 ──

    def _play_audio(self, path: str):
        """播放音频文件"""
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self.btn_play.setText("暂停")

    def _on_play(self):
        """播放 / 暂停"""
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.btn_play.setText("继续")
        elif state in (QMediaPlayer.PlaybackState.PausedState, QMediaPlayer.PlaybackState.StoppedState):
            self._player.play()
            self.btn_play.setText("暂停")

    def _on_stop(self):
        """停止播放"""
        self._player.stop()
        self.btn_play.setText("播放")
        self.slider_audio.setValue(0)

    def _on_player_position(self, position: int):
        """播放进度更新"""
        duration = self._player.duration()
        if duration > 0:
            self.slider_audio.setValue(int(position / duration * 1000))
        self._update_time_label(position, duration)

    def _on_player_duration(self, duration: int):
        """时长更新"""
        self._update_time_label(self._player.position(), duration)

    def _on_playback_state(self, state):
        """播放状态变化"""
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.btn_play.setText("播放")
            self.slider_audio.setValue(0)

    def _update_time_label(self, position: int, duration: int):
        """更新时间标签"""
        self.lbl_time.setText(f"{self._ms_to_str(position)} / {self._ms_to_str(duration)}")

    @staticmethod
    def _ms_to_str(ms: int) -> str:
        """毫秒转 mm:ss"""
        if ms <= 0:
            return "00:00"
        seconds = ms // 1000
        m = seconds // 60
        s = seconds % 60
        return f"{m:02d}:{s:02d}"

    def _on_slider_moved(self, value: int):
        """拖动进度条"""
        duration = self._player.duration()
        if duration > 0:
            self._player.setPosition(int(value / 1000 * duration))

    # ── 关闭事件 ──

    def closeEvent(self, event):
        """关闭时停止播放和线程"""
        self._player.stop()
        if self._tts_worker and self._tts_worker.isRunning():
            self._tts_worker.wait(3000)
        event.accept()


# ═══════════════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("小说转广播剧 - Novel to Radio Drama")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        # 状态
        self._worker: Optional[PipelineWorker] = None
        self._script: Optional[dict] = None
        self._audio_segments: dict[str, str] = {}  # seg_key -> audio_path
        self._final_output: str = ""

        # 音频播放器
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)
        self._player.positionChanged.connect(self._on_player_position)
        self._player.durationChanged.connect(self._on_player_duration)
        self._player.playbackStateChanged.connect(self._on_playback_state)

        # 构建 UI
        self._build_ui()

        # 更新 LLM 显示
        self._update_llm_display()

        # 更新 TTS 显示
        self._update_tts_display()

        # 定时器用于更新播放进度
        self._play_timer = QTimer()
        self._play_timer.setInterval(100)

    def _build_ui(self):
        """构建界面"""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(8)

        # ── 文件输入区 ──
        file_group = QGroupBox("文件")
        file_layout = QHBoxLayout(file_group)
        self.btn_open = QPushButton("打开小说")
        self.btn_open.clicked.connect(self._on_open_file)
        self.le_file = QLineEdit()
        self.le_file.setPlaceholderText("选择小说文本文件 (.txt)")
        self.le_file.setReadOnly(True)
        self.btn_open_script = QPushButton("加载剧本")
        self.btn_open_script.clicked.connect(self._on_open_script)
        file_layout.addWidget(self.btn_open)
        file_layout.addWidget(self.le_file, 1)
        file_layout.addWidget(self.btn_open_script)
        main_layout.addWidget(file_group)

        # ── 配置区 ──
        config_group = QGroupBox("配置")
        config_layout = QGridLayout(config_group)
        config_layout.setHorizontalSpacing(16)

        # LLM 后端（显示当前设置，可通过设置对话框修改）
        config_layout.addWidget(QLabel("LLM 后端:"), 0, 0)
        self.cmb_llm = QComboBox()
        self.cmb_llm.addItems(["LM Studio (本地推荐)", "API (云端/LM Studio HTTP)", "Ollama (本地)", "llama-cpp (本地GGUF)"])
        self.cmb_llm.currentIndexChanged.connect(self._on_llm_backend_changed)
        config_layout.addWidget(self.cmb_llm, 0, 1)

        # 旁白音色
        config_layout.addWidget(QLabel("旁白音色:"), 0, 2)
        self.cmb_narrator = QComboBox()
        self.cmb_narrator.addItems(["男声 (narrator_male)", "女声 (narrator_female)"])
        config_layout.addWidget(self.cmb_narrator, 0, 3)

        # TTS 后端
        config_layout.addWidget(QLabel("TTS 引擎:"), 0, 4)
        self.cmb_tts = QComboBox()
        self.cmb_tts.addItems(["Edge-TTS", "CosyVoice2"])
        self.cmb_tts.currentIndexChanged.connect(self._on_tts_backend_changed)
        config_layout.addWidget(self.cmb_tts, 0, 5)

        # 缓存
        self.cb_cache = QCheckBox("使用缓存")
        self.cb_cache.setChecked(True)
        config_layout.addWidget(self.cb_cache, 0, 6)

        # 当前模型名称 + 设置 / 语音测试按钮
        self.lbl_llm_model = QLabel("当前: 未配置")
        self.lbl_llm_model.setStyleSheet("color: #a6adc8; padding: 2px 0;")
        config_layout.addWidget(self.lbl_llm_model, 1, 0, 1, 3)

        self.btn_settings = QPushButton("设置")
        self.btn_settings.clicked.connect(self._on_open_settings)
        config_layout.addWidget(self.btn_settings, 1, 3)

        self.btn_tts_test = QPushButton("语音测试")
        self.btn_tts_test.clicked.connect(self._on_open_tts_test)
        config_layout.addWidget(self.btn_tts_test, 1, 4)

        # 输出路径
        config_layout.addWidget(QLabel("输出:"), 2, 0)
        self.le_output = QLineEdit()
        self.le_output.setPlaceholderText("输出音频路径 (留空=自动)")
        self.btn_output = QPushButton("...")
        self.btn_output.setFixedWidth(40)
        self.btn_output.clicked.connect(self._on_select_output)
        config_layout.addWidget(self.le_output, 2, 1, 1, 3)
        config_layout.addWidget(self.btn_output, 2, 4)

        main_layout.addWidget(config_group)

        # ── 控制按钮 ──
        btn_layout = QHBoxLayout()
        self.btn_generate = QPushButton("开始生成")
        self.btn_generate.setObjectName("btn_start")
        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_analyze = QPushButton("仅分析剧本")
        self.btn_analyze.clicked.connect(self._on_analyze)
        self.btn_synthesize = QPushButton("仅合成语音")
        self.btn_synthesize.clicked.connect(self._on_synthesize)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_cancel.setEnabled(False)
        btn_layout.addWidget(self.btn_generate)
        btn_layout.addWidget(self.btn_analyze)
        btn_layout.addWidget(self.btn_synthesize)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)

        # ── 进度条 ──
        progress_layout = QHBoxLayout()
        self.label_stage = QLabel("就绪")
        self.label_stage.setFixedWidth(200)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.label_progress = QLabel("0%")
        self.label_progress.setFixedWidth(50)
        progress_layout.addWidget(self.label_stage)
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.label_progress)
        main_layout.addLayout(progress_layout)

        # ── 主体区域 (分割器) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧: 剧本树
        script_widget = QWidget()
        script_layout = QVBoxLayout(script_widget)
        script_layout.setContentsMargins(0, 0, 0, 0)
        script_label = QLabel("剧本浏览")
        script_label.setStyleSheet("font-weight: bold; color: #89b4fa; padding: 2px;")
        script_layout.addWidget(script_label)
        self.tree_script = QTreeWidget()
        self.tree_script.setHeaderLabels(["类型", "说话人", "内容", "情感"])
        self.tree_script.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_script.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_script.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree_script.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_script.setAlternatingRowColors(True)
        self.tree_script.itemClicked.connect(self._on_tree_item_clicked)
        script_layout.addWidget(self.tree_script)
        splitter.addWidget(script_widget)

        # 右侧: 标签页 (日志 + 预览)
        tab_widget = QTabWidget()

        # 日志页
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(5000)
        tab_widget.addTab(self.log_text, "日志")

        # 预览页
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)

        # 当前播放信息
        self.label_current = QLabel("未选择音频")
        self.label_current.setStyleSheet("font-size: 13px; padding: 4px; color: #a6adc8;")
        self.label_current.setWordWrap(True)
        preview_layout.addWidget(self.label_current)

        # 播放控制
        play_layout = QHBoxLayout()
        self.btn_play = QPushButton("播放")
        self.btn_play.setFixedWidth(80)
        self.btn_play.clicked.connect(self._on_play)
        self.btn_play.setEnabled(False)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setFixedWidth(80)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        self.slider_audio = QSlider(Qt.Orientation.Horizontal)
        self.slider_audio.setRange(0, 1000)
        self.slider_audio.sliderMoved.connect(self._on_slider_moved)
        play_layout.addWidget(self.btn_play)
        play_layout.addWidget(self.btn_stop)
        play_layout.addWidget(self.slider_audio, 1)
        preview_layout.addLayout(play_layout)

        # 时间显示
        time_layout = QHBoxLayout()
        self.label_time = QLabel("00:00 / 00:00")
        self.label_time.setStyleSheet("color: #a6adc8; font-size: 12px;")
        time_layout.addStretch()
        time_layout.addWidget(self.label_time)
        preview_layout.addLayout(time_layout)

        # 音量控制
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("音量:"))
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(80)
        self.slider_volume.setFixedWidth(120)
        self.slider_volume.valueChanged.connect(self._on_volume_changed)
        vol_layout.addWidget(self.slider_volume)
        vol_layout.addStretch()
        preview_layout.addLayout(vol_layout)

        # 已合成片段列表
        preview_label = QLabel("已合成音频片段:")
        preview_label.setStyleSheet("font-weight: bold; color: #89b4fa; padding: 4px 0;")
        preview_layout.addWidget(preview_label)

        self.tree_segments = QTreeWidget()
        self.tree_segments.setHeaderLabels(["#", "说话人", "内容", "状态"])
        self.tree_segments.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_segments.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_segments.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree_segments.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_segments.setAlternatingRowColors(True)
        self.tree_segments.itemDoubleClicked.connect(self._on_segment_double_clicked)
        preview_layout.addWidget(self.tree_segments)

        tab_widget.addTab(preview_widget, "音频预览")

        splitter.addWidget(tab_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 500])
        main_layout.addWidget(splitter, 1)

        # ── 状态栏 ──
        self.statusBar().showMessage("就绪")

    # ═══════════════════════════════════════════════════════════════
    #  LLM 显示 & 设置 / 语音测试
    # ═══════════════════════════════════════════════════════════════

    def _update_llm_display(self):
        """从 settings.json 读取并更新 LLM 后端显示和模型名标签"""
        settings = get_llm_config()
        backend = settings.get("llm_backend", "ollama")

        # 更新下拉框（不触发信号）
        backend_map = {"ollama": 0, "api": 1, "local": 2}
        self.cmb_llm.blockSignals(True)
        self.cmb_llm.setCurrentIndex(backend_map.get(backend, 0))
        self.cmb_llm.blockSignals(False)

        # 更新模型名标签
        backend_labels = {"ollama": "Ollama", "api": "API", "local": "llama-cpp"}
        backend_label = backend_labels.get(backend, backend)

        if backend == "ollama":
            model = settings.get("ollama_model", "qwen3:4b")
        elif backend == "api":
            model = settings.get("llm_api_model", "gpt-4o-mini")
        else:
            model = Path(settings.get("local_model_path", "")).name or "未配置"

        self.lbl_llm_model.setText(f"当前: {model} ({backend_label})")

    def _update_tts_display(self):
        """从 settings.json 读取并更新 TTS 后端显示"""
        from config import get_tts_config
        tts_config = get_tts_config()
        backend = tts_config.get("tts_backend", "edge-tts")
        self.cmb_tts.blockSignals(True)
        self.cmb_tts.setCurrentIndex(0 if backend == "edge-tts" else 1)
        self.cmb_tts.blockSignals(False)

    def _on_tts_backend_changed(self, idx: int):
        """TTS 后端切换 -- 保存到设置"""
        backend = "edge-tts" if idx == 0 else "cosyvoice"
        settings = load_settings()
        settings["tts_backend"] = backend
        save_settings(settings)
        self.log_text.appendPlainText(f"[设置] TTS 后端已切换为: {backend}")

    def _on_llm_backend_changed(self, idx: int):
        """主窗口 LLM 后端下拉框变化 -- 保存到设置"""
        backend_map = {0: "ollama", 1: "api", 2: "local"}
        backend = backend_map.get(idx, "ollama")

        settings = load_settings()
        settings["llm_backend"] = backend
        save_settings(settings)

        self._update_llm_display()
        self.log_text.appendPlainText(f"[设置] LLM 后端已切换为: {backend}")

    def _on_open_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        dialog.exec()
        # 设置关闭后刷新显示
        self._update_llm_display()
        self._update_tts_display()

    def _on_open_tts_test(self):
        """打开语音测试对话框"""
        dialog = TtsTestDialog(self)
        dialog.exec()

    # ═══════════════════════════════════════════════════════════════
    #  文件操作
    # ═══════════════════════════════════════════════════════════════

    def _on_open_file(self):
        """打开小说文本文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择小说文本", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if path:
            self.le_file.setText(path)
            self.log_text.appendPlainText(f"[文件] 已选择: {path}")

    def _on_open_script(self):
        """加载已有剧本"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择剧本 JSON", str(OUTPUT_DIR), "JSON 文件 (*.json)"
        )
        if path:
            from utils.text_utils import load_json
            try:
                script = load_json(path)
                self._script = script
                self._populate_script_tree(script)
                self.log_text.appendPlainText(f"[剧本] 已加载: {path}")
                self.statusBar().showMessage(f"剧本已加载: {script.get('title', '未命名')}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"加载剧本失败:\n{e}")

    def _on_select_output(self):
        """选择输出路径"""
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出路径", str(OUTPUT_DIR), "WAV 文件 (*.wav);;MP3 文件 (*.mp3)"
        )
        if path:
            self.le_output.setText(path)

    # ═══════════════════════════════════════════════════════════════
    #  流水线控制
    # ═══════════════════════════════════════════════════════════════

    def _get_llm_backend(self) -> str:
        """从 settings.json 获取当前 LLM 后端（而非从下拉框获取）"""
        return get_llm_config().get("llm_backend", "ollama")

    def _get_narrator_voice(self) -> str:
        return "narrator_male" if self.cmb_narrator.currentIndex() == 0 else "narrator_female"

    def _start_worker(self, mode: str):
        """启动后台工作线程"""
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "提示", "正在处理中，请等待或取消当前任务。")
            return

        # 验证输入
        if mode in ("generate", "analyze"):
            if not self.le_file.text():
                QMessageBox.warning(self, "提示", "请先选择小说文本文件。")
                return
            input_path = self.le_file.text()
            script_path = ""
        else:
            if not self._script:
                QMessageBox.warning(self, "提示", "请先加载剧本或运行分析。")
                return
            input_path = ""
            script_path = str(OUTPUT_DIR / f"{self._script.get('title', 'output')}_script.json")

        # 保存剧本到文件（合成模式需要）
        if mode == "synthesize" and self._script:
            from utils.text_utils import save_json
            script_path = str(OUTPUT_DIR / f"{self._script.get('title', 'output')}_script.json")
            save_json(self._script, script_path)

        output_path = self.le_output.text() or None

        # 清空状态
        self._audio_segments.clear()
        self.tree_segments.clear()
        self.progress_bar.setValue(0)
        self.label_progress.setText("0%")
        self.log_text.clear()

        # 禁用按钮
        self._set_buttons_running(True)

        # 创建工作线程（后端由 settings.json 决定，llm_backend 参数仅保留兼容）
        self._worker = PipelineWorker(
            mode=mode,
            input_path=input_path,
            script_path=script_path,
            output_path=output_path,
            use_cache=self.cb_cache.isChecked(),
            llm_backend=self._get_llm_backend(),
            narrator_voice=self._get_narrator_voice(),
        )

        # 连接信号
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.script_ready.connect(self._on_script_ready)
        self._worker.segment_ready.connect(self._on_segment_ready)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        self._worker.start()
        self.statusBar().showMessage(f"正在运行: {mode}")

    def _on_generate(self):
        """开始完整生成"""
        self._start_worker("generate")

    def _on_analyze(self):
        """仅分析剧本"""
        self._start_worker("analyze")

    def _on_synthesize(self):
        """仅合成语音"""
        self._start_worker("synthesize")

    def _on_cancel(self):
        """取消处理"""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.log_text.appendPlainText("[取消] 正在停止...")
            self.statusBar().showMessage("正在取消...")

    def _set_buttons_running(self, running: bool):
        """设置按钮状态"""
        self.btn_generate.setEnabled(not running)
        self.btn_analyze.setEnabled(not running)
        self.btn_synthesize.setEnabled(not running)
        self.btn_cancel.setEnabled(running)

    # ═══════════════════════════════════════════════════════════════
    #  信号处理
    # ═══════════════════════════════════════════════════════════════

    def _on_progress(self, stage: int, stage_name: str, current: int, total: int, message: str):
        """处理进度信号"""
        self.label_stage.setText(f"Stage {stage}: {stage_name}")
        if total > 0:
            pct = int(current / total * 100)
            self.progress_bar.setValue(pct)
            self.label_progress.setText(f"{pct}%")
        self.statusBar().showMessage(message)

    def _on_log(self, message: str):
        """处理日志信号"""
        self.log_text.appendPlainText(message)

    def _on_script_ready(self, script: dict):
        """剧本就绪 - 填充剧本树"""
        self._script = script
        self._populate_script_tree(script)

    def _on_segment_ready(self, seg_key: str, audio_path: str, line: dict):
        """音频片段就绪 - 添加到片段列表"""
        self._audio_segments[seg_key] = audio_path

        # 添加到片段树
        speaker = line.get("speaker") or "旁白"
        text_preview = line["text"][:40] + ("..." if len(line["text"]) > 40 else "")
        emotion = line.get("emotion") or ""

        item = QTreeWidgetItem([
            str(len(self._audio_segments)),
            speaker,
            text_preview,
            "已合成",
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, seg_key)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, audio_path)

        # 根据类型设置颜色
        if line["type"] == "dialogue":
            item.setForeground(1, C_BLUE)
        else:
            item.setForeground(1, C_GRAY)

        self.tree_segments.addTopLevelItem(item)
        self.tree_segments.scrollToBottom()

    def _on_finished(self, output_path: str):
        """生成完成"""
        self._final_output = output_path
        self.log_text.appendPlainText(f"\n[完成] 输出文件: {output_path}")
        self.statusBar().showMessage(f"完成: {output_path}")
        QMessageBox.information(self, "完成", f"广播剧已生成:\n{output_path}")

    def _on_error(self, error: str):
        """处理错误"""
        self.log_text.appendPlainText(f"\n[错误] {error}")
        QMessageBox.critical(self, "错误", error)

    def _on_worker_finished(self):
        """工作线程结束"""
        self._set_buttons_running(False)
        if self._final_output:
            self.statusBar().showMessage(f"完成: {self._final_output}")
        else:
            self.statusBar().showMessage("就绪")

    # ═══════════════════════════════════════════════════════════════
    #  剧本树
    # ═══════════════════════════════════════════════════════════════

    def _populate_script_tree(self, script: dict):
        """填充剧本树"""
        self.tree_script.clear()

        for chapter in script.get("chapters", []):
            ch_item = QTreeWidgetItem([
                f"第{chapter['chapter_id']}章",
                "",
                chapter.get("title", ""),
                "",
            ])
            ch_item.setForeground(0, C_YELLOW)
            f = ch_item.font(0)
            f.setBold(True)
            ch_item.setFont(0, f)

            for scene in chapter.get("scenes", []):
                scene_item = QTreeWidgetItem([
                    f"场景 {scene.get('scene_id', '')}",
                    "",
                    f"[{scene.get('location', '')}] {scene.get('mood', '')}",
                    "",
                ])
                scene_item.setForeground(0, C_PURPLE)
                f = scene_item.font(0)
                f.setBold(True)
                scene_item.setFont(0, f)

                for line_idx, line in enumerate(scene.get("lines", [])):
                    seg_key = f"{chapter['chapter_id']}-{scene.get('scene_id', '')}-{line_idx}"
                    line_type = line["type"]
                    speaker = line.get("speaker") or "旁白"
                    text = line["text"]
                    emotion = line.get("emotion") or ""

                    # 截断过长文本
                    if len(text) > 80:
                        text = text[:80] + "..."

                    line_item = QTreeWidgetItem([
                        line_type,
                        speaker,
                        text,
                        emotion,
                    ])
                    line_item.setData(0, Qt.ItemDataRole.UserRole, seg_key)

                    # 颜色区分
                    if line_type == "dialogue":
                        line_item.setForeground(1, C_BLUE)
                        line_item.setForeground(2, C_GREEN)
                    elif line_type == "narration":
                        line_item.setForeground(1, C_GRAY)
                        line_item.setForeground(2, C_GRAY)

                    # 如果已有音频，标记
                    if seg_key in self._audio_segments:
                        line_item.setForeground(3, C_GREEN)

                    scene_item.addChild(line_item)

                ch_item.addChild(scene_item)

            self.tree_script.addTopLevelItem(ch_item)

        self.tree_script.expandToDepth(0)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        """点击剧本树项 - 如果有音频则准备播放"""
        seg_key = item.data(0, Qt.ItemDataRole.UserRole)
        if seg_key and seg_key in self._audio_segments:
            audio_path = self._audio_segments[seg_key]
            self._play_audio(audio_path, item.text(1), item.text(2))

    # ═══════════════════════════════════════════════════════════════
    #  音频预览
    # ═══════════════════════════════════════════════════════════════

    def _play_audio(self, path: str, speaker: str = "", text: str = ""):
        """播放音频文件"""
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

        self.btn_play.setText("暂停")
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)

        info = f"{speaker}: {text}" if speaker else Path(path).name
        self.label_current.setText(info)
        self.label_current.setStyleSheet("font-size: 13px; padding: 4px; color: #a6e3a1;")

    def _on_play(self):
        """播放/暂停"""
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.btn_play.setText("继续")
        elif state in (QMediaPlayer.PlaybackState.PausedState, QMediaPlayer.PlaybackState.StoppedState):
            self._player.play()
            self.btn_play.setText("暂停")

    def _on_stop(self):
        """停止播放"""
        self._player.stop()
        self.btn_play.setText("播放")
        self.slider_audio.setValue(0)

    def _on_segment_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击片段列表播放"""
        audio_path = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if audio_path and Path(audio_path).exists():
            self._play_audio(audio_path, item.text(1), item.text(2))

    def _on_player_position(self, position: int):
        """播放进度更新"""
        duration = self._player.duration()
        if duration > 0:
            self.slider_audio.setValue(int(position / duration * 1000))
        self._update_time_label(position, duration)

    def _on_player_duration(self, duration: int):
        """时长更新"""
        self._update_time_label(self._player.position(), duration)

    def _on_playback_state(self, state):
        """播放状态变化"""
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.btn_play.setText("播放")
            self.slider_audio.setValue(0)

    def _update_time_label(self, position: int, duration: int):
        """更新时间标签"""
        pos_str = self._ms_to_str(position)
        dur_str = self._ms_to_str(duration)
        self.label_time.setText(f"{pos_str} / {dur_str}")

    @staticmethod
    def _ms_to_str(ms: int) -> str:
        """毫秒转 mm:ss"""
        if ms <= 0:
            return "00:00"
        seconds = ms // 1000
        m = seconds // 60
        s = seconds % 60
        return f"{m:02d}:{s:02d}"

    def _on_slider_moved(self, value: int):
        """拖动进度条"""
        duration = self._player.duration()
        if duration > 0:
            self._player.setPosition(int(value / 1000 * duration))

    def _on_volume_changed(self, value: int):
        """音量变化"""
        self._audio_output.setVolume(value / 100.0)

    # ═══════════════════════════════════════════════════════════════
    #  关闭事件
    # ═══════════════════════════════════════════════════════════════

    def closeEvent(self, event):
        """关闭窗口时停止线程"""
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "确认", "正在处理中，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._worker.cancel()
            self._worker.wait(3000)

        self._player.stop()
        event.accept()


# ═══════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    # 设置应用字体
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()