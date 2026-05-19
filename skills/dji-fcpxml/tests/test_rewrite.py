#!/usr/bin/env python3
"""
fix_video_assets.py の rewrite() と main() のプリフライトを直接検証する。
ffprobe 非依存。clip_map を手で渡して純粋な文字列変換の不変条件だけを見る。

実行:
    python3 tests/test_rewrite.py

全 PASS で exit 0、1件でも FAIL があれば exit 1。
"""
import sys
import subprocess
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from fix_video_assets import rewrite  # noqa: E402


# ダミーの clip_map。v_0013 の camera TC 相当を入れる。
# asset.start_numerator, nb_frames
CLIP_MAP = {
    "0013": (2369204838, 423),  # 21:56:13;18 DF = 2366838 frames × 1001
    "0034": (1039151113, 3884),
}


FAILED = []


def assert_contains(name: str, haystack: str, needle: str):
    if needle in haystack:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name}: expected {needle!r} in output")
        FAILED.append(name)


def assert_not_contains(name: str, haystack: str, needle: str):
    if needle not in haystack:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name}: did not expect {needle!r} in output")
        FAILED.append(name)


# -----------------------------------------------------------------------------
# Case 1: skeleton (30fps 前提で手書きされたXML) → 29.97 準拠に変換
# -----------------------------------------------------------------------------
SKELETON = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.13">
  <resources>
    <format id="r1" name="FFVideoFormat3840x2160p30" frameDuration="100/3000s" width="3840" height="2160" colorSpace="1-1-1 (Rec. 709)"/>
    <asset id="v_0013" name="Clip 0013" start="0/1s" duration="423/30s" hasAudio="1" hasVideo="1" format="r1" audioSources="1" audioChannels="2" audioRate="48000">
      <media-rep kind="original-media" src="file:///tmp/DJI_13.MP4"/>
    </asset>
  </resources>
  <event name="t"><project name="t">
    <sequence format="r1" duration="300/30s" tcStart="0/1s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
      <spine><gap name="T" duration="300/30s" start="0/1s">
        <asset-clip ref="v_0013" lane="1" offset="0/30s" name="A" duration="30/30s" start="0/30s"/>
        <asset-clip ref="v_0013" lane="1" offset="30/30s" name="B" duration="60/30s" start="120/30s"/>
      </gap></spine>
    </sequence>
  </project></event>
</fcpxml>
"""


def test_skeleton_conversion():
    print("[1] skeleton → 29.97 準拠")
    out = rewrite(SKELETON, CLIP_MAP)

    # format は 29.97 に昇格
    assert_contains("format r1 29.97", out, 'frameDuration="1001/30000s"')
    assert_not_contains("format 30fps 消滅", out, 'frameDuration="100/3000s"')

    # asset.start = camera TC、duration = frames*1001
    assert_contains("asset.start = TC", out, 'start="2369204838/30000s"')
    assert_contains("asset.duration = N*1001", out, 'duration="423423/30000s"')

    # asset-clip A (start=0/30s) → asset.start + 0 = asset.start
    assert_contains(
        "clip A start = asset.start",
        out,
        'name="A" duration="30030/30000s" start="2369204838/30000s"',
    )
    # asset-clip B (start=120/30s) → asset.start + 120*1001 = 2369204838 + 120120 = 2369324958
    assert_contains(
        "clip B start = asset.start + 120 frames",
        out,
        'name="B" duration="60060/30000s" start="2369324958/30000s"',
    )


# -----------------------------------------------------------------------------
# Case 2: idempotency (skeleton を2回rewriteしても同じ)
# -----------------------------------------------------------------------------
def test_idempotent():
    print("[2] idempotency")
    once = rewrite(SKELETON, CLIP_MAP)
    twice = rewrite(once, CLIP_MAP)
    if once == twice:
        print("  PASS rewrite(rewrite(x)) == rewrite(x)")
    else:
        print("  FAIL NOT idempotent")
        # diff out first difference
        for i, (a, b) in enumerate(zip(once, twice)):
            if a != b:
                print(f"    diff at char {i}: {once[i:i+80]!r} vs {twice[i:i+80]!r}")
                break
        FAILED.append("idempotent")


# -----------------------------------------------------------------------------
# Case 3: mixed input — skeleton parts + FCP-export fragment で rerun。
# FCP export 由来の /5000s 絶対値は触らず、skeleton /30s は変換される
# -----------------------------------------------------------------------------
MIXED = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.13">
  <resources>
    <format id="r1" name="FFVideoFormat3840x2160p30" frameDuration="100/3000s" width="3840" height="2160" colorSpace="1-1-1 (Rec. 709)"/>
    <asset id="v_0013" name="Clip 0013" start="0/1s" duration="423/30s" hasAudio="1" hasVideo="1" format="r1" audioSources="1" audioChannels="2" audioRate="48000">
      <media-rep kind="original-media" src="file:///tmp/DJI_13.MP4"/>
    </asset>
  </resources>
  <event name="t"><project name="t">
    <sequence format="r1" duration="300/30s" tcStart="0/1s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
      <spine><gap name="T" duration="300/30s" start="0/1s">
        <asset-clip ref="v_0013" lane="1" offset="0/30s" name="Skel" duration="30/30s" start="0/30s"/>
        <asset-clip ref="v_0013" lane="1" offset="30/30s" name="FCPexp" duration="243243/30000s" start="394885491/5000s"/>
      </gap></spine>
    </sequence>
  </project></event>
</fcpxml>
"""


