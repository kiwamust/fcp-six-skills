---
name: fcp-titles
description: >-
  Final Cut Pro の title 要素 (Basic Title / Typewriter 等) を FCPXML で実装する。
  字幕・テロップ・ロケーション名・所感など「テキスト系オーバーレイ」専用。
  effect uid (Bumper:Opener / Build In:Out)、param Position/Size/Alignment/Flatten、
  text-style-def、Drop Shadow/Outline、 Typewriter のタイピング演出
  (Animate / End Offset / Spread)、title.Position の単位 (1920x1080基準pixel) を扱う。
  AI下書き → FCP refine (Inspector) → export → 反映 のループ運用も含む。
  「字幕」「Title」「Basic Title」「Typewriter」「タイピング演出」「Build In」「Type On」
  「テロップ」「FCPで字幕」「字幕プリセット」「Drop Shadow」「Outline」「fontSize」
  「テキストオーバーレイ」等で発動。
  画像オーバーレイ (帯・box) は fcp-image-overlay、 spine構造変更は fcp-spine-edit、
  基本のFCPXML仕様は dji-fcpxml。
---

# fcp-titles — FCP の title 要素（字幕・テロップ）

`<title>` 要素は FCPXML 1.13 で **Basic Title** (Motion テンプレ) を使ったテキストオーバーレイ。字幕、テロップ、ロケーションカードのテキスト部分などに使う。

## 核となる教訓

- **Basic Title の uid は `Bumper:Opener.localized` 配下**、 **Typewriter の uid は `Build In:Out.localized` 配下** ─ 同じ "title" でもカテゴリが違う。両方を押さえる
- **param keyのprefix がカテゴリで変わる**: Basic Title は `9999/999166631/999166633/...`、 Typewriter は `9999/10986/10988/...`。**keyを付け替えないと param が無視される**
- **表示サイズは `<param name="Size">` で制御**。`text-style.fontSize` 単独では効かない
- **Position は 1920x1080 基準 pixel** (中央0,0、x:±960, y:±540)
- **resource ID は動的取得**（FCPがclip削除等で再番号付けする）

## 1. 正規構造

```xml
<resources>
    <effect id="rN" name="Basic Title"
            uid=".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"/>
</resources>

<spine>
    <asset-clip ref="rX" offset="..." start="..." duration="...">
        <!-- lane はプロジェクト固定ではない。画像オーバーレイと併用する典型スタックは fcp-image-overlay §6 の推奨を優先 -->
        <title ref="rN" lane="3"
               offset="<親asset-clip.start値>"
               name="字幕#N"
               start="108108000/30000s"
               duration="<dur>">
            <param name="Position"  key="9999/999166631/999166633/1/100/101"           value="0 0"/>
            <param name="Flatten"   key="9999/999166631/999166633/2/351"               value="1"/>
            <param name="Alignment" key="9999/999166631/999166633/2/354/999169573/401" value="1 (Center)"/>
            <param name="Size"      key="9999/999166631/999166633/5/999166635/3"       value="50"/>
            <text>
                <text-style ref="tsM">字幕本文</text-style>
            </text>
            <text-style-def id="tsM">
                <text-style font="Helvetica" fontSize="50" fontFace="Regular"
                            fontColor="1 1 1 1" alignment="center"/>
            </text-style-def>
        </title>
    </asset-clip>
</spine>
```

### 決定的ポイント

| 項目        | 真値                                                     | 注意                                           |
| ----------- | -------------------------------------------------------- | ---------------------------------------------- |
| uid         | `Bumper:Opener.localized` 配下                           | `Build In:Out.localized` は誤り                |
| 表示サイズ  | `<param name="Size">`                                    | text-style.fontSize 単独では無効。両方同期する |
| 表示位置    | `<param name="Position">` `"x y"` (1920基準pixel)        | center=`0 0`、下端寄せはY=負値                 |
| 整列        | `<param name="Alignment">` `"1 (Center)"`                | "0 (Left)" / "1 (Center)" / "2 (Right)"        |
| Flatten     | `<param name="Flatten">` `"1"`                           | 2D平面化（3D効果なし）デフォルト               |
| 配置        | 親 asset-clip の **子要素**（lane は重なり回避で決める） | connected clip 扱い                            |
| offset      | 親 asset-clip の **start値と一致**                       | 親の先頭から表示開始                           |
| duration    | 親より長くてOK                                           | 複数clipにまたがって表示可                     |
| title.start | `108108000/30000s` のまま                                | テンプレ内部時間軸、触らない                   |

