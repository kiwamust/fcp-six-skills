---
name: dji-fcpxml
description: >-
  DJI OSMO Pocket 3 の素材を Final Cut Pro で扱うための実装技術スキル。
  FCPXML（1.13）を新規生成・編集・診断する。特に 29.97fps 素材の format / timecode / frame-alignment を正しく書く。
  「DJI」「OP3」「Osmo Pocket」「fcpxml」「fcpxmld」「invalid edit」「frame boundary」
  「asset-clip」「タイムコード」「29.97」「DF」「drop-frame」「粗編集XML」「スケルトンXML」「ffprobe」等で発動。
  素材取り込みとXML基本仕様に絞る。字幕は fcp-titles、 画像オーバーレイは fcp-image-overlay、
  spine構造編集は fcp-spine-edit、音声は fcp-audio、 library運用は fcp-library-ops、
  企画〜納品のフェーズ管理は任意のドメインワークフロースキル（本リポジトリ外）に委譲。
---

# dji-fcpxml — DJI OP3 × Final Cut Pro 実装技術

DJI OSMO Pocket 3 の実ファイル特性と、FCP が要求する FCPXML の正規仕様を知っているのが前提のスキル。
推測で属性をいじるのではなく、**ffprobe で実ファイルを測定し、FCP正規exportと差分を取る**のが基本姿勢。

## なぜこのスキルが必要か

DJI OP3 の MP4 は 29.97fps (30000/1001) で、フレームは非整数秒境界に並ぶ。さらに各ファイルに**カメラ内部の recording timecode** が埋まっている。FCP はこれらを厳密にチェックする。

人間が「30fps ぽい」前提で XML を書くと：

- `invalid edit with no respective media` が全video asset-clipに出る
- `the item is not on an edit frame boundary` が大量発生する
- タイムラインに動画が表示されない

過去、これらを推測で直そうとして **4回試行 × 各数十分** を溶かした。FCP 正規 export を1本取って差分を見た瞬間に解けた。この教訓がスキルの核。

## 作業基準は `.fcpxmld/Info.fcpxml`（手書き単体 `.fcpxml` ではない）

FCPXML を編集するとき、**作業基準ファイルは FCP 正規 export の `.fcpxmld` バンドル**（中身は `Info.fcpxml`）にする。手書き単体 `.fcpxml` を更新し続けるのは推測の温床。

**理由**:

- FCP の実プロジェクト状態は `.fcpxmld` にしか正確に出ない
- 手書き単体 `.fcpxml` で作業し続けると、FCP上の編集（video 組み直し、audio fade、keyframe、duration 調整）と乖離する
- 乖離した状態で SE/ENV/GFX を配置すると、TC が全部ずれて「実装したのに反映されない」事態になる

**ワークフロー**:

1. **初期 skeleton**: 手書き `.fcpxml`（小さく、シンプルに作る）
2. FCP に import → タイムラインで編集
3. **編集後に修正が必要なら、まず FCP で再 export を依頼**: `File > Export XML... > FCPXML 1.13` で `.fcpxmld` を生成
4. `.fcpxmld/Info.fcpxml` を基準ファイルにして編集（Edit ツール直接書き換えOK）
5. 編集後 FCP で再 import（または `.fcpxmld` を直接読み込み）

**注意**:

- バックアップは **バンドル全体（フォルダ）をコピー**: `cp -r foo.fcpxmld foo.fcpxmld.YYYY-MM-DD.bak`
- `.fcpxmld/Info.fcpxml` は通常の XML として扱える（`xmllint --noout` で検証、Edit で書き換え）
- FCP export の最簡約形（例: `9009/500s` ＝ `540540/30000s`）は**触らない**。値が等価なら denominator 違いは無視。新規追加部分だけ `/30000s` で書く（FCP が import 時に最簡約する）
- 単体 `.fcpxml` と `.fcpxmld/Info.fcpxml` の両方が存在する場合、混乱を避けるため **作業状況を明示**する（「fcpxmld 側が最新、fcpxml は古い skeleton」）
- 「ユーザーが FCP上で編集した可能性がある」状況では、推測で属性いじり始めずに **再 export を依頼**する

これは「推測で属性いじり続けるのは悪手。1本 export → 差分が最短」（核教訓）の運用形。

## このスキルに含まれるもの

1. **作業基準ファイルの選び方** — 単体 `.fcpxml` ではなく `.fcpxmld/Info.fcpxml`
2. **DJI OP3 ファイル仕様** — 解析すべきメタデータと典型値
3. **FCPXML の正規仕様**（29.97 素材向け）— `asset.start` / `asset-clip.start` / format / denominator
4. **TC → /30000s の変換** — スクリプト提供
5. **トラブルシューティングのフローチャート** — import エラーの切り分け

含まれないもの（別 skill）:

