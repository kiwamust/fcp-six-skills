---
name: fcp-image-overlay
description: >-
  Final Cut Pro の video 要素 (PNG/SVG画像) を FCPXML で実装する。
  シネマティック帯、半透明box、ロケーションカード、地図アニメ、グラフィック挿入カットなど
  「画像系オーバーレイ」専用。video.adjust-transform position の単位 (4K canvas基準で
  1080px=50unit、変換係数 1/21.6) を扱う。SVG → rsvg-convert → rgba PNG変換、
  format個別定義（r1共有のNG）、transparent alpha の扱い、 lane合成順を含む。
  「帯」「シネマ帯」「box」「PNGオーバーレイ」「SVG」「装飾」「ロケーションカード」
  「画像挿入」「グラフィック」「rsvg-convert」「半透明」「adjust-transform」等で発動。
  テキスト系オーバーレイは fcp-titles、 spine構造変更は fcp-spine-edit、
  基本のFCPXML仕様は dji-fcpxml。
---

# fcp-image-overlay — FCP の video 要素（PNG/SVG画像オーバーレイ）

`<video>` 要素は FCPXML 1.13 で **PNG/SVG画像 asset** をタイムライン上にオーバーレイするための要素。シネマティック帯、半透明box、ロケーションカード、地図アニメ、挿入カットの装飾画像などに使う。

## 核となる教訓

- **adjust-transform position は 4K canvas基準の独自unit**（1080px = 50 unit、変換係数 1/21.6）
- **format は PNGネイティブサイズで個別定義**（r1=4K共有だと画像が4Kに伸びる）
- **start="3600s" が必須**（`"0s"` だとFCPが処理できない場合あり）
- **半透明PNGは SVG → rsvg-convert で生成**（ffmpeg 直生成は alpha がFCPで効かない）
- **resource ID は動的取得**（FCPがclip削除等で再番号付けする）

## 1. asset 定義（PNG/SVG）

```xml
<resources>
    <!-- format は PNG ネイティブサイズで個別定義 (重要: r1共有だとFCPが4Kに伸ばす) -->
    <format id="g_xxx_fmt" name="FFVideoFormatRateUndefined"
            width="<png_width>" height="<png_height>" colorSpace="1-13-1"/>

    <asset id="g_xxx" name="..." start="0s" duration="0s"
           hasVideo="1" format="g_xxx_fmt" videoSources="1">
        <media-rep kind="original-media"
                   src="file:///abs/path/to/image.png"/>
    </asset>
</resources>
```

## 2. video 要素の正規構造

```xml
<asset-clip ref="rX" ...>
    <video ref="g_xxx" lane="3"
           offset="<親asset-clip.start値>"
           name="..."
           start="3600s"
           duration="<dur>">
        <adjust-transform position="<x_unit> <y_unit>"/>
    </video>
</asset-clip>
```

### 決定的ポイント

| 項目      | 真値                                 | 注意                                                 |
| --------- | ------------------------------------ | ---------------------------------------------------- |
| start     | `"3600s"` 必須                       | generator系の標準                                    |
| Position  | `<adjust-transform position="x y"/>` | **4K canvas unit**（1080px=50unit）                  |
| format    | PNG ネイティブサイズで個別定義       | `r1` (sequence format=4K) 共有はNG                   |
| media-rep | src 絶対パス                         | bookmark なくても動くが、FCP再import時に消える可能性 |
| lane      | 字幕より小さい数値が奥               | 帯=lane1,2、字幕=lane3,4                             |

## 3. position の単位（重要）

video の `<adjust-transform position="x y"/>` は **4K canvas基準の独自単位**:

- 中央: (0, 0)
- y=50 で画面上端 (4K canvas height 1080 px = 50 unit)
- y=-50 で画面下端
- 変換係数: **1 unit = 21.6 pixel** (4K canvas基準)

### Inspector ↔ XML の対応

- Inspector で **Y=950 (pixel)** に動かす → XML 上は **`position="0 43.9815"`** (= 950/21.6)
- 逆に XML で `position="0 43.9815"` → Inspector では Y=950

