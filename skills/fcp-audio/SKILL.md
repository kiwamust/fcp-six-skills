---
name: fcp-audio
description: >-
  Final Cut Pro の audio 系 (BGM, 環境音 ENV, SE, audio-only asset-clip) を FCPXML で実装する。
  audio asset の正規構造、 lane=-1 への audio-only 配置、 `<adjust-volume>` の amount 指定、
  `<fadeIn>` / `<fadeOut>` (子要素として `<param name="amount">` 内)、 duration単位 `/720000s` 、
  audio role (music/dialogue/effects)、 audio file 形式 (mp3/m4a/wav)、
  Channel EQ filter (`<filter-audio>` で presetID指定、 `06 Mastering` 系プリセット) を扱う。
  「BGM」「audio fade」「fadeIn」「fadeOut」「クロスフェード」「audio-only」「lane=-1」
  「adjust-volume」「audioRole」「環境音」「ENV」「SE」「sound effect」「Channel EQ」
  「audio filter」「filter-audio」「マスタリング」「音色整え」等で発動。
  spine構造編集は fcp-spine-edit、基本のFCPXML仕様は dji-fcpxml、上位ワークフローは travelVlog skill。
---

# fcp-audio — FCP の audio 配置と fade

`<asset-clip lane="-1">` (audio-only) として BGM や 環境音、 SE を spine に配置する。 オーディオ専用 lane (lane=負値) で配置することで、 video lane と並列に再生される。 audio fade は **`<adjust-volume>` 内 `<param name="amount">` の子要素** として書く。

## 核となる教訓

- **audio lane は負数** (lane=-1, -2, -3...): video lane (正数) と独立、 並列再生
- **fade は `<adjust-volume>` 内 `<param name="amount">` の `<fadeIn>` `<fadeOut>`**: 推測でasset-clip 直下に書くと効かない
- **fade duration の単位は `/720000s`**: video の `/30000s` とは違う (24倍精度)
- **audio asset の duration は `/1s` でも `/30000s` でも OK**: audio sample-base、 frame整合不要

## 1. audio asset の正規構造

```xml
<resources>
    <asset id="g_bgm1" name="BGM1 Aesthetic Lofi"
           uid="..." start="0/1s" duration="144/1s"
           hasVideo="0" hasAudio="1"
           audioSources="1" audioChannels="2" audioRate="44100">
        <media-rep kind="original-media"
                   src="file:///path/to/bgm1.mp3"/>
    </asset>
</resources>
```

| 属性            | 値                                         |
| --------------- | ------------------------------------------ |
| `hasVideo`      | `"0"` (audio-only)                         |
| `hasAudio`      | `"1"`                                      |
| `audioSources`  | `"1"` (mono) or `"1"` (stereo, 1ペア)      |
| `audioChannels` | `"2"` (stereo)                             |
| `audioRate`     | `"44100"` (mp3標準) or `"48000"` (m4a標準) |
| `start`         | `"0/1s"` (mp3冒頭)                         |
| `duration`      | `"<sec>/1s"` (mp3実duration)               |

## 2. spine上の audio asset-clip (lane=-1)

典型は **映像の `<asset-clip>` の子要素**として繋ぐ（connected clip）。これなら「どのカットに紐づくBGMか」が構造で固定される。

```xml
<spine>
  <asset-clip ref="rVideo" lane="1"
              offset="0/30000s"
              name="Scene A"
              start=".../30000s"
              duration="300300/30000s">

    <!-- audio-only は lane が負数 -->
    <asset-clip ref="g_bgm1" lane="-1"
                offset="<親asset-clip.start値>"
                name="BGM1"
                start="0s"
                duration="3132/30s"
                audioRole="music">
      <adjust-volume amount="-12dB"/>
    </asset-clip>

  </asset-clip>
</spine>
```

別パターンとして spine 直下に `lane="-1"` を並べる構成もあるが、プロジェクトによって見通しが悪くなりやすい。**迷ったら FCP で実際に繋いだ形を Export XML して写経**する。

| 属性        | 値                                                            |
| ----------- | ------------------------------------------------------------- |
| `lane`      | **`-1`** (audio-only) - 負数で audio専用 lane                 |
| `audioRole` | `"music"` (BGM) / `"dialogue"` (会話) / `"effects"` (SE)      |
| `start`     | `"0s"` (mp3冒頭から) or `"<offset_in_mp3>/30000s"` (途中から) |
| `duration`  | spine上の表示時間                                             |

### 配置場所

audio asset-clip は典型として **対象の video `<asset-clip>` の子要素** (connected clip) として書く。親 asset-clip の duration を超えても OK（設計次第で「シーン全体に被せる」もできる）。