- 字幕・テロップ系（`<title>`、Basic Title、Drop Shadow） → **fcp-titles**
- 画像オーバーレイ（`<video>`、PNG/SVG 装飾、帯、box） → **fcp-image-overlay**
- spine 構造編集（asset-clip duration/offset 一括変更、kindベース尺リサイズ） → **fcp-spine-edit**
- 音声（BGM/ENV/SE、lane=-1、fade の XML 構造） → **fcp-audio**
- library 運用（Copy to library、SD運用、Transcoded Media） → **fcp-library-ops**

---

## 1. まず ffprobe で実ファイルを測定する

XML 生成や診断の前に、必ずこれを実行。推測で書き始めない。

```bash
ffprobe -v error \
  -show_entries stream=codec_name,r_frame_rate,nb_frames,width,height,color_space \
  -show_entries stream_tags=timecode \
  -show_entries format=duration \
  /path/to/DJI_xxx.MP4
```

### DJI OP3 の典型値（4K 30p 設定時）

| 項目         | 値               | 備考                                               |
| ------------ | ---------------- | -------------------------------------------------- |
| codec        | `hevc` Main 10   | 10-bit 4:2:0                                       |
| 解像度       | 3840 × 2160      |                                                    |
| r_frame_rate | `30000/1001`     | **29.97fps（30fpsではない）**                      |
| color_space  | `bt709`          | Rec.709                                            |
| audio        | AAC 48000Hz 2ch  |                                                    |
| **timecode** | 例 `21:56:13;18` | **DF (drop-frame)**。セミコロン区切り              |
| nb_frames    | 実フレーム数     | XML著者が30fps前提で割ると 0〜3 フレーム過大になる |

**TC を読み損ねない**。`stream_tags=timecode` が空のファイルは DJI 素材として不正なので疑え。

---

## 2. FCPXML 1.13 の正規仕様（29.97 素材）

FCP 自身がexport する形を写経する。これが**唯一の真実**。
推測するな、FCP に書かせろ。

### 決定的ポイント

| 要素                             | 正規の書き方                                                                                                      | 誤りがち                                                                      |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `<format>`                       | `frameDuration="1001/30000s"` name="FFVideoFormat3840x2160p2997"                                                  | 30fps宣言（`100/3000s`）で書くと全clipが invalid                              |
| video `<asset>` start            | **camera TC を DF frames換算** した `(DF_frames * 1001)/30000s`                                                   | `0/1s` と書くと全clipが invalid                                               |
| video `<asset>` duration         | `(nb_frames * 1001)/30000s`                                                                                       | 著者想定フレーム数 / 30s                                                      |
| video `<asset>` format           | sequence と同じ `r1` を参照                                                                                       | r2 split は不要（混在パターンも効かない）                                     |
| `<asset-clip>` start             | **`asset.start + in-point_frames * 1001` の絶対値**（denominator は何でも良い。`/30000s` で書けば必ずimport通る） | in-point の相対値で書くと invalid                                             |
| `<asset-clip>` offset / duration | `(sequence_frames * 1001)/30000s`                                                                                 | `X/30s` だと frame boundary 違反                                              |
| `<sequence>`                     | `format="r1"` duration `/30000s` 単位                                                                             |                                                                               |
| 音声 `<asset>` duration          | `X/30s` のまま（絶対時間）                                                                                        | 変換不要                                                                      |
| 静止画 `<asset>`                 | `duration="0s"`（timeless）                                                                                       | `<asset-clip>` で参照せず `<video>` で参照（`<asset-clip>`だとFCPクラッシュ） |

### minimal pattern — FCP probe export の実例（`references/fcp-canonical-export-1.13.fcpxml` より抜粋、先頭3秒・末尾2秒トリム済み）

```xml
<format id="r1" name="FFVideoFormat3840x2160p2997" frameDuration="1001/30000s"
        width="3840" height="2160" colorSpace="1-1-1 (Rec. 709)"/>

<asset id="r2" name="DJI_20260405215615_0013_D"
       uid="04972A01EBD8BD56BFD94A8B58AC451F"
       start="2369204838/30000s"          <!-- camera TC: 21:56:13;18 DF → 2366838 frames × 1001 -->
       duration="423423/30000s"           <!-- 423 frames × 1001 (実ファイル nb_frames=423) -->
       hasVideo="1" hasAudio="1" format="r1"
       videoSources="1" audioSources="1" audioChannels="2" audioRate="48000">
  <media-rep kind="original-media" sig="04972A01EBD8BD56BFD94A8B58AC451F"
             src="file://<PROJECT_ROOT>/Video/DJI_20260405215615_0013_D.MP4"/>
</asset>

<sequence format="r1" duration="243243/30000s" tcStart="0s" tcFormat="NDF"
          audioLayout="stereo" audioRate="48k">
  <spine>
    <asset-clip ref="r2" offset="0s" name="DJI_20260405215615_0013_D"
                start="394885491/5000s"    <!-- asset.start + 108 frames (3.6s trim-in). = 2369312946/30000s を最簡約した形 -->
                duration="243243/30000s"   <!-- 243 frames (トリム後の表示尺) -->
                tcFormat="DF" audioRole="dialogue">
      <audio-channel-source srcCh="1, 2" role="dialogue.dialogue-1"/>
    </asset-clip>
  </spine>
</sequence>
```

