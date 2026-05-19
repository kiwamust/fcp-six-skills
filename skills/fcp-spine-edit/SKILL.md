---
name: fcp-spine-edit
description: >-
  FCPXML の spine 構造を一括編集する。asset-clip の duration / offset を kindベース
  (long/standard/short/peak) で書き換え、offset を累積で再計算し、sequence duration
  を整合させる。clip削除があった場合の元clip番号との diff特定、idempotent な再構築
  (既存 title/video を全削除 → 新 spine で再注入)、resource ID の動的取得を含む。
  projection-ready 化 (リードイン/トレイル黒画面の `<gap>` 挿入、 80% title-safe zone への
  Position シフト、 全 asset-clip offset の一括シフト) も含む。
  「spine編集」「duration一括変更」「尺リサイズ」「メリハリ」「kindベース」
  「offset再計算」「clip削除diff」「idempotent rebuild」「sequence duration」
  「カットの長短」「テンポ調整」「29.97 frame整合」「projection-ready」「黒画面」
  「リードイン」「トレイルアウト」「title-safe zone」「投影」「gap」等で発動。
  overlay系 (字幕・画像) は fcp-titles / fcp-image-overlay、 基本仕様は dji-fcpxml、
  library運用は fcp-library-ops。
---

# fcp-spine-edit — FCPXML spine の構造編集

`<spine>` 内の `<asset-clip>` 列に対して、duration の一括書き換え、offset 累積再計算、シーン構成の再構築を行う。動画素材refine（尺の長短メリハリ・clip選別）の中核となるスキル。

## 核となる教訓

- **duration を変えると offset の累積再計算が必須**（後続clipは前clipのdurationに依存）
- **sequence duration も合わせて更新**（spine全体の合計）
- **29.97fps frame整合は `1001 × N / 30000s` 形式**（`/30000s` denominator統一）
- **resource ID は動的取得**（FCPがclip削除等で再番号付けする）
- **idempotent rebuild が必須**（既存 title/video を全削除→新規注入で再現性を確保）

## 1. kindベース尺リサイズの構造

各 clip に**重要度ラベル (kind)** を割り当て、それに応じた duration を自動付与する。

### 標準 kind 定義

| kind       | フレーム | 30000s denom | 秒      | 適用先                                      |
| ---------- | -------- | ------------ | ------- | ------------------------------------------- |
| `long`     | 120      | 120120       | 4.004s  | シーンの最初・最後 (場所提示・締め)         |
| `standard` | 75       | 75075        | 2.5025s | シーンの2番目・最後から2番目 (字幕読み時間) |
| `short`    | 45       | 45045        | 1.5015s | シーン中間 (テンポUP) / 字幕なしエリア      |
| `peak`     | 180      | 180180       | 6.006s  | 重要ピーク (頂上・夕景・代表カット)         |

29.97fps frame整合: `frames × 1001 / 30000s` の形式で書く。**整数 frame数 × 1001** が必須。

### kind 決定ルール (Z パターン)

```python
def determine_kind(clip_idx_1based: int, scene_plan, peak_clips):
    if clip_idx_1based in peak_clips:
        return KIND_PEAK
    for _, start, end in scene_plan:
        if start <= clip_idx_1based <= end:
            # シーン両端 → long
            if clip_idx_1based == start or clip_idx_1based == end:
                return KIND_LONG
            # 端から2番目 → standard (字幕読み時間)
            if clip_idx_1based == start + 1 or clip_idx_1based == end - 1:
                return KIND_STANDARD
            # それ以外 → short (テンポUP)
            return KIND_SHORT
    return KIND_SHORT  # 字幕なしエリア
```

### 試算式

```
total_seconds = (long数 * 120 + standard数 * 75 + short数 * 45 + peak数 * 180) * 1001 / 30000
```

例（180clip、12シーン）:

- long 24 + standard 24 + short 127 + peak 5
- = (24×120 + 24×75 + 127×45 + 5×180) × 1001 / 30000
- = (2880 + 1800 + 5715 + 900) × 1001 / 30000
- = 11295 × 1001 / 30000 ≈ **6:17**