## 2. Typewriter (Build In:Out 系) — タイピング演出

字幕を**開始時点から1文字ずつ打ち出す**演出を入れたい時、 Basic Title ではなく **Typewriter** title を使う。 Build In:Out カテゴリ配下の別 effect なので、 effect定義・param key prefix・必須param がすべて Basic Title と異なる。

### 正規構造

```xml
<resources>
    <effect id="rN" name="Typewriter"
            uid=".../Titles.localized/Build In:Out.localized/Typewriter.localized/Typewriter.moti"/>
</resources>

<spine>
    <asset-clip ref="rX" ...>
        <title ref="rN" lane="1"
               offset="<親asset-clip.start値>"
               name="字幕#N"
               start="108108000/30000s"
               duration="<dur>">
            <param name="Position"   key="9999/10986/10988/1/100/101"           value="-820 -494"/>
            <param name="Alignment"  key="9999/10986/10988/2/354/1156452346/401" value="0 (Left)"/>
            <param name="Opacity"    key="9999/10986/10988/4/11030/1000/1044"   value="0"/>
            <param name="Animate"    key="9999/10986/10988/4/11030/201/203"     value="1 (Character (without spaces))"/>
            <param name="Spread"     key="9999/10986/10988/4/11030/201/204"     value="0"/>
            <param name="End Offset" key="9999/10986/10988/4/11030/201/213"     value="120"/>
            <text>
                <text-style ref="tsM">Day 1  18:54  Colombo Bandaranaike Airport</text-style>
            </text>
            <text-style-def id="tsM">
                <text-style font="Helvetica" fontSize="40" fontFace="Bold Oblique"
                            fontColor="1 1 1 1" bold="1" italic="1"/>
            </text-style-def>
        </title>
    </asset-clip>
</spine>
```

### 決定的ポイント

| param        | key                                     | 役割                                                                      |
| ------------ | --------------------------------------- | ------------------------------------------------------------------------- |
| `Position`   | `9999/10986/10988/1/100/101`            | 1920x1080基準pixel (Basic Title と同じ単位)                               |
| `Alignment`  | `9999/10986/10988/2/354/1156452346/401` | `"0 (Left)"` 等。**末尾IDが Basic Title と異なる** (999169573→1156452346) |
| `Opacity`    | `9999/10986/10988/4/11030/1000/1044`    | `"0"` 初期値 (アニメ開始時)                                               |
| `Animate`    | `9999/10986/10988/4/11030/201/203`      | `"1 (Character (without spaces))"` でスペース以外を1文字ずつ              |
| `Spread`     | `9999/10986/10988/4/11030/201/204`      | `"0"` (タイピング間隔の散らばり)                                          |
| `End Offset` | `9999/10986/10988/4/11030/201/213`      | typing 速度。 値↑ で typing が遅く (= 各文字の表示時間が長く)             |

### Basic Title との差異

| 項目           | Basic Title                    | Typewriter                                   |
| -------------- | ------------------------------ | -------------------------------------------- |
| effect uid     | `Bumper:Opener.localized/...`  | `Build In:Out.localized/...`                 |
| key prefix     | `9999/999166631/999166633/...` | `9999/10986/10988/...`                       |
| 必須/特有param | `Flatten`, `Font`              | `Animate`, `Opacity`, `Spread`, `End Offset` |
| Alignment末尾  | `999169573/401`                | `1156452346/401`                             |