## 3. audio fade (fadeIn / fadeOut)

**正規構造** (FCP正規exportから確定):

```xml
<asset-clip ref="g_bgm1" lane="-1" ...>
    <adjust-volume amount="-12dB">
        <param name="amount">
            <fadeIn type="easeIn" duration="2825569/720000s"/>
            <fadeOut type="easeIn" duration="756277/720000s"/>
        </param>
    </adjust-volume>
</asset-clip>
```

### 重要ポイント

- **`<fadeIn>` `<fadeOut>` は `<param name="amount">` の子**: asset-clip 直下や `<adjust-volume>` 直下ではない
- **duration の単位は `/720000s`** (24倍精度: 30000 × 24 = 720000)
- **type 属性**: `"easeIn"` / `"easeOut"` / `"easeInOut"` / `"linear"`

### duration 計算式

```
N/720000s = N/720000 秒
1.0秒 = 720000/720000s
1.5秒 = 1080000/720000s
2.0秒 = 1440000/720000s
3.0秒 = 2160000/720000s
```

### 設計ポイント (BGM 4本ミックスの実例)

| BGM              | 役割         | fadeIn          | fadeOut         |
| ---------------- | ------------ | --------------- | --------------- |
| 先頭 (Intro直後) | 世界に入る   | **長め (3-4s)** | 短め (1s)       |
| 中盤 1           | crossfade    | 短め (1s)       | 中 (3-4s)       |
| 中盤 2           | crossfade    | 短め (1s)       | 中 (2-3s)       |
| 末尾 (Outro前)   | 静かに閉じる | 短め (1s)       | **長め (8-9s)** |

中間境界では crossfade (前BGM の長めfadeOut + 次BGMの短めfadeIn が重なる) で自然に遷移。

## 4. クロスフェード設計

連続する2つの audio-clip 間でクロスフェード:

```
       前BGM       次BGM
       =====       =====
fadeOut --→        ←-- fadeIn
       |  重複  |
       offset_2 - offset_1 < duration_1
```

- 前BGM の `fadeOut` 末尾と 次BGM の `fadeIn` 先頭が同時刻に重なるよう offset/duration を計算
- 重なり時間 = max(fadeOut, fadeIn) ≈ 1.5-3秒が自然

## 5. audioRole の選択

| Role                                   | 用途                                                          |
| -------------------------------------- | ------------------------------------------------------------- |
| `"music"`                              | BGM、 主題曲                                                  |
| `"dialogue"` / `"dialogue.dialogue-1"` | ナレーション、 現地会話                                       |
| `"effects"` / `"effects.effects-1"`    | SE (whoosh, water, temple bell 等)                            |
| `"natural"`                            | 環境音として割り当てたいケースで **たまに**見えるが、環境依存 |

FCP は role ごとに track を分ける → ミキシングしやすい。

**`natural` は推測で書かない**。自分の library / テンプレで本当にその文字列が成立するかは、対象クリップを **FCP → Export XML** して `audioRole="..."` を確認する。成立しない場合は、プロジェクトの運用に合わせて **`effects` 系に寄せる**など代替を選ぶ。

## 6. Channel EQ (audio filter)

BGM の音色を整える時に使う。 Final Cut Pro 標準の `Channel EQ` (Apple AudioUnit)。 Logic 由来の preset (Drums / Keyboards / Guitar / Horns / Voice / Mastering / EQ Tools) があり、 BGM には **`06 Mastering` 系** (Final Mix - Pop / Rock / Smooth / Bright 等) が無難。

### 正規構造

```xml
<resources>
    <effect id="rN" name="Channel EQ" uid="AudioUnit: 0x61756678000000ec454d4147"/>
</resources>

<spine>
    <asset-clip ref="rX" lane="-1" name="BGM..." ...>
        <adjust-volume amount="-15dB">
            <param name="amount">
                <fadeIn type="easeIn" duration="..."/>
                <fadeOut type="easeIn" duration="..."/>
            </param>
        </adjust-volume>
        <filter-audio ref="rN" name="Channel EQ" presetID="[2]06 Mastering/Final Mix - Pop.pst"/>
    </asset-clip>
</spine>
```

### 決定的ポイント

| 項目          | 真値                                        | 注意                                                               |
| ------------- | ------------------------------------------- | ------------------------------------------------------------------ |
| effect uid    | `AudioUnit: 0x61756678000000ec454d4147`     | 環境依存性は低いが念のため正規 export で確認                       |
| presetID 形式 | `[2]<カテゴリ>/<プリセット>.pst`            | 例: `[2]06 Mastering/Final Mix - Pop.pst`、 `[2]05 Voice/Warm.pst` |
| 配置          | `<adjust-volume>` の **後**                 | 直後に1行で `<filter-audio .../>`、 自己閉じ                       |
| ref           | resources で `name="Channel EQ"` を動的取得 | resource ID は再番号付けされる前提                                 |

