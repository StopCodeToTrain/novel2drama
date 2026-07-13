"""小说转广播剧 - CLI 入口"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import NovelToDramaPipeline
from config import OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(
        description="小说转广播剧 - 将中文小说自动转换为多角色广播剧",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 启动 GUI 界面
  python main.py gui

  # 完整流水线：小说 -> 广播剧
  python main.py generate novel.txt

  # 指定输出路径
  python main.py generate novel.txt -o output/drama.wav

  # 仅生成剧本（不合成语音）
  python main.py analyze novel.txt -s output/script.json

  # 仅合成语音（需要已有剧本）
  python main.py synthesize output/script.json

  # 仅混音（需要剧本和音频片段）
  python main.py mix output/script.json -o output/drama.wav

  # 查看可用音色
  python main.py voices
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # gui - 启动图形界面
    subparsers.add_parser("gui", help="启动图形界面")

    # generate - 完整流水线
    gen_parser = subparsers.add_parser("generate", help="完整流水线：小说文本 -> 广播剧音频")
    gen_parser.add_argument("input", help="输入小说文本文件路径")
    gen_parser.add_argument("-o", "--output", help="输出音频路径（默认 output/标题.wav）")
    gen_parser.add_argument("-s", "--script", help="剧本 JSON 保存路径")
    gen_parser.add_argument("--no-cache", action="store_true", help="不使用缓存")

    # analyze - 仅文本分析
    ana_parser = subparsers.add_parser("analyze", help="仅执行文本分析，生成剧本 JSON")
    ana_parser.add_argument("input", help="输入小说文本文件路径")
    ana_parser.add_argument("-s", "--script", help="剧本 JSON 保存路径")
    ana_parser.add_argument("--no-cache", action="store_true", help="不使用缓存")

    # synthesize - 仅语音合成
    syn_parser = subparsers.add_parser("synthesize", help="仅执行语音合成（需要已有剧本）")
    syn_parser.add_argument("script", help="剧本 JSON 文件路径")
    syn_parser.add_argument("--no-cache", action="store_true", help="不使用缓存")

    # mix - 仅混音
    mix_parser = subparsers.add_parser("mix", help="仅执行混音（需要剧本和音频片段）")
    mix_parser.add_argument("script", help="剧本 JSON 文件路径")
    mix_parser.add_argument("-o", "--output", required=True, help="输出音频路径")
    mix_parser.add_argument("--no-cache", action="store_true", help="不使用缓存")

    # voices - 查看可用音色
    subparsers.add_parser("voices", help="查看可用的预设参考音色")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    use_cache = not getattr(args, "no_cache", False)

    if args.command == "gui":
        from gui import main as gui_main
        gui_main()

    elif args.command == "generate":
        pipeline = NovelToDramaPipeline(use_cache=use_cache)
        pipeline.run(
            input_path=args.input,
            output_path=args.output,
            script_path=args.script,
        )

    elif args.command == "analyze":
        pipeline = NovelToDramaPipeline(use_cache=use_cache)
        pipeline.analyze_only(args.input, args.script)

    elif args.command == "synthesize":
        pipeline = NovelToDramaPipeline(use_cache=use_cache)
        pipeline.synthesize_only(args.script)

    elif args.command == "mix":
        pipeline = NovelToDramaPipeline(use_cache=use_cache)
        # mix_only 需要音频片段，这里简化为从缓存加载
        print("注意: mix 命令需要已合成的音频片段")
        print("请先运行 synthesize 命令生成音频片段")
        # 实际使用时，可以从 TTS 输出目录加载所有片段
        # 这里仅作为接口预留
        sys.exit(1)

    elif args.command == "voices":
        from voice_design.voice_assigner import VoiceAssigner
        assigner = VoiceAssigner()
        voices = assigner.list_available_voices()
        print("\n可用预设音色:")
        print("-" * 60)
        for v in voices:
            status = "✓ 可用" if v["available"] else "✗ 未找到"
            print(f"  {v['key']:20s} {status}")
            print(f"  {'':20s} {v['description']}")
            print(f"  {'':20s} 路径: {v['path']}")
            print()
        if not any(v["available"] for v in voices):
            print(f"\n请将参考音频文件放在: {assigner.voices_dir}")
            print("文件名参考上述列表中的 key + .wav")


if __name__ == "__main__":
    main()