key prefix を変えずに値だけ書き換えると **param が反映されない**。 そのまま import は通るが Inspector で見ると "default" 表示になる。

### 一括適用パターン (Basic Title → Typewriter)

字幕#1 だけ FCP で手動で Typewriter に置換 → Export XML → 残り N-1 個に複製 が最短ルート。

```python
TITLE_RE = re.compile(
    r'<title ref="r4" lane="1" offset="(?P<offset>[^"]+)" name="(?P<name>字幕#\d+P)" '
    r'start="(?P<start>[^"]+)" duration="(?P<duration>[^"]+)">\s*'
    r'<param name="Position" key="9999/999166631/999166633/1/100/101" value="(?P<pos>[^"]+)"/>\s*'
    r'<param name="Flatten" key="9999/999166631/999166633/2/351" value="1"/>\s*'
    r'(?:<param name="Font" key="9999/999166631/999166633/5/999166635/83" value="[^"]*"/>\s*)?'
    r'<text>\s*<text-style ref="(?P<tsid>ts\d+)">(?P<text>[^<]+)</text-style>\s*</text>\s*'
    r'<text-style-def id="(?P=tsid)">\s*'
    r'<text-style font="Helvetica" fontSize="40" fontFace="Bold Oblique" fontColor="1 1 1 1" bold="1" italic="1"/>\s*'
    r'</text-style-def>\s*</title>',
    re.DOTALL,
)
```

ref を `r4 → 動的取得した Typewriter id` (上の例では `r6`) に差し替え、 param block を Typewriter 用に組み直す。 duration / start / offset / Position 値・text-style はすべて温存する。

### typing 速度の感覚

- `End Offset="120"` で 41文字 (例: `Day 1  18:54  Colombo Bandaranaike Airport`) を約 **2-3秒** で打ち切る感覚
- 短い字幕 (10-15文字) なら 1秒未満で完了 → 表示残り時間でテキスト視認
- 値を増やすと typing が伸びる (各文字の在床時間が伸びる)
- 速度を全字幕で揃えたい場合は **End Offset を固定** + duration はクリップ毎に既存値を温存、で十分自然

### typewriter で Build In アニメは title 全体に内包される

Build In:Out 系 title は `<title>` 自体がアニメーション付き generator。 別途 `<filter-video>` でエフェクトを乗せる必要はない。 typing は "始まった瞬間から" 自動で走る。

## 3. Position の単位

**1920x1080 基準 pixel** (4K素材でも内部基準は1920x1080)。

- 中央: (0, 0)
- 画面端: x: ±960, y: ±540
- 安全領域 (8%) 考慮: x: ±884, y: ±496
- 左上付近: (-600, 400)
- 右上付近: (600, 400)
- 下端字幕: (0, -450)

帯（画像オーバーレイ）と並べる時は単位差に注意。詳細は **fcp-image-overlay** の単位変換を参照。

## 4. Drop Shadow / Outline (要 export)

字幕に Drop Shadow や Outline を付ける場合、param key は **FCP正規 export からのみ確定する**。
推測で `9999/.../4/352` 系を書いても効かない（実測あり）。

### 取得手順

1. FCPで対象 title clip を選択
2. Inspector → Title タブ → **Drop Shadow / Outline** を有効化
3. 色・距離・ぼかし・太さを設定
4. **File → Export XML** で保存
5. exported XML から param key を抽出してスクリプトに反映

## 5. resource ID は動的取得（必須）

FCPは clip削除や再import の際に resource ID を再番号付けする。`<title ref="r3">` 固定書きは時間差で壊れる。

```python
import re

BASIC_TITLE_EFFECT_RE = re.compile(
    r'<effect\s+id="(r\d+)"\s+name="Basic Title"', re.DOTALL
)

def main():
    content = INFO_FCPXML.read_text(encoding="utf-8")
    m = BASIC_TITLE_EFFECT_RE.search(content)
    if not m:
        raise SystemExit("Basic Title effect not found")
    basic_title_effect_id = m.group(1)  # 実行時に取得
```