## 2. offset 累積再計算

asset-clip の `offset` 属性は spine 上の絶対時刻。各clipの duration を変更したら、それ以降のすべての offset を再計算する。

```python
cumulative_frames = 0
for clip_idx, asset_clip_match in enumerate(matches):
    kind = determine_kind(clip_idx + 1)
    new_offset = f"{cumulative_frames * 1001}/30000s"
    new_duration = f"{kind.frames * 1001}/30000s"

    # 元タグの offset / duration を新値に置換
    new_open_tag = re.sub(
        r'offset="[^"]+"', f'offset="{new_offset}"',
        re.sub(r'duration="[^"]+"', f'duration="{new_duration}"', asset_clip_match.group(0)),
    )
    # spine内の該当位置を置換 (後ろから処理してインデックスずれ回避)
    cumulative_frames += kind.frames

# sequence duration も更新
total_30000s = f"{cumulative_frames * 1001}/30000s"
content = re.sub(
    r'(<sequence\s+format="r1"\s+duration=")[^"]+(")',
    rf'\g<1>{total_30000s}\g<2>',
    content, count=1,
)
```

### 重要: 後ろから処理する

文字列インデックスがずれないよう、**spine内の置換は後ろから**行う:

```python
insertions.sort(key=lambda x: x[0], reverse=True)
for pos, replacement in insertions:
    content = content[:pos] + replacement + content[pos:]
```

## 3. clip削除 diff の特定

ユーザーがFCPで clipを削除して re-export した場合、元の clip番号が**ずれる**。SCENE_PLAN を新clip番号に再マッピングする必要がある。

### 診断ロジック

順序保持の前提で、元 vid列 と現在 vid列 を比較:

```python
def diff_deleted(original_vids, current_vids):
    """順序保持で削除された元clip番号を特定"""
    i_orig = 0
    i_curr = 0
    deleted = []
    shifted = {}  # 元clip# → 新clip#

    while i_orig < len(original_vids):
        if i_curr < len(current_vids) and original_vids[i_orig] == current_vids[i_curr]:
            shifted[i_orig + 1] = i_curr + 1
            i_orig += 1
            i_curr += 1
        else:
            deleted.append(i_orig + 1)
            i_orig += 1

    return deleted, shifted
```

### vid 抽出

asset-clip の name 属性から:

```python
def name_to_vid(name: str) -> str | None:
    if name.startswith("Clip "):
        return name[5:].strip()       # "Clip 0010" → "0010"
    if name.startswith("DJI_"):
        parts = name.split("_")
        return parts[2] if len(parts) >= 3 else None  # "DJI_..._0019_D" → "0019"
    return None
```

### SCENE_PLAN の再マッピング

```python
# 旧 SCENE_PLAN: (sid, start_clip, end_clip, ...)
# 新 SCENE_PLAN: shifted で再マッピング

new_scene_plan = []
for sid, start, end, *rest in old_scene_plan:
    new_start = shifted.get(start)
    new_end = shifted.get(end)
    if new_start is None:
        # start が削除された場合、隣接の有効な新番号を探す
        ...
    if new_end is None:
        # end が削除された場合、シーン末尾を1つ手前にずらす
        ...
    new_scene_plan.append((sid, new_start, new_end, *rest))
```

## 4. idempotent rebuild

スクリプトを何度実行しても同じ結果になるように、**既存の title/video を全削除してから新規注入**する。

### 削除パターン

