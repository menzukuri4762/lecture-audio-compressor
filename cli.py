import os
import sys
import argparse
from compressor import (
    probe_file,
    calculate_optimal_bitrate,
    estimate_output_size_mb,
    AudioCompressor,
    format_duration,
    format_size
)

def main():
    parser = argparse.ArgumentParser(description="講義音声を100MB未満のAI向けMP3に変換するCLIツール")
    parser.add_argument("inputs", nargs="+", help="入力ファイルパス（複数指定可）")
    parser.add_argument("-t", "--target-mb", type=float, default=95.0, help="目標上限サイズ (MB) [デフォルト: 95.0]")
    parser.add_argument("-m", "--mode", choices=["ai_voice", "fit_target", "compact"], default="ai_voice", help="圧縮モード [ai_voice / fit_target / compact]")
    parser.add_argument("-o", "--output-dir", default=None, help="保存先ディレクトリ [デフォルト: 入力ファイルと同じ]")
    parser.add_argument("--no-optimize", action="store_true", help="AI向け音声強調フィルタ（ノイズカット・ノーマライズ）を無効化")

    args = parser.parse_args()

    compressor = AudioCompressor()

    for idx, input_path in enumerate(args.inputs):
        if not os.path.exists(input_path):
            print(f"[スキップ] ファイルが存在しません: {input_path}")
            continue

        print(f"\n==========================================")
        print(f"[{idx+1}/{len(args.inputs)}] 解析中: {os.path.basename(input_path)}")
        try:
            info = probe_file(input_path)
        except Exception as e:
            print(f"解析失敗: {e}")
            continue

        if not info.has_audio:
            print("エラー: 音声トラックが見つかりません。")
            continue

        print(f"  - 再生時間: {format_duration(info.duration)}")
        print(f"  - 元サイズ: {format_size(info.file_size)}")

        bitrate = calculate_optimal_bitrate(info.duration, target_mb=args.target_mb, mode=args.mode)
        est_mb = estimate_output_size_mb(info.duration, bitrate)
        print(f"  - 目標サイズ上限: {args.target_mb:.1f} MB")
        print(f"  - 適用ビットレート: {bitrate} kbps (モノラル)")
        print(f"  - 変換後予想サイズ: 約 {est_mb:.1f} MB")

        # Determine output path
        base_name, _ = os.path.splitext(os.path.basename(input_path))
        out_dir = args.output_dir if args.output_dir else os.path.dirname(os.path.abspath(input_path))
        out_path = os.path.join(out_dir, f"{base_name}_compressed.mp3")

        print(f"  - 出力先: {out_path}")
        print("変換中...")

        def progress_cb(pct, text):
            sys.stdout.write(f"\r  進捗: {text}    ")
            sys.stdout.flush()

        ai_opt = not args.no_optimize
        success = compressor.convert(
            input_path=input_path,
            output_path=out_path,
            duration_sec=info.duration,
            bitrate_kbps=bitrate,
            ai_optimize=ai_opt,
            progress_callback=progress_cb
        )

        sys.stdout.write("\n")
        if success:
            act_size = os.path.getsize(out_path)
            print(f"変換完了: {format_size(act_size)} (目標 {args.target_mb}MB 以内)\n")
        else:
            print("変換に失敗または中止されました。\n")

if __name__ == "__main__":
    main()