削除regex も汎用化:

```python
# 良: id汎用、再番号付けに強い
TITLE_BLOCK_RE = re.compile(r'\s*<title\s+ref="r\d+"[^>]*>.*?</title>', re.DOTALL)
```

## 6. AI下書き → FCP refine → export ループ

字幕は文言や位置の試行錯誤が頻発する。FCP上で軽快に refine するためのワークフロー:

1. **AI**: skeleton的な title を仮値で書き込む（Position 0,0、Size 50 など）
2. **ユーザー**: FCPで .fcpxmld を re-import → 視聴
3. **ユーザー**: Inspector で Position/Size/文言/Drop Shadow を refine → File → Export XML で上書き
4. **AI**: export された XML から正規 param 値を読み取り、テンプレ化して連発

### 最初の1個 export で取れる重要情報

- effect uid（環境依存性は低いが念のため確認）
- Position/Size param の正確な key
- Drop Shadow/Outline param key（必要時）
- text-style 属性のバリデーション

## 7. 既知の落とし穴

- **Basic Title の uid を Build In:Out で書く**: 誤り。Basic Title は Bumper:Opener が正解、Typewriter は Build In:Out が正解 ─ **逆**
- **Typewriter に Basic Title の key prefix を流用する**: prefix が違う (Basic は `9999/999166631/999166633/...`、 Typewriter は `9999/10986/10988/...`) ので param が無視される
- **Typewriter に Basic Title の Alignment key 末尾を流用**: Basic は `999169573/401`、 Typewriter は `1156452346/401`。 末尾IDが違う
- **fontSize だけで大きさを変える**: 効かない。`<param name="Size">` を併記する (Basic Title)
- **Position が画面外に飛ぶ**: 4K canvas の値（±1920）で書くと外れる。1920x1080基準pixel が正解
- **ref="r3" 固定**: FCPがID再番号付けで壊れる。動的取得する
- **TITLE_BLOCK_RE が ref="r3" 固定**: 削除regex も `r\d+` で汎用化する
- **`&` `<` を生で書く**: DTD validation failed エラー。`xml_escape()` を text/name 書き出し直前に必ず適用
- **alignment="center" のまま長文書く**: 画面外に切れる。`alignment="0 (Left)"` + 中心スタートで右展開する選択肢も持つ
- **size パラメータを変えても fontSize と非同期**: param Size と text-style fontSize は両方同じ値で書く（片方だけだと FCP が混乱）
- **Typewriter title の duration が短すぎる**: typing が完了する前に title が消える → 文字が途中で切れる。 End Offset 値と文字数を見て duration を確保する

## 関連スキル

- **fcp-image-overlay**: 帯・box・PNGなど画像系オーバーレイ。字幕と並べる時の単位変換も。lane の典型スタックもこちらで定義する
- **fcp-spine-edit**: spine 構造編集（title が連結している parent asset-clip の側）
- **dji-fcpxml**: 基本のFCPXML仕様（asset.start/format/TC変換）

## lane の決め方（帯と字幕を同一カットに載せるとき）

- **原則**: lane は「奥→手前」のスタック順。**数値が大きいほど手前**。
- **典型（fcp-image-overlay と整合）**: 帯（背景寄り）を lane 1–2、字幕（`<title>`）を lane 3–4。
- **単独字幕のみ**: `lane="1"` のような低番号でも import は通るが、後から帯を足すと合成順が崩れやすい。最初から「将来の帯」を見越して余白 lane を空けるか、帯導入時に lane をまとめて見直す。
- **確定手順が最短**: FCP で期待の前後関係になるまでドラッグ調整 → Export XML で lane を読み取り、その値をテンプレ化する。

## 関連メモリ

- `feedback_fcpxml_title_structure.md` — title要素の正規構造（実測ベース）
- `feedback_fcpxml_resource_id_dynamic.md` — resource ID 動的取得の必要性
- `feedback_fcpxml_typewriter.md` — Typewriter title の正規構造と Basic Title との差異