### title (1920x1080基準pixel) との変換

字幕（title.Position）と帯（video.adjust-transform）を **画面の同じ高さ**に並べる:

```python
PIXEL_TO_UNIT = 2.0 / 21.6  # ≈ 0.0926

# 例: 字幕 title.Position y=494 (1920基準) と帯 video.position y=45.74 (4K unit) は画面上で同じ高さ
title_y_pixel = 494          # title.Position の Y
video_y_unit = title_y_pixel * PIXEL_TO_UNIT  # ≈ 45.74
```

理由:

- title.Position は 1920x1080 基準なので、4K canvas pixel に換算すると **×2**
- 4K canvas pixel → unit に換算すると **÷21.6**
- 合わせて **×2/21.6 ≈ ×0.0926**

## 4. 半透明 PNG は SVG → rsvg-convert が確実

ffmpeg で `color=black@0.7` を生成すると `pix_fmt=rgb24` になり、FCPで透明度が効かない。

### 確実な手順

```bash
# 1. SVG で fill-opacity を明示
cat > /path/glass-bar.svg <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 92" width="1920" height="92">
    <rect x="0" y="0" width="1920" height="92" fill="black" fill-opacity="0.5"/>
</svg>
EOF

# 2. rsvg-convert で rgba PNG に変換 (SVG alpha が PNG alpha チャンネルに保持される)
rsvg-convert -w 1920 -h 92 /path/glass-bar.svg > /path/glass-bar.png

# 3. 検証
ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 /path/glass-bar.png
# → rgba （rgb24 でないこと）

magick /path/glass-bar.png -format "%[pixel:p{50,50}]" info:
# → srgba(0,0,0,0.501961) のように alpha が保持されていれば OK
```

### なぜ ffmpeg 直生成はダメか

- ffmpeg `-pix_fmt rgba` 指定でも、FCPが alpha を「**ストレートalpha vs pre-multiplied alpha**」のどちらに解釈すべきか判別できず、結果として alpha が無視される
- SVG は **vector レベルで透明度** を持つ。rsvg-convert は SVG の fill-opacity を **PNG alpha チャンネルに正しくエンコード**する
- FCPは rsvg-convert 出力の rgba PNG を確実に半透明として描画する

## 5. format は PNG ネイティブサイズで個別定義

```xml
<!-- 良: PNGネイティブサイズで個別定義 -->
<format id="g_glass_bar_fmt" name="FFVideoFormatRateUndefined"
        width="1920" height="92" colorSpace="1-13-1"/>

<!-- 悪: r1 (sequence format=4K) 共有 -->
<asset id="g_glass_bar" format="r1" ...>  <!-- FCP が画像を3840x2160に拡大する -->
```

PNG 1920x92 を **r1 (4K) format で共有させると、FCPがspatial conformで画像をsequence解像度に拡大**してしまう。 結果、上下に置いた帯が**画面全体を覆う**ような表示になる。

### 専用formatの命名規則

```
g_<asset_name>_fmt
  └ width=<png_width> height=<png_height> colorSpace="1-13-1"
```

各PNGに対して 1 format。共有しない。

## 6. lane 合成順

数値が大きいほど手前。

このスキルは「画像オーバーレイ（`<video>`）と字幕（`<title>`）を同一カットに載せる」前提が多いので、**fcp-titles と共有する典型スタック**をここで固定する:

| stack（奥→手前） | 要素                   | 推奨lane |
| ---------------- | ---------------------- | -------- |
| 奥               | 上下帯など「背景寄り」 | 1–2      |
| 中               | ロケーションカード等   | 2–3      |
| 手前             | 字幕（`<title>`）      | 3–4      |

例外もある（エンドカードのみ、字幕無しの装飾のみ等）。迷ったら **FCP上で上下関係を作って Export XML → lane を読む**のが最短。

同じlaneに重複して clip を置くと衝突する。connected clip は lane を別々に。

## 7. resource ID は動的取得（必須）