ここから読み取れる決定的事実：

- **asset.start は camera TC**（21:56:13;18 DF = 2366838 DF frames → × 1001 = 2369204838/30000s）
- **asset-clip.start は in-point の絶対座標**。トリムなしなら asset.start と一致、3秒トリムなら asset.start + 108 frames
- **FCP は分数を最簡約して書く**。`394885491/5000s` は `2369312946/30000s` と同じ時刻。reference を diff するときは値が一致していれば denominator 違いは気にしない
- offset は spine 直下の asset-clip なので `0s`（sequence 先頭）。connected clip なら gap 起点の offset が入る

**なぜこの形か**: FCP は asset.start を「ファイルに書かれた TC」と一致しているか検証する。一致しなければ "no respective media"。asset-clip.start は絶対 TC 座標（差分で書くと invalid）。offset / duration は sequence の frame 境界（29.97）に載る。

### 生成側のルール（このスキルのスクリプト動作）

- **hand-authored skeleton**: `/30s` 形式（30fps 的にフレーム数で書く人間向け書き方）で書いて構わない
- **`fix_video_assets.py` の変換**: `/30s` 相対 in-point → asset.start + in-point × 1001 の `/30000s` 絶対座標に変換する
- **既に絶対座標（/5000s や /1001s など FCP export 由来の最簡約形）になっている値は触らない**。既に正しい値なので正規化する意味がない（import 的には等価）
- 逆に言うと、rerunnable tool とはいえ「FCP export 由来の XML を再正規化するツール」ではない。想定入力はあくまで skeleton 手書き XML

差分を取るときは `references/fcp-canonical-export-1.13.fcpxml` をベースラインに、**値（絶対時間）が一致すれば denominator 表記の違いは気にしない**。

### optional 属性（FCP が export に付けるが import 必須ではない）

- `uid` / `sig`（media content hash）— 省略可
- `videoSources="1"`、`audioRole="dialogue"`、`<audio-channel-source>` — 省略してもインポートは通る
- メタデータ（`<md key="...">`）— 不要

最初は必須属性だけで通し、必要になったら足す。

---

## 3. TC → /30000s の変換

DF (drop-frame) timecode をフレーム数に変換するロジックは地味に間違えやすい。スクリプトを用意してある。

### [scripts/tc_to_frames.py](scripts/tc_to_frames.py)

```bash
python3 ~/.claude/skills/dji-fcpxml/scripts/tc_to_frames.py /path/to/DJI_xxx.MP4
# 出力: clip_id  timecode  DF_frames  start_numerator(分母30000)
```

複数ファイル一括：

```bash
python3 ~/.claude/skills/dji-fcpxml/scripts/tc_to_frames.py /Volumes/KIOXIA/.../Video/*.MP4
```

### 計算式（ロジック把握用）

```
NDF_frames = h*108000 + m*1800 + s*30 + f
drops = (total_min - floor(total_min / 10)) * 2
DF_frames = NDF_frames - drops
start_numerator = DF_frames * 1001
# → <asset start="{start_numerator}/30000s">
```

### 既存 XML の一括書き換え

設計書ベースで粗編集 XML を手作成した後、実ファイル準拠に直すには：

[scripts/fix_video_assets.py](scripts/fix_video_assets.py) — 指定パスの fcpxml について、videoアセットの `start`/`duration`/`format` を実ファイルの TC/frames に合わせて書き換える。タイムラインの `asset-clip.start` も `asset.start + in-point` に自動計算。

```bash
python3 ~/.claude/skills/dji-fcpxml/scripts/fix_video_assets.py \
  --xml /Volumes/KIOXIA/.../full-skeleton.fcpxml \
  --video-dir /Volumes/KIOXIA/.../Video/
```

バックアップ（`.bak`）を自動で作る。

**pre-flight 検証**: 書き込み前に XML の自己整合性をチェック、以下の異常で exit 1 + XML無変化:

- XML で宣言された `<asset id="v_NNNN">` に対応する実ファイルが `--video-dir` に無い
- `<asset-clip ref="v_NNNN">` が宣言されていない video asset を参照している（dangling ref）
- `/30000s` denominator の numerator が 1001 の倍数でない（off-frame）。29.97fps の frame boundary 違反を FCP に取り込む前に弾く。人間/AI が `N × 1001` の暗算で下位桁の繰り上がりを見落とすと起きる（例: `3480 × 1001 = 3483480` を `3483450` と書く）

