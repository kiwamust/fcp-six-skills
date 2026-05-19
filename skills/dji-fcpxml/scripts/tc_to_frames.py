#!/usr/bin/env python3
"""
DJI OP3 の MP4 からカメラ内部 timecode を読み、DFフレーム数と FCPXML用 start値(/30000s分子)を出力する。

使い方:
    python3 tc_to_frames.py /path/to/DJI_xxx.MP4
    python3 tc_to_frames.py /path/to/DJI_*.MP4
    python3 tc_to_frames.py --dir /path/to/Video/

出力: タブ区切り
    clip_id  timecode  nb_frames  DF_frames  start_numerator

FCPXML の asset に <asset ... start="{start_numerator}/30000s" duration="{nb_frames*1001}/30000s">
と書く。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path


def tc_to_df_frames(tc: str) -> int:
    """29.97 DF timecode (`HH:MM:SS;FF`) をフレーム数に変換する。

    DJI OP3 は 29.97fps 録画で必ず DF（セミコロン区切り）を書き込む。
    NDF（コロン区切り）が来たら設計外で、静かに DF とみなすと drops を誤適用し
    TC がズレた asset を生成してしまうため fail loud にする。

    DF 公式:
        NDF_frames = h*108000 + m*1800 + s*30 + f
        drops      = (total_min - total_min // 10) * 2
        DF_frames  = NDF_frames - drops
    """
    m = re.match(r"(\d+):(\d+):(\d+)([;:])(\d+)", tc)
    if not m:
        raise ValueError(f"invalid tc format: {tc!r}")
    h, mn, s, sep, f = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    h, mn, s, f = int(h), int(mn), int(s), int(f)
    if sep != ";":
        raise ValueError(
            f"timecode {tc!r} uses NDF separator ':' — "
            f"expected DF ';' for 29.97fps DJI source. "
            f"If this is NOT DJI OP3 material, handle NDF→frames conversion explicitly."
        )
    total_min = h * 60 + mn
    ndf = (h * 3600 + mn * 60 + s) * 30 + f
    drops = (total_min - total_min // 10) * 2
    return ndf - drops


def probe_mp4(path: Path) -> dict:
    """ffprobe で video stream の必要情報を取得"""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_frames,r_frame_rate",
            "-show_entries",
            "stream_tags=timecode",
            "-of",
            "default=nw=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr}")

    info = {}
    for line in result.stdout.strip().split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


def extract_clip_id(filename: str) -> str:
    """DJI_20260405215615_0013_D.MP4 → 0013"""
    m = re.search(r"_(\d{4})_D\.MP4$", filename, re.IGNORECASE)
    return m.group(1) if m else filename


def process(paths: list[Path]) -> int:
    """1行でも処理できなければ非ゼロを返す（下流スクリプトが安全側に倒せるように）"""
    print("clip_id\ttimecode\tnb_frames\tDF_frames\tstart_numerator")
    errors = 0
    for p in paths:
        try:
            info = probe_mp4(p)
            tc = info.get("TAG:timecode", "")
            nb_str = info.get("nb_frames", "")
            fr = info.get("r_frame_rate", "")

            # fail fast: 欠損メタデータで 0 や空値を黙って採用しない。
            # duration="0/30000s" を書き込むと壊れた asset が生成される
            if not nb_str or nb_str in ("0", "N/A"):
                raise RuntimeError(
                    f"ffprobe returned nb_frames={nb_str!r}. "
                    "File may be corrupt or container doesn't expose frame count."
                )
            if not tc:
                raise RuntimeError(
                    "no timecode tag in video stream. "
                    "DJI OP3 material should always have a recording TC."
                )
            if fr != "30000/1001":
                print(
                    f"# WARN {p.name}: r_frame_rate={fr} (expected 30000/1001)",
                    file=sys.stderr,
                )

            df = tc_to_df_frames(tc)
            start_num = df * 1001
            cid = extract_clip_id(p.name)
            print(f"{cid}\t{tc}\t{int(nb_str)}\t{df}\t{start_num}")
        except Exception as e:
            errors += 1
            print(f"# ERR {p.name}: {e}", file=sys.stderr)
    return 1 if errors else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", help="MP4 file paths")
    ap.add_argument("--dir", help="Process all DJI_*.MP4 under this directory")
    args = ap.parse_args()

    paths: list[Path] = []
    if args.dir:
        d = Path(args.dir)
        paths.extend(sorted(d.glob("DJI_*.MP4")))
    paths.extend(Path(f) for f in args.files)

    if not paths:
        ap.error("no input files. provide files or --dir")

    sys.exit(process(paths))


if __name__ == "__main__":
    main()
