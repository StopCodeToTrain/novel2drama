"""流水线编排器 - 串联所有 Stage，实现端到端小说转广播剧"""

import sys
import time
from pathlib import Path
from typing import Dict, Optional, Callable, Any

sys.path.insert(0, str(Path(__file__).parent))

from text_analysis.script_generator import ScriptGenerator
from text_analysis.llm_client import LLMClient
from voice_design.voice_assigner import VoiceAssigner
from tts_engine.cosyvoice_backend import CosyVoiceBackend
from tts_engine.edge_tts_backend import EdgeTTSBackend
from mixer.audio_mixer import AudioMixer
from utils.text_utils import read_text_file, clean_text, save_json, load_json
from utils.cache import get_cache_key, save_cache, load_cache, cache_exists
from config import OUTPUT_DIR, TTSConfig, get_tts_config


class NovelToDramaPipeline:
    """小说转广播剧流水线

    支持进度回调，用于 GUI 实时显示进度：

    回调签名:
        on_progress(stage: int, stage_name: str, current: int, total: int, message: str)
        on_log(message: str)
        on_script_ready(script: dict)
        on_segment_ready(seg_key: str, audio_path: str, line: dict)
        on_finished(output_path: str)
        on_error(error: str)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        tts_backend: Optional[CosyVoiceBackend] = None,
        use_cache: bool = True,
    ):
        self.llm = llm_client or LLMClient()
        self.tts = tts_backend  # 延迟初始化
        self.script_generator = ScriptGenerator(self.llm)
        self.voice_assigner = VoiceAssigner()
        self.mixer = AudioMixer()
        self.use_cache = use_cache

        # 回调函数
        self.on_progress: Optional[Callable] = None
        self.on_log: Optional[Callable] = None
        self.on_script_ready: Optional[Callable] = None
        self.on_segment_ready: Optional[Callable] = None
        self.on_finished: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

        # 取消标志
        self._cancelled = False

    def cancel(self):
        """请求取消处理"""
        self._cancelled = True

    def cleanup(self):
        """释放所有资源（模型连接、大对象引用等）"""
        import gc

        # 释放 LLM 客户端（含 LM Studio SDK 模型连接）
        if self.llm:
            self.llm.close()

        # 释放 TTS 后端
        if self.tts is not None:
            if hasattr(self.tts, 'close'):
                try:
                    self.tts.close()
                except Exception:
                    pass
            self.tts = None

        # 清空大对象引用
        self.script_generator = None
        self.voice_assigner = None
        self.mixer = None

        # 强制垃圾回收
        gc.collect()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def _emit_progress(self, stage: int, stage_name: str, current: int, total: int, message: str = ""):
        """发送进度回调"""
        if self.on_progress:
            self.on_progress(stage, stage_name, current, total, message)

    def _emit_log(self, message: str):
        """发送日志回调"""
        if self.on_log:
            self.on_log(message)
        else:
            print(message)

    def _emit_script(self, script: dict):
        """发送剧本就绪回调"""
        if self.on_script_ready:
            self.on_script_ready(script)

    def _emit_segment(self, seg_key: str, audio_path: str, line: dict):
        """发送音频片段就绪回调"""
        if self.on_segment_ready:
            self.on_segment_ready(seg_key, audio_path, line)

    def _emit_finished(self, output_path: str):
        """发送完成回调"""
        if self.on_finished:
            self.on_finished(output_path)

    def _emit_error(self, error: str):
        """发送错误回调"""
        if self.on_error:
            self.on_error(error)
        else:
            print(f"错误: {error}")

    def run(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        script_path: Optional[str] = None,
    ) -> str:
        """
        运行完整流水线

        Args:
            input_path: 输入小说文本路径
            output_path: 输出音频路径（默认 output/标题.wav）
            script_path: 剧本 JSON 路径（用于保存/加载中间结果）

        Returns:
            输出音频文件路径
        """
        self._cancelled = False
        start_time = time.time()
        title = Path(input_path).stem

        # 设置输出路径
        if output_path is None:
            output_path = str(OUTPUT_DIR / f"{title}.wav")
        if script_path is None:
            script_path = str(OUTPUT_DIR / f"{title}_script.json")

        try:
            # ============ Stage 1: 文本分析 ============
            self._emit_log("=" * 60)
            self._emit_log("Stage 1: 文本分析与剧本化")
            self._emit_log("=" * 60)
            self._emit_progress(1, "文本分析", 0, 4, "开始文本分析...")

            if self.use_cache and Path(script_path).exists():
                self._emit_log(f"从缓存加载剧本: {script_path}")
                self._emit_progress(1, "文本分析", 1, 4, "加载缓存剧本...")
                script = load_json(script_path)
                self._emit_progress(1, "文本分析", 4, 4, "剧本加载完成")
            else:
                text = clean_text(read_text_file(input_path))
                # 设置 script_generator 的进度回调
                self.script_generator.on_progress = lambda cur, tot, msg: self._emit_progress(1, "文本分析", cur, tot, msg)
                self.script_generator.on_log = self._emit_log
                script = self.script_generator.generate(text, title=title, use_cache=self.use_cache)
                save_json(script, script_path)
                self._emit_log(f"剧本已保存: {script_path}")

            self._print_script_stats(script)
            self._emit_script(script)

            if self._cancelled:
                self._emit_log("已取消")
                return ""

            # ============ Stage 2: 声音设计 ============
            self._emit_log("=" * 60)
            self._emit_log("Stage 2: 角色声音分配")
            self._emit_log("=" * 60)
            self._emit_progress(2, "声音设计", 0, 1, "分配角色音色...")

            script = self.voice_assigner.assign_voices(script)

            tts_config = get_tts_config()
            if tts_config.get("tts_backend") == "edge-tts":
                self._emit_log("使用 Edge-TTS 在线语音合成（无需参考音频）")
            else:
                available = self.voice_assigner.list_available_voices()
                has_voices = any(v["available"] for v in available)
                if not has_voices:
                    self._emit_log("警告: 未找到预设参考音频文件！")
                    self._emit_log(f"请将参考音频文件放在: {self.voice_assigner.voices_dir}")
                    self._emit_log("将使用 CosyVoice2 默认音色（无声音克隆）")

            self._emit_progress(2, "声音设计", 1, 1, "角色音色分配完成")

            if self._cancelled:
                self._emit_log("已取消")
                return ""

            # ============ Stage 3: 语音合成 ============
            self._emit_log("=" * 60)
            self._emit_log("Stage 3: 逐句语音合成")
            self._emit_log("=" * 60)

            audio_segments = self._synthesize_script(script)

            if self._cancelled:
                self._emit_log("已取消")
                return ""

            # ============ Stage 5: 混音输出 ============
            self._emit_log("=" * 60)
            self._emit_log("Stage 5: 混音与导出")
            self._emit_log("=" * 60)
            self._emit_progress(5, "混音导出", 0, 1, "正在混音...")

            self.mixer.mix_script(script, audio_segments, output_path)

            self._emit_progress(5, "混音导出", 1, 1, "导出完成")

            elapsed = time.time() - start_time
            self._emit_log(f"\n完成！总耗时: {elapsed:.1f} 秒")
            self._emit_log(f"输出文件: {output_path}")
            self._emit_finished(output_path)

            return output_path

        except Exception as e:
            self._emit_error(str(e))
            raise

    def _synthesize_script(self, script: Dict) -> Dict[str, str]:
        """
        为剧本中每一行生成语音

        Returns:
            {segment_key: audio_file_path}
        """
        # 懒加载 TTS
        if self.tts is None:
            tts_config = get_tts_config()
            backend = tts_config.get("tts_backend", "edge-tts")
            self._emit_log(f"加载 TTS 引擎: {backend}")
            if backend == "cosyvoice":
                self.tts = CosyVoiceBackend()
            else:
                self.tts = EdgeTTSBackend()

        # 判断是否为 edge-tts 模式
        use_edge_tts = isinstance(self.tts, EdgeTTSBackend)

        audio_segments = {}
        narrator = script.get("narrator_voice", {})
        narrator_ref = narrator.get("reference_audio")
        narrator_text = narrator.get("reference_text")
        narrator_voice = narrator.get("voice")

        # 统计总行数
        total_lines = sum(
            len(scene.get("lines", []))
            for chapter in script.get("chapters", [])
            for scene in chapter.get("scenes", [])
        )
        self._emit_log(f"共 {total_lines} 行需要合成")

        current_idx = 0
        for chapter in script.get("chapters", []):
            if self._cancelled:
                break
            chapter_id = chapter["chapter_id"]
            self._emit_log(f"  章节 {chapter_id}: {chapter.get('title', '')}")

            for scene in chapter.get("scenes", []):
                if self._cancelled:
                    break
                scene_id = scene["scene_id"]

                for line_idx, line in enumerate(scene.get("lines", [])):
                    if self._cancelled:
                        break

                    seg_key = f"{chapter_id}-{scene_id}-{line_idx}"
                    current_idx += 1

                    # 进度回调
                    line_preview = line["text"][:30] + ("..." if len(line["text"]) > 30 else "")
                    speaker = line.get("speaker") or "旁白"
                    self._emit_progress(
                        3, "语音合成", current_idx, total_lines,
                        f"[{current_idx}/{total_lines}] {speaker}: {line_preview}"
                    )

                    # 检查缓存
                    cache_key = get_cache_key(line["text"] + str(line.get("speaker", "")), prefix="tts")
                    if self.use_cache and cache_exists(cache_key, subdir="tts"):
                        cached = load_cache(cache_key, subdir="tts")
                        if cached and "path" in cached:
                            audio_segments[seg_key] = cached["path"]
                            self._emit_segment(seg_key, cached["path"], line)
                            continue

                    # 确定音色参数
                    if use_edge_tts:
                        # Edge-TTS 模式：传递 voice 名称
                        if line["type"] == "dialogue":
                            voice = self._get_character_voice(script, line.get("speaker"))
                        else:
                            voice = narrator_voice

                        try:
                            audio_path = self.tts.synthesize(
                                text=line["text"],
                                voice=voice,
                                emotion=line.get("emotion"),
                                speed=TTSConfig.speed,
                            )
                        except Exception as e:
                            self._emit_log(f"  合成失败 [{seg_key}]: {e}")
                            self._emit_log(f"    文本: {line['text'][:50]}...")
                            continue
                    else:
                        # CosyVoice 模式：传递参考音频
                        if line["type"] == "dialogue":
                            ref_audio, ref_text = self._get_character_reference(script, line.get("speaker"))
                        else:
                            ref_audio = narrator_ref
                            ref_text = narrator_text

                        try:
                            audio_path = self.tts.synthesize(
                                text=line["text"],
                                reference_audio=ref_audio,
                                reference_text=ref_text,
                                emotion=line.get("emotion"),
                                speed=TTSConfig.speed,
                            )
                        except Exception as e:
                            self._emit_log(f"  合成失败 [{seg_key}]: {e}")
                            self._emit_log(f"    文本: {line['text'][:50]}...")
                            continue

                    audio_segments[seg_key] = audio_path
                    self._emit_segment(seg_key, audio_path, line)

                    # 缓存
                    if self.use_cache:
                        save_cache(cache_key, {"path": audio_path}, subdir="tts")

        self._emit_log(f"成功合成 {len(audio_segments)}/{total_lines} 行")
        return audio_segments

    def _get_character_voice(self, script: Dict, speaker: str) -> Optional[str]:
        """获取角色的 edge-tts 声音名称"""
        if not speaker:
            return None
        for char in script.get("characters", []):
            if char["name"] == speaker or speaker in char.get("aliases", []):
                return char.get("voice")
        return None

    def _get_character_reference(self, script: Dict, speaker: str) -> tuple:
        """获取角色的参考音色"""
        if not speaker:
            return None, None

        for char in script.get("characters", []):
            if char["name"] == speaker or speaker in char.get("aliases", []):
                return char.get("reference_audio"), char.get("reference_text")

        return None, None

    def _print_script_stats(self, script: Dict):
        """打印剧本统计信息"""
        chapters = script.get("chapters", [])
        characters = script.get("characters", [])
        total_scenes = sum(len(ch.get("scenes", [])) for ch in chapters)
        total_lines = sum(
            len(scene.get("lines", []))
            for ch in chapters
            for scene in ch.get("scenes", [])
        )
        dialogue_count = sum(
            1
            for ch in chapters
            for scene in ch.get("scenes", [])
            for line in scene.get("lines", [])
            if line["type"] == "dialogue"
        )

        self._emit_log(f"\n剧本统计:")
        self._emit_log(f"  标题: {script.get('title', '未命名')}")
        self._emit_log(f"  章节数: {len(chapters)}")
        self._emit_log(f"  场景数: {total_scenes}")
        self._emit_log(f"  总行数: {total_lines}")
        self._emit_log(f"  对话行: {dialogue_count}")
        self._emit_log(f"  旁白行: {total_lines - dialogue_count}")
        self._emit_log(f"  角色数: {len(characters)}")
        for char in characters:
            aliases = "、".join(char.get("aliases", []))
            self._emit_log(f"    - {char['name']}（别名：{aliases}）" if aliases else f"    - {char['name']}")

    # ============ 分步执行方法 ============

    def analyze_only(self, input_path: str, script_path: Optional[str] = None) -> str:
        """仅执行文本分析，生成剧本"""
        self._cancelled = False
        title = Path(input_path).stem
        if script_path is None:
            script_path = str(OUTPUT_DIR / f"{title}_script.json")

        text = clean_text(read_text_file(input_path))
        self.script_generator.on_progress = lambda cur, tot, msg: self._emit_progress(1, "文本分析", cur, tot, msg)
        self.script_generator.on_log = self._emit_log
        script = self.script_generator.generate(text, title=title, use_cache=self.use_cache)
        save_json(script, script_path)
        self._print_script_stats(script)
        self._emit_script(script)
        self._emit_log(f"\n剧本已保存: {script_path}")
        return script_path

    def synthesize_only(self, script_path: str) -> Dict[str, str]:
        """仅执行语音合成（需要已有剧本）"""
        self._cancelled = False
        script = load_json(script_path)
        script = self.voice_assigner.assign_voices(script)
        self._emit_script(script)
        audio_segments = self._synthesize_script(script)
        self._emit_log(f"合成完成，共 {len(audio_segments)} 个音频片段")
        return audio_segments

    def mix_only(
        self,
        script_path: str,
        audio_segments: Dict[str, str],
        output_path: str,
    ) -> str:
        """仅执行混音"""
        script = load_json(script_path)
        self._emit_progress(5, "混音导出", 0, 1, "正在混音...")
        result = self.mixer.mix_script(script, audio_segments, output_path)
        self._emit_progress(5, "混音导出", 1, 1, "导出完成")
        self._emit_finished(output_path)
        return result