def test_mixed_input():
    print("[3] mixed (skeleton + FCP-export) rerun")
    out = rewrite(MIXED, CLIP_MAP)
    # skeleton 由来の "Skel" は変換される
    assert_contains(
        "skeleton 部分は変換",
        out,
        'name="Skel" duration="30030/30000s" start="2369204838/30000s"',
    )
    # FCP-export 由来の "FCPexp" は触らない（/5000s 形式で絶対値として保持）
    assert_contains("FCP export 部分は保持", out, 'start="394885491/5000s"')


# -----------------------------------------------------------------------------
# Case 4: pre-flight guard（CLI 経由で確認）
# -----------------------------------------------------------------------------
SCRIPT = SCRIPTS / "fix_video_assets.py"


def run_cli(xml_content: str, video_dir: Path) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".fcpxml", delete=False) as f:
        f.write(xml_content)
        path = f.name
    try:
        r = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--xml",
                path,
                "--video-dir",
                str(video_dir),
                "--no-backup",
            ],
            capture_output=True,
            text=True,
        )
        return r.returncode, r.stderr
    finally:
        Path(path).unlink(missing_ok=True)


def test_preflight_dangling_ref():
    print("[4] pre-flight: dangling asset-clip ref")
    # v_0013 は declared だが v_9999 は未宣言の ref
    xml = SKELETON.replace(
        '<asset-clip ref="v_0013" lane="1" offset="30/30s" name="B"',
        '<asset-clip ref="v_9999" lane="1" offset="30/30s" name="Dangling"',
    )
    # pre-flight は XML 構造チェックなので video_dir は空 tempdir でよい。
    # build_clip_map は DJI_*.MP4 を scan するが、空なら空 dict を返すだけ。
    # ffprobe も呼ばれない（該当ファイルが無いので）。
    with tempfile.TemporaryDirectory() as td:
        code, err = run_cli(xml, Path(td))
    if code != 0 and "undeclared" in err and "v_9999" in err:
        print(f"  PASS exit={code}, mentions v_9999 as undeclared")
    else:
        print(f"  FAIL: code={code}, stderr={err[:200]}")
        FAILED.append("dangling_ref")


def test_preflight_missing_file():
    print("[5] pre-flight: declared asset with no matching file")
    xml = SKELETON.replace(
        '<asset id="v_0013"',
        '<asset id="v_8888"',
    ).replace('ref="v_0013"', 'ref="v_8888"')
    with tempfile.TemporaryDirectory() as td:
        code, err = run_cli(xml, Path(td))
    if code != 0 and "v_8888" in err:
        print(f"  PASS exit={code}, mentions v_8888 in stderr")
    else:
        print(f"  FAIL: code={code}, stderr={err[:200]}")
        FAILED.append("missing_file")


# -----------------------------------------------------------------------------
# Case 6: pre-flight — off-frame /30000s value (numerator not a multiple of 1001)
#
# 29.97fps では全ての /30000s 値で numerator が 1001 の倍数である必要がある。
# 手書きで N × 1001 を計算するときの typo (例: 3480 × 1001 = 3483480 を 3483450
# と書く) は FCP で "item is not on an edit frame boundary" を警告する。
# XML は既に 29.97 準拠（/30000s形式）で書かれている前提の XML を用意して、
# 意図的に 30 ずれの値を混入させ、書き込み前に pre-flight が弾くことを確認する。
# -----------------------------------------------------------------------------
OFF_FRAME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.13">
  <resources>
    <format id="r1" name="FFVideoFormat3840x2160p2997" frameDuration="1001/30000s" width="3840" height="2160" colorSpace="1-1-1 (Rec. 709)"/>
    <asset id="v_0013" name="Clip 0013" start="2369204838/30000s" duration="423423/30000s" hasAudio="1" hasVideo="1" format="r1" audioSources="1" audioChannels="2" audioRate="48000">
      <media-rep kind="original-media" src="file:///tmp/DJI_13.MP4"/>
    </asset>
  </resources>
  <event name="t"><project name="t">
    <sequence format="r1" duration="300300/30000s" tcStart="0/1s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
      <spine><gap name="T" duration="300300/30000s" start="0/1s">
        <asset-clip ref="v_0013" lane="1" offset="3483450/30000s" name="BAD" duration="30030/30000s" start="2369204838/30000s"/>
      </gap></spine>
    </sequence>
  </project></event>
</fcpxml>
"""


def test_preflight_off_frame():
    print("[6] pre-flight: off-frame /30000s numerator (not multiple of 1001)")
    with tempfile.TemporaryDirectory() as td:
        code, err = run_cli(OFF_FRAME_XML, Path(td))
    # 3483450 は 3480 × 1001 = 3483480 のつもりで書かれた典型 typo
    if code != 0 and "off-frame" in err and "3483450" in err:
        print(f"  PASS exit={code}, mentions off-frame value 3483450")
    else:
        print(f"  FAIL: code={code}, stderr={err[:300]}")
        FAILED.append("off_frame")


# -----------------------------------------------------------------------------
def main():
    test_skeleton_conversion()
    test_idempotent()
    test_mixed_input()
    test_preflight_dangling_ref()
    test_preflight_missing_file()
    test_preflight_off_frame()

    print()
    if FAILED:
        print(f"FAILED: {len(FAILED)} test(s): {FAILED}")
        sys.exit(1)
    print("ALL PASSED")


if __name__ == "__main__":
    main()