```python
# title (汎用ID対応)
TITLE_BLOCK_RE = re.compile(
    r'\s*<title\s+ref="r\d+"[^>]*>.*?</title>', re.DOTALL,
)

# 装飾 video
# ref は import/re-export で g_* → r\d+ に変わり得る。安定キーは name（運用で規約固定）。
DECORATION_VIDEO_RE = re.compile(
    r'\s*<video\b[^>]*\bname="(?:Top Bar|Bottom Bar|Glass Bar)"[^>]*(?:/>|>.*?</video>)',
    re.DOTALL,
)

# 装飾 asset（PNG/SVG 由来）
# id も r\d+ に変わり得るので、name で狙う（この例は Glass Bar）
DECORATION_ASSETS_RE = re.compile(
    r'\s*<asset\b[^>]*\bname="Glass Bar"[^>]*>.*?</asset>',
    re.DOTALL,
)

# 装飾 format
# id は環境で変わり得るので、「ネイティブPNGサイズの Undefined format」に限定して絞り込む
DECORATION_FORMATS_RE = re.compile(
    r'\s*<format\b[^>]*\bname="FFVideoFormatRateUndefined"[^>]*\bwidth="\d+"[^>]*\bheight="\d+"[^>]*colorSpace="1-13-1"[^/]*/>',
    re.DOTALL,
)
```

### main() の流れ

```python
def main():
    content = INFO_FCPXML.read_text(encoding="utf-8")

    # 1. resource ID を動的取得
    basic_title_effect_id = ...  # name="Basic Title" で取得

    # 2. 既存 overlay 系を全削除
    content = TITLE_BLOCK_RE.sub("", content)
    content = DECORATION_VIDEO_RE.sub("", content)
    content = DECORATION_ASSETS_RE.sub("", content)
    content = DECORATION_FORMATS_RE.sub("", content)

    # 3. 装飾 format/asset を resources に追加
    # 4. spine内の各 asset-clip 内に title/video を新規注入
    # 5. sequence duration を更新

    INFO_FCPXML.write_text(content, encoding="utf-8")
```

## 5. resource ID 動的取得（必須）

FCPは clip削除や再exportで resource ID を再番号付けする。固定id 書きは時間差で壊れる。

```python
import re

# Basic Title effect の id を動的取得
BASIC_TITLE_EFFECT_RE = re.compile(
    r'<effect\s+id="(r\d+)"\s+name="Basic Title"', re.DOTALL,
)

m = BASIC_TITLE_EFFECT_RE.search(content)
if not m:
    raise SystemExit("Basic Title effect not found")
basic_title_effect_id = m.group(1)
```

詳細は **fcp-titles** / **fcp-image-overlay** の動的取得セクションを参照。

## 6. spine の作業フロー

### 標準パイプライン

```
1. clip_map.tsv (元 vid列) を読み込み
2. INFO_FCPXML から現状 spine の vid列を取得
3. diff で削除 clip番号と shift マップを計算
4. SCENE_PLAN を新clip番号に再マッピング
5. 各clipに kind を割り当て
6. asset-clip duration/offset を一括書き換え
7. sequence duration を更新
8. 既存 title/video を全削除 → 新規注入
9. INFO_FCPXML を上書き保存
```

### スクリプト分離

役割を分けると保守しやすい:

- `refine_durations.py`: spine の duration / offset 一括変更（kind ベース）
- `inject_titles.py`: title / video 注入（既存 overlay を削除して再注入）
- `diagnose_deleted.py`: clip削除 diff 診断（手動 SCENE_PLAN 更新の補助）

実行順: `refine_durations.py` → `inject_titles.py`（順序を守らないと title.duration が古い計算で出る）

## 7. 既知の落とし穴

