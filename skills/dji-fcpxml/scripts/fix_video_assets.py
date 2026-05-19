#!/usr/bin/env python3
"""
既存 FCPXML 1.13 の video asset / asset-clip を実ファイル準拠に書き換える。

主な変換:
1. format を 29.97fps 単一（r1 = frameDuration="1001/30000s"）に統合
2. 各 video asset の start を実ファイルの camera TC (DFフレーム×1001/30000) に
3. 各 video asset の duration を実フレーム数 × 1001/30000 に
4. 各 video asset-clip の start を (asset.start + in-point_frames × 1001) / 30000s に
5. タイムライン全体（asset-clip offset/duration、sequence duration、gap duration、marker等）を
   /30000s denominator に変換し 29.97 frame-alignment を担保（元が /30s なら numerator × 1001）

前提:
- XML の video asset id が "v_NNNN" 形式（例: v_0013）
- video ファイル名に対応する clip_id（NNNN）が含まれる（例: DJI_20260405215615_0013_D.MP4）
- ffprobe が利用可能

使い方:
    python3 fix_video_assets.py --xml /path/to/skeleton.fcpxml --video-dir /path/to/Video/
    python3 fix_video_assets.py --xml ... --video-dir ... --no-backup

出力:
    {xml}.bak にバックアップを取り、{xml} を in-place で書き換える。
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def tc_to_df_frames(tc: str) -> int:
    """29.97 DF timecode (`HH:MM:SS;FF`) をフレーム数に変換する。

    DJI OP3 は 29.97fps で録画すると必ず DF（セミコロン区切り）で書き込む。
    NDF（コロン区切り）が来たら設計外なので fail loud。静かに DF とみなすと
    drop計算が誤適用され、TC がズレた asset を生成してしまう。
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
            f"If this is NOT DJI OP3 material, handle NDF→frames conversion explicitly "
            f"(at 29.97, NDF frame count = h*108000 + m*1800 + s*30 + f without drops)."
        )
    total_min = h * 60 + mn
    ndf = (h * 3600 + mn * 60 + s) * 30 + f
    drops = (total_min - total_min // 10) * 2
    return ndf - drops


def probe(path: Path) -> tuple[int, str, str]:
    """return (nb_frames, timecode, r_frame_rate)"""
    r = subprocess.run(
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
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {path}: {r.stderr}")
    info = {}
    for line in r.stdout.strip().split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()

    # fail fast: 欠損メタデータを黙って 0/空文字で返すと duration="0/30000s" を
    # XML に書き込んでしまい、FCP 側で壊れた asset になる
    nb_str = info.get("nb_frames", "")
    if not nb_str or nb_str in ("0", "N/A"):
        raise RuntimeError(
            f"{path.name}: ffprobe returned nb_frames={nb_str!r}. "
            f"File may be corrupt, truncated, or a container that doesn't expose frame count."
        )
    tc = info.get("TAG:timecode", "")
    if not tc:
        raise RuntimeError(
            f"{path.name}: no timecode tag in video stream. "
            f"DJI OP3 material should always have a recording TC. Verify source."
        )
    fr = info.get("r_frame_rate", "")
    return int(nb_str), tc, fr


def build_clip_map(video_dir: Path) -> dict:
    """video_dir 内の DJI_*.MP4 をスキャンし、{clip_id: (start_numerator, frames)} を返す"""
    m = {}
    for p in sorted(video_dir.glob("DJI_*.MP4")):
        if p.name.startswith("._"):
            continue
        mm = re.search(r"_(\d{4})_D\.MP4$", p.name, re.IGNORECASE)
        if not mm:
            continue
        cid = mm.group(1)
        try:
            nb, tc, fr = probe(p)
            if fr != "30000/1001":
                print(
                    f"# WARN {p.name}: fr={fr} (expected 30000/1001)", file=sys.stderr
                )
            if not tc:
                print(f"# WARN {p.name}: no timecode", file=sys.stderr)
                continue
            df = tc_to_df_frames(tc)
            m[cid] = (df * 1001, nb)
        except Exception as e:
            print(f"# ERR {p.name}: {e}", file=sys.stderr)
    return m


def rewrite(xml: str, clip_map: dict) -> str:
    # Step 1: format を 29.97 単一化
    xml = re.sub(
        r'<format id="r1" name="FFVideoFormat[^"]*" frameDuration="100/3000s"',
        '<format id="r1" name="FFVideoFormat3840x2160p2997" frameDuration="1001/30000s"',
        xml,
    )
    # 既存 r2 (29.97) があれば削除（r1 に統合したため不要）
    xml = re.sub(
        r'\s*<format id="r2" name="FFVideoFormat[^"]*" frameDuration="1001/30000s"[^/]*/>',
        "",
        xml,
    )

    # Step 2-3: video asset の start / duration / format を実ファイル準拠に
    def fix_asset(m):
        cid = m.group(1)
        if cid not in clip_map:
            return m.group(0)
        start_num, frames = clip_map[cid]
        dur_num = frames * 1001
        line = m.group(0)
        line = re.sub(r'\sstart="[^"]*"', f' start="{start_num}/30000s"', line, count=1)
        line = re.sub(
            r'\sduration="[^"]*"', f' duration="{dur_num}/30000s"', line, count=1
        )
        line = re.sub(r'\sformat="r2"', ' format="r1"', line)
        return line

    xml = re.sub(r'<asset id="v_(\d+)"[^>]*>', fix_asset, xml)

    # Step 4-5: タイムライン変換は行単位で行う（<asset id=...> 宣言行は除外）
    out_lines = []
    for line in xml.split("\n"):
        if "<asset id=" in line:
            out_lines.append(line)
            continue

        # まず /30s → /30000s（numerator × 1001）に変換
        line = re.sub(
            r'"(\d+)/30s"', lambda mm: f'"{int(mm.group(1)) * 1001}/30000s"', line
        )

        # video asset-clip の start は asset.start + (in-point) の絶対TCで書く。
        # 再実行時の二重加算を防ぐため、現在値が既に asset.start 以上なら
        # 「絶対TCに変換済み」とみなしてスキップ。DJI TC は常に大きな値
        # （数時間〜）なので、in-point 相対値（0〜asset.duration frames × 1001）と
        # は明確に差がつくため、この判定で誤判定は起きない。
        mv = re.search(r'<asset-clip [^>]*ref="v_(\d+)"', line)
        if mv:
            cid = mv.group(1)
            if cid in clip_map:
                asset_start = clip_map[cid][0]

                def _maybe_add(mm, _asset_start=asset_start):
                    cur = int(mm.group(1))
                    if cur >= _asset_start:
                        return mm.group(0)  # idempotent: already absolute
                    return f'start="{_asset_start + cur}/30000s"'

                line = re.sub(r'start="(\d+)/30000s"', _maybe_add, line)
        out_lines.append(line)
    return "\n".join(out_lines)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--xml", required=True, help="path to fcpxml to rewrite in-place")
    ap.add_argument("--video-dir", required=True, help="directory containing DJI_*.MP4")
    ap.add_argument("--no-backup", action="store_true", help="skip writing .bak")
    args = ap.parse_args()

    xml_path = Path(args.xml).resolve()
    video_dir = Path(args.video_dir).resolve()
    if not xml_path.is_file():
        ap.error(f"xml not found: {xml_path}")
    if not video_dir.is_dir():
        ap.error(f"video dir not found: {video_dir}")
    if xml_path.suffix not in {".fcpxml", ".xml"}:
        ap.error(f"refusing to rewrite unexpected extension: {xml_path}")

    clip_map = build_clip_map(video_dir)
    print(f"found {len(clip_map)} DJI clips in {video_dir}", file=sys.stderr)

    original = xml_path.read_text()

    # Pre-flight: XML が整合しているか、書き込み前に検証。
    # Pre-flight で検出する異常:
    #   (1) <asset id="v_NNNN"> が宣言されているが video_dir に実ファイルが無い
    #   (2) <asset-clip ref="v_NNNN"> が spine にあるが <asset> として宣言されていない (dangling ref)
    #   (3) /30000s denominator の numerator が 1001 の倍数でない (off-frame)
    # (1)(2) はいずれも「部分的に stale な XML」を静かに正本化することになる。
    # (3) は 29.97fps の frame boundary 違反で、FCP が "item is not on an edit
    #     frame boundary" を警告する。手書きで N × 1001 を計算するとき、特に
    #     千分位で下一桁の繰り上がりを見落とす事故が多い (3480 × 1001 を 3483450
    #     と書く等)。書き込み前に弾かないと、FCP に取り込んでから気づくことになる。
    # いずれも rerunnable tool の前提では危険なので fail。
    xml_v_declared = set(re.findall(r'<asset id="v_(\d+)"', original))
    xml_v_refs = set(re.findall(r'<asset-clip [^>]*ref="v_(\d+)"', original))

    missing_files = sorted(xml_v_declared - set(clip_map))
    dangling_refs = sorted(xml_v_refs - xml_v_declared)

    off_frame = []
    for mm in re.finditer(r'(\w+)="(\d+)/30000s"', original):
        attr, num = mm.group(1), int(mm.group(2))
        if num % 1001 != 0:
            line_no = original[: mm.start()].count("\n") + 1
            nearest_lo = (num // 1001) * 1001
            nearest_hi = nearest_lo + 1001
            off_frame.append((line_no, attr, num, nearest_lo, nearest_hi))

    errors = []
    if missing_files:
        errors.append(
            f"{len(missing_files)} video asset(s) declared in XML but no matching file in {video_dir}:\n  "
            + "\n  ".join(f"v_{cid}" for cid in missing_files)
        )
    if dangling_refs:
        errors.append(
            f"{len(dangling_refs)} asset-clip ref(s) point to undeclared video asset(s):\n  "
            + "\n  ".join(f"v_{cid}" for cid in dangling_refs)
        )
    if off_frame:
        preview_lines = [
            f"L{ln}: {a}={n}/30000s — nearest frame boundary: {lo} or {hi}"
            for ln, a, n, lo, hi in off_frame[:10]
        ]
        suffix = (
            f"\n  ... and {len(off_frame) - 10} more" if len(off_frame) > 10 else ""
        )
        errors.append(
            f"{len(off_frame)} off-frame value(s) — 29.97fps requires numerator to be N × 1001:\n  "
            + "\n  ".join(preview_lines)
            + suffix
        )
    if errors:
        print(
            "ERROR: XML is not self-consistent.\n"
            + "\n".join(errors)
            + "\nAborting without writing. Fix the source and rerun.",
            file=sys.stderr,
        )
        sys.exit(1)

    new = rewrite(original, clip_map)

    if not args.no_backup:
        bak = xml_path.with_suffix(xml_path.suffix + ".bak")
        shutil.copy2(xml_path, bak)
        print(f"backup: {bak}", file=sys.stderr)

    xml_path.write_text(new)
    print(
        f"rewritten: {xml_path} ({len(xml_v_declared)} video assets declared, "
        f"{len(xml_v_refs)} asset-clip refs)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