### 一括適用パターン

1個の BGM に手で Channel EQ + preset を適用 → Export XML → 残り N-1 本に同じ `<filter-audio>` 行を `</adjust-volume>` 直後に挿入する。

```python
# 例: 各 BGM の </adjust-volume> 直後に 1行追加
TEMPLATE = '<filter-audio ref="r4" name="Channel EQ" presetID="[2]06 Mastering/Final Mix - Pop.pst"/>'
```

key/value をいじらず**1行追加**で済むので、 Typewriter のような param re-key と比べて軽い。

### preset 選定の指針

- **Drums / Keyboards / Guitar / Horns**: 楽器特化。 BGM全体に当てると不自然
- **Voice**: 人声前提。 BGM (とくに Lofi/Chill) に当てるとモコモコする
- **Mastering**: 全帯域バランスを整えるソフトな EQ。 **BGM全般に無難**
- **EQ Tools**: 単機能 utility (low cut のみ等)

迷ったら `06 Mastering / Final Mix - Pop` か `Final Mix - Smooth`。 楽器構成不明な royalty-free 素材集なら preset-default のまま乗せるだけでも効果がある (将来 Inspector で値を回せば全 BGM に適用される構造になる)。

### `<filter-audio>` と `<adjust-volume>` の併用

両方を併存させる典型 BGM 構造は:

1. `<adjust-volume>` で全体音量 + fade
2. `<filter-audio>` (Channel EQ など) で音色

順序: adjust-volume → filter-audio。 これは FCP正規 export と一致。

## 7. BPM同期（実験メモ / 通常運用では未使用）

この節は「発動させない」ためスキル説明のトリガーから外している。必要になったらツール化してから `description` に戻す。

clip 切り替えを BGM の拍に合わせる手法:

1. BGM mp3 から BPM 抽出 (`aubio tempo` / `librosa.beat.beat_track`)
2. **曲中の BPM変動も検出** (静的BPMだけでなく時間軸 BPM)
3. 各 BGM 区間で 1拍秒 = 60/BPM
4. 区間内の clip duration を 1拍 / 2拍 / 4拍 / 8拍 の倍数に設定
5. long = 4拍, standard = 2拍, short = 1拍, peak = 8拍 のような配分

ツール:

- `brew install aubio` → `aubio tempo file.mp3`
- Python: `librosa.beat.beat_track(y, sr)` で動的 BPM 取得

## 8. 既知の落とし穴

- **`<fadeIn>2s</fadeIn>` を asset-clip 直下に書く**: 効かない。 `<adjust-volume>` → `<param name="amount">` の中
- **fade duration を `/30000s` で書く**: FCPで誤解釈。 必ず `/720000s`
- **type 属性を省く**: 動作不安定。 明示的に `"easeIn"` 等を書く
- **lane を正数にする**: video lane と被って合成順序がおかしい。 audio は **必ず負数**
- **audioRole 未指定**: ミックスで分離できない。 必ず指定する（少なくとも `music` / `dialogue` / `effects` は確実）。`natural` を使うなら export で実在を確認してから
- **mp3 duration を frame整合する**: audio は frame整合不要。 `/1s` でOK
- **Channel EQ の preset を推測する**: `presetID="[2]..."` の prefix `[2]` を `[1]` で書く等、 細かい syntax は必ず**FCP正規 export を見る**。 推測すると preset が読み込まれず default に戻る silent failure
- **filter-audio を adjust-volume の前に書く**: FCP正規順序は adjust-volume → filter-audio。 逆順だと import で reorder されることはあるが推測しない

## 関連スキル

- **fcp-spine-edit**: spine構造編集 (audio-clipも spine の一部)
- **fcp-image-overlay**: video系 overlay (audio とは別レイヤー)
- **fcp-titles**: title (テキスト)、 audio とは独立
- **dji-fcpxml**: 基本のFCPXML仕様
- **travelVlog**: 上位ワークフロー (BGM選曲・配置の戦略決定)

## 関連メモリ

- `feedback_fcpxml_audio_fade.md` — fadeIn/fadeOut の正規構造 (実測ベース)
- `feedback_fcpxml_resource_id_dynamic.md` — audio asset id も再番号付け対象
- `feedback_music_selection_temperature.md` — BGM選曲は映像の温度で決める