- **offset を変えずに duration だけ変える**: 後続の asset-clip が重なる/隙間が空く。**累積で再計算必須**
- **sequence duration を更新し忘れる**: spine 全体の長さがズレて FCP が混乱
- **clip 削除後に SCENE_PLAN を clip_index ベースで持つ**: shift で各シーンの境界がずれて字幕がおかしな位置に。**vid ベース** (`SCENE_PLAN_BY_VID`) で持って、実行時に resolve するのが頑健
- **resource ID 固定書き**: FCPが番号付け変えた瞬間に importエラー (feedback_fcpxml_resource_id_dynamic.md)
- **削除regex を ref="g_xxx" 固定で書く**: 既存の overlay を削除しきれず累積する。 `name="..."` ベースで識別する (feedback_fcpxml_name_based_deletion.md)
- **書き出すテキストに `&` が混じる**: import で DTD validation failed。 書き出し直前に `xml_escape()` を必ず適用 (feedback_fcpxml_xml_escape.md)
- **`/30000s` denominator を統一しない**: FCP が "item is not on an edit frame boundary" 警告を出す
- **frame整合しない**: `60000/30000s = 2.0s` と書くと 60 frames、 `60060/30000s = 2.002s` と書くと 60.06 frames。**frames × 1001** で書く
- **映像クリップの offset/duration を動かしたのに audio-only を見ない**: `lane="-1"` の BGM/ENV/SE は設計次第で「親子関係」になり得る。タイムラインの絶対時刻がズレたら、音声だけ先行/遅延する。**fcp-audio の構造前提を確認して offset を再検証**する

## 8. idempotent rebuild の防御チェックリスト

スクリプト実行ごとに「既存削除→新規注入」する設計のとき、以下を必ず満たす:

| 防御項目                                                     | 実装                                                               |
| ------------------------------------------------------------ | ------------------------------------------------------------------ |
| 削除regex は **name属性ベース**                              | `<video [^>]*\bname="(?:Top Bar\|Bottom Bar\|Glass Bar)[^"]*"...>` |
| 削除regex は **id を `r\d+` で汎用化** (refベースで書く場合) | `<title ref="r\d+"[^>]*>...</title>`                               |
| 書き込む ref は **動的取得**                                 | resourcesから name属性で識別して取得                               |
| 書き込む text/name は **escape**                             | `xml_escape()` を適用                                              |
| シーン定義は **vid ベース**                                  | `SCENE_PLAN_BY_VID` を実行時に clip indexに resolve                |
| sequence duration を更新                                     | spine 全長を再計算して `<sequence duration>` に書く                |

これらが1つでも欠けると、FCPが clip削除/再export を挟んだ瞬間に重複や壊れたXMLが累積する。

### 書き込み前ゲート（運用で効く最小セット）

1. **バックアップ**: `.fcpxmld` ならフォルダごと `cp -R`。単体 `.fcpxml` なら `.bak` を必ず作る
2. **差分確認**: `diff -u before after`（または IDE diff）で「意図しない削除」が無いことを見る
3. **DTD**: `xmllint --noout Info.fcpxml`（単体 `.fcpxml` でも同様）
4. **frame boundary**: `dji-fcpxml` の `fix_video_assets.py` の off-frame 検査と同値の思考で、spine の `/30000s` timeline 値が **`1001` の倍数**になっているかを確認（typo を事前に潰す）
5. **FCP import**: warning の有無と、該当カットの見た目（overlay の前後関係・音声位置）を確認

## 9. projection-ready 化（リードイン/トレイル黒 + 80% safe zone）

プロジェクター投影では画面端の数%が切れる + 投影機の安定化に頭出し時間が必要。 納品前に以下を仕込む:

### リードイン/トレイル黒画面

`<gap>` 要素を spine の前後に**明示的**に挿入する。 暗黙の空白 (offset > 0 の最初の clip 等) は FCP が黒として render しないことがある (silent failure)。

```xml
<spine>
    <gap name="Lead-in Black" offset="0s" start="3600s" duration="90090/30000s"/>
    <asset-clip ref="r2" offset="90090/30000s" name="Intro Slideshow" .../>
    <!-- ... 本編 ... -->
    <asset-clip ref="r150" offset="12508496/30000s" duration="194194/30000s" .../>
    <gap name="Trail Black" offset="12702690/30000s" start="3600s" duration="90090/30000s"/>
</spine>
```

- `start="3600s"` は FCP の gap 内部時間 (慣習値、 FCP 正規 export と一致)
- `duration="90090/30000s"` = 3s (90 × 1001 / 30000)
- 既存 asset-clip の offset を **すべて +3s シフト**して空きを作る
- sequence duration を **+6s** (リードイン3s + トレイル3s)

### offset 一括シフト + sequence 更新スクリプト