補足: この off-frame チェックは **字面どおり `/30000s` の分子が `1001` 倍数か**を見ている（属性名は区別しない）。目的は「手書きタイムライン値の typo」をFCPに渡す前に落とすこと。

実務上は **`asset.start` が camera TC の `/30000s` 表記で、`asset-clip.start` が別 denominator（`/5000s` など）に最簡約されている**ケースがあり、そのとき本文ルール（絶対時刻の一致）との読み比べが必要。pre-flight が誤爆したら、まず **分母が `/30000s` になっているか**、次に **値が frame boundary として意味を持つ中心か**を切り分ける。

「部分更新で stale な XML を静かに正本化する」「人間/AI の typo をFCPに押し付ける」事故を防ぐ設計。

**テスト**: 変換ロジックと pre-flight を直接検証するテストが `tests/` にある:

```bash
python3 ~/.claude/skills/dji-fcpxml/tests/test_rewrite.py
```

カバー範囲: skeleton→29.97変換、idempotency、mixed input (skeleton+FCP export) での rerun、dangling ref / missing file / off-frame numerator の pre-flight。

---

## 4. トラブルシューティングのフローチャート

import で warning / エラーが出たとき、以下の順で切り分ける。**2回試行しても直らなかったら即座に手順5に飛べ**。

1. **ファイルが見える**: src のパス解決。SDカードならマウント（`diskutil mount diskNs1`）
2. **ffprobe が通る**: 実ファイルが壊れていないか、フレーム数・TC が読めるか
3. **"invalid edit"** が video asset-clip に集中 → **asset.start が TC と不一致**（本スキル最大の落とし穴）
4. **"item is not on an edit frame boundary"** → timeline 値が 30fps denominator。`/30000s` に変換必要
5. **原因不明 / 2回試行で解決しない** → **FCP 正規 export で差分を取る**（次項）

### FCP Probe XML の取り方（最重要）

1. FCP で**新規 Event** 作成（例: `Probe`）
2. 新規 Project 作成。フォーマットは **撮影素材と完全一致**させる（3840×2160, 29.97p, stereo/48k）
3. 対象素材を1本 import（Copy to library は OFF 確認）
4. タイムラインにドラッグ
5. **必ず先頭と末尾を両方トリム**（3秒/2秒程度）。  
   **トリム必須の理由**: `start="0/1s"` の特殊ケースでは FCP の厳密仕様が表に出ない。トリムすると asset-clip の start が「asset.start + 相対オフセット」で書かれ、正規仕様が露出する
6. `File` → `Export XML...` → fcpxml 1.13 を選択
7. 出力された `.fcpxmld/Info.fcpxml` を読み、自分の XML と差分を取る
8. 差分のうち import 必須な属性（start, duration, format, denominator）だけ反映

---

## 5. 推奨プロジェクトレイアウト

外部 SSD でもローカルでもよい。**SD 直読みは避け**、Video はコピー先を `media-rep@src` に書く。

```
<PROJECT_ROOT>/
├── <library>.fcpbundle/   # FCP ライブラリ
├── Video/                 # 映像素材（DJI 等）
├── MusicSE/               # BGM / 環境音 / SE
├── Graphics/              # PNG / SVG オーバーレイ
├── edit/                  # .fcpxml / .fcpxmld / *.bak
└── docs/                  # 設計書・ショットリスト（任意のワークフロースキルが参照）
```

- 企画・尺・ナレーション方針 → 任意のドメインワークフロースキル（例: `docs/optional-domain-workflow.md`）
- FCPXML の**書き方と修正** → 本スキル + `fcp-*` セット

---

## 関連スキル

- **fcp-titles**: title要素 (Basic Title)、字幕・テロップ
- **fcp-image-overlay**: video要素 (PNG/SVG装飾)、帯・box・ロケーションカード
- **fcp-audio**: audio配置 (BGM・環境音・SE)、 audio-only lane、 fadeIn/fadeOut
- **fcp-spine-edit**: spine構造編集、kindベース尺リサイズ、clip削除diff、resource ID 動的取得
- **fcp-library-ops**: library運用、Copy to library、SD運用、Transcoded Media

## 関連メモリ（任意）

Claude Code 等でセッション横断メモリを使う場合、同テーマの `feedback_fcpxml_*.md` をプロジェクトに置くと再現性が上がる。本リポジトリの SKILL 本文が正本。

---

## 最後に — このスキルを使うときの姿勢

**推測で XML をいじるな。ffprobe で測れ。Probe XML を取れ。**  
FCPXML は仕様が厳密。人間の直感は高確率で外れる。観測した数値だけを信じる。