```python
import re

GLASS_BAR_ASSET_RE = re.compile(
    r'<asset\s+id="(r\d+|g_\w+)"\s+name="Glass Bar"', re.DOTALL
)

def main():
    content = INFO_FCPXML.read_text(encoding="utf-8")
    m = GLASS_BAR_ASSET_RE.search(content)
    if not m:
        raise SystemExit("Glass Bar asset not found")
    glass_bar_asset_id = m.group(1)
```

特に**自分で名前を付けた asset (g_xxx_fmt)** は固定ID で書き込めるが、FCPで実際に import → re-export すると、自動asset (r4, r5 等)に変換される可能性がある。 name 属性で動的取得が頑健。

## 8. AI下書き → FCP refine → export ループ

最初の1個は **FCPで Inspector経由で配置 → export → AI読み取り** が最短。

### ループ手順

1. **AI**: skeleton で video を仮値で書き込む（Position 0,0 など）
2. **ユーザー**: FCPで .fcpxmld を re-import → 視聴
3. **ユーザー**: Inspector で Position/Scale/Opacity を refine → File → Export XML で上書き
4. **AI**: exported XML から `<adjust-transform position>` の正規値を読み取り、テンプレ化

### 最初の1個 export で取れる重要情報

- format の正規構造（width/height/colorSpace/name）
- asset の正規 attribute（uid/sig/start/duration/hasVideo）
- video の start 属性の正規値（"3600s"）
- adjust-transform position の単位（pixel? unit? の確定）

## 9. 既知の落とし穴

- **format=r1 共有**: FCPが画像を4Kサイズに拡大する。PNGネイティブサイズで個別定義
- **PNG が transparent にならない**: ffmpeg 直生成 (rgb24) ではFCPが alpha を読まない。SVG→rsvg-convert で rgba 生成
- **adjust-transform position に 1920基準pixel を入れる**: 単位が違う。4K canvas unit (1080=50) に変換
- **start="0s" で書く**: generator系は `"3600s"` が標準
- **bookmark なし**: 同じmac でも import時に再認識されないことあり。FCP正規 export 経由で bookmark を取得するのが理想
- **削除regex を `ref="g_xxx"` で書く**: FCPがimport→re-exportで `g_glass_bar` → `r3` 等に id 再番号付け。残骸が消えず重複蓄積する。**`name="Top Bar"` 等の name属性ベース**で識別する
- **シーンごとに帯を配置する**: 30シーン × 上下 = 60本の帯がタイムラインに並ぶ。**spine全体に1本ずつ** (最初のasset-clip lane=1,2 に duration=spine全長) が正解
- **name属性に `&` を含める**: XML escape必須。`xml_escape()` を name書き出し直前に適用

### 削除regexの現実的パターン（re-export 耐性）

`ref` は再番号付けされる。**安定キーは `name=`**（運用で名前規約を固定する）。

```python
import re

# 例: name が Top Bar / Bottom Bar の装飾 video を削除（タグは自己閉じ/子要素ありの両対応）
DECO_VIDEO_BY_NAME_RE = re.compile(
    r'\s*<video\b[^>]*\bname="(?:Top Bar|Bottom Bar)"[^>]*(?:/>|>.*?</video>)',
    re.DOTALL,
)
```

広すぎる `<video ...>` 全削除は誤爆する（ユーザーの通常クリップまで消える）。**削除対象は「このプロジェクトで付けた装飾の name 規約」に限定**する。

## 関連スキル

- **fcp-titles**: テキスト系オーバーレイ（字幕・テロップ）。画像と並べる時の単位変換
- **fcp-spine-edit**: spine 構造編集（image overlay が連結している parent asset-clip の側）
- **dji-fcpxml**: 基本のFCPXML仕様（asset.start/format/TC変換）
- **travelVlog**: 上位ワークフロー（旅行Vlog制作の5フェーズ）

## 関連メモリ

- `feedback_fcpxml_title_structure.md` — overlay系の正規構造（title/video 共通）
- `feedback_fcpxml_resource_id_dynamic.md` — resource ID 動的取得の必要性