```python
import re
from fractions import Fraction
from pathlib import Path

DELTA = Fraction(90090, 30000)  # 3s

def parse_time(s):
    s = s.strip().rstrip("s")
    if not s:
        return Fraction(0)
    if "/" in s:
        n, d = s.split("/")
        return Fraction(int(n), int(d))
    return Fraction(int(s))

def format_time(f):
    if f == 0: return "0s"
    if f.denominator == 1: return f"{f.numerator}s"
    test = f * 30000
    if test.denominator == 1: return f"{test.numerator}/30000s"
    return f"{f.numerator}/{f.denominator}s"

# 1. spine直下 (lane属性なし) の asset-clip offset を +3s
PAT_OFFSET = re.compile(r'(<asset-clip ref="r\d+" offset=")([^"]+)(")')
def shift(m):
    return m.group(1) + format_time(parse_time(m.group(2)) + DELTA) + m.group(3)
content = PAT_OFFSET.sub(shift, content)

# 2. sequence duration +6s
PAT_SEQ = re.compile(r'(<sequence format="r1" duration=")([^"]+)(")')
def shift_seq(m):
    return m.group(1) + format_time(parse_time(m.group(2)) + DELTA * 2) + m.group(3)
content = PAT_SEQ.sub(shift_seq, content)

# 3. 明示的 <gap> を spine の前後に挿入 (Edit/Write で位置決め)
```

**重要**: regex `<asset-clip ref="r\d+" offset="..."` は spine直下のみ match する (connected clip は `<asset-clip ref="rN" lane="-1" offset="..."` で間に lane 属性が入るため)。 BGM 等の lane=-1 の asset-clip は触らない (parent's local time 基準で書かれているため、 spine offset の概念が異なる)。

### 80% title-safe zone

プロジェクターは画面端 10-15% が表示されない領域 (title-safe area)。 字幕・credit text は **safe zone 内に収める**:

- 1920x1080 基準で safe area: x ∈ [-768, 768], y ∈ [-432, 432] (= 80% × 80%)
- 余裕含みなら x ∈ [-750, 750], y ∈ [-420, 420]
- 中央配置 (Position `0 0`) や中央寄せ (Position `0 -180`) は問題ない (中心部だから)
- 左下字幕 (Position `-820 -494` 等) は **safe zone 外**。 内側に移動: `-750 -420` など

### 一括 Position 移動

```python
# 既存の左下字幕を一括で safe zone 内に
content = content.replace('value="-820 -494"', 'value="-750 -420"')
```

### 既知の落とし穴 (projection-ready)

- **暗黙の gap が黒で render されない**: 最初の asset-clip を `offset="3s"` にしただけだと、 0-3s が黒にならない (FCP の挙動が不安定)。 `<gap>` を**明示的**に書く
- **lane=-1 の asset-clip まで shift してしまう**: BGM/audio の offset まで触ると音がずれる。 regex で spine直下のみ捕捉
- **Position 80% safe を絵柄で目視確認しない**: 値だけで判断せず、 PC で全画面再生して端の見切れ感を確認
- **trail gap の offset 計算ミス**: 最後の asset-clip の **offset + duration** が trail gap の offset になる。 sequence duration から逆算しない

## 関連スキル

- **dji-fcpxml**: 基本のFCPXML仕様（asset.start / format / TC / 29.97 frame整合）
- **fcp-titles**: spine上のtitle要素（spine構造変更時は title も再注入する。 Position 80% safe zone も title 側で管理）
- **fcp-image-overlay**: spine上のvideo要素（同上、装飾も再注入）
- **fcp-library-ops**: spine変更後の library運用 (Transcoded Media のリフレッシュ)

## 関連メモリ

- `feedback_fcpxml_framerate.md` — 29.97 素材の denominator 整合
- `feedback_fcpxml_resource_id_dynamic.md` — resource ID 動的取得の必要性
- `feedback_fcpxmld_bundle.md` — `.fcpxmld` バンドル形式を作業基準にする運用
