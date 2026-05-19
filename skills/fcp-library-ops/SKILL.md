---
name: fcp-library-ops
description: >-
  Final Cut Pro の library 運用に関するノウハウ。Copy to library 設定、SDカード運用
  (NTFS / mount issue / DJI OP3)、Event 間の media 共有挙動、Transcoded Media と
  Analysis Files のキャッシュ管理、library サイズ抑制、 import 前ゲート
  (xmllint で DTD valid + asset uid 整合性チェック) を扱う。
  「library」「Copy to library」「media management」「Transcoded Media」「キャッシュ」
  「SD」「DJI OP3 SDカード」「diskutil mount」「fcpbundle」「外付け SSD」「Storage Locations」
  「ライブラリが大きい」「ディスク容量」「import error」「uid 衝突」「unique identifier」
  「media already exists in the library」「xmllint」「DTD valid」「import 前チェック」等で発動。
  XML仕様・spine編集は dji-fcpxml / fcp-spine-edit、 overlay系は fcp-titles / fcp-image-overlay。
---

# fcp-library-ops — FCP library運用とmedia管理

Final Cut Pro の `.fcpbundle` library と外部 media (SDカード / 外付け SSD) の運用ノウハウ。「ライブラリが数百GBに膨れた」「SDカードが見えない」「Transcoded Media を消したい」などのトラブル対処と、最初から肥大化を防ぐ設定を扱う。

## 核となる教訓

- **「Copy to library」を OFF**にしないと media が library に複製されてサイズが膨らむ
- **SD のファイルシステムは環境依存**（exFAT/FAT32/NTFS など）。macOS での read/write 可否もそれに依存する。**断定せず `diskutil info` で確認**する
- **Event 間で media は共有されない** → 同じソースを複数 Event に import すると Transcoded が重複生成
- **Library Properties → Storage Locations は別設定**（コピー先指定であって、「コピーしない」設定ではない）

## 1. Copy to library を OFF にする

`Final Cut Pro → Settings → Import` タブ → **Copy to library media folder** のチェックを外す。

これで import 時に動画が library 内にコピーされず、外部参照のままになる。

### 注意点

- **Library Properties → Storage Locations は別設定**。これは「コピーする場合にどこへコピーするか」の指定で、「コピーしない」設定ではない。混同しやすい
- 一度 ON の状態で import した素材は、`.fcpbundle/EventName/Original Media/` にコピー済み。後から OFF にしてもコピー済み media は残る。手動で削除する必要がある
- ON のままだと library が **数百GB** に膨れる（特に4K HEVC の DJI素材）

### library 内の media 配置

```
.fcpbundle/
├── <EventName>/
│   ├── Original Media/         ← Copy to library ON で入る原本コピー
│   ├── Transcoded Media/       ← FCPが自動生成する proxy / optimized media
│   ├── Analysis Files/         ← shake/face detection等の分析結果
│   └── CurrentVersion.fcpevent
```

## 2. Event 間で media は共有されない

同じソースファイルを複数の Event に import しても、トランスコード済み media (Transcoded Media / Analysis Files) は **Event ごとに重複生成**される。

- 同じ library 内で XML import と通常 import を併用すると二重化する
- 試行錯誤で「probe」「test1」「test2」のように Event を増やすと、各 Event で同じ素材の Transcoded を持つ

### 対策

- 試行錯誤用の Event は、終わったら **library から削除** (Right-click → Move to Trash)
- 不要な Event の Transcoded Media を直接削除する場合は **まずパスを人間が検証**してから（下の「破壊的操作ゲート」）

## 3. SDカード運用（DJI OP3 等）

### ファイルシステム確認（先にこれ）

```bash
diskutil list
diskutil info diskXsY
```

ここで **File System Personality** を確認してから読み取り専用かどうかを判断する。

### macOS で read-only になりがちなケース

- **NTFS**: 追加ドライバ無しの環境では **read-only** になりやすい
- **exFAT/FAT32**: たいてい read/write 可能だが、取り外し手順を誤ると壊れる

撮影分の整理・削除が書き込み必須なら、**カード上で直接いじらず**、まず外付けSSDへコピーして編集するのが安全。

### 自動マウントしない問題

時折、SD カードが macOS で自動認識されない:

```bash
# 検出はするが /Volumes に出ない
diskutil list

# 手動マウント
diskutil mount disk6s1   # disk番号は環境依存
# → /Volumes/DJI_OP3 が出現
```

### SD 依存を避ける

長期 editing では SD依存を避ける:

```bash
# 必要ファイルを外付け SSD にコピー (read-only NTFS から外付け SSD へ)
cp -R /Volumes/DJI_OP3/DCIM/Movies/ /Volumes/<SSD>/<project>/Video/

# XML の src を書き換え（まずバックアップ）
cp -R /path/to/project.fcpxmld "/path/to/project.fcpxmld.$(date +%Y%m%d-%H%M%S).bak"

# sed はパスに `%` などが混じると事故りやすい。まず dry-run:
grep -n "file:///Volumes/DJI_OP3/" /path/to/project.fcpxmld/Info.fcpxml | head

# 問題なければ置換（実行後も grep で残りが無いことを確認）
sed -i '' 's|file:///Volumes/DJI_OP3/|file:///Volumes/<SSD>/<project>/|g' /path/to/project.fcpxmld/Info.fcpxml
```

置換後は **`xmllint --noout /path/to/project.fcpxmld/Info.fcpxml`** → **FCP で import** までがセット。

これで SD抜き差しの度に library が壊れる事故を避けられる。

## 破壊的操作ゲート（必須）

ターミナルで library / XML を触るとき、最低これだけ守る:

1. **FCP を終了**（未保存が無いことを確認。`killall` は最終手段）
2. **対象パスを `ls` / Finder で実在確認**（`rm -rf` のTypoは復旧不能）
3. **バックアップ**（`.fcpbundle` は丸ごと、`fcpxmld` はフォルダごと）
4. **変更後に import / 再生確認**（静的に成功したつもりにならない）

## import 前ゲート（必須）— XML valid + uid 整合性

スクリプト生成 fcpxml を FCP に import する前に、 必ず以下2つをチェックする。

### (A) DTD / XML 構造 valid

```bash
xmllint --noout /path/to/.fcpxmld/Info.fcpxml
```

無出力 = OK。 エラーが出たら閉じタグ漏れ・属性 escape 漏れ等を修正。

### (B) asset uid 整合性 — FCP library 既存 entry との衝突回避

**症状**: 「The media already exists in the library with a different unique identifier. (uid="..." : /fcpxml[1]/resources[1]/asset[N]/@uid) The file XXX.MP4 cannot be imported again with a different unique identifier」

**原因**: 同じ media file が library に既に登録されているが、 新 fcpxml が**異なる uid** を指定している。 FCP は file ↔ uid の 1:1 対応を強制する。

**根治策**: 既存 fcpxml backup から該当 file の uid を抽出して再利用する。 不明な file には uid 属性を**省略する** (FCPXML 1.13 で uid は #IMPLIED = optional)。

```python
import re, glob
from pathlib import Path

def load_known_uids(backup_glob: str) -> dict[str, str]:
    """既存 fcpxml backup から file_basename → uid マップを構築"""
    uid_map: dict[str, str] = {}
    pattern = re.compile(
        r'<asset id="[^"]+" name="([^"]+)"[^>]*uid="([A-F0-9]+)"',
        re.DOTALL,
    )
    for path in sorted(glob.glob(backup_glob)):
        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception:
            continue
        for m in pattern.finditer(content):
            name = m.group(1)
            uid = m.group(2)
            if name not in uid_map:
                uid_map[name] = uid
    return uid_map

# 例:
# load_known_uids("<PROJECT_ROOT>/edit/series-vlog.fcpxmld*/Info.fcpxml")
# → 既存 backup 全部から uid を集約
```

asset 出力時の helper:

```python
def asset_uid_attr(name: str, uid_map: dict[str, str]) -> str:
    u = uid_map.get(name)
    return f'uid="{u}" ' if u else ""  # 不明なら省略
```

**uid を省略してよい場合**:

- backup に該当 file が無い (新規 file、 もしくは backup 取得前に library 登録された file)
- → FCP は path で resolve、 既存 entry があればそれを使う、 無ければ新規登録

**uid を必ず指定すべき場合**:

- backup 内で uid が判明している file
- → 同じ uid を維持しないと library 側で別 entry とみなされる (or import error)

### import 前ゲートのチェックリスト

| ゲート    | 検証コマンド / 確認                       | NG時の対処                                |
| --------- | ----------------------------------------- | ----------------------------------------- |
| DTD valid | `xmllint --noout Info.fcpxml`             | 出力エラーから閉じタグ・escape 漏れを修正 |
| uid 整合  | backup uid 抽出 + uid map 適用            | uid 不明の asset は uid 属性省略          |
| 物理 path | `ls` で各 `media-rep src=` の実在確認     | 切れていればコピー / src 書き換え         |
| frame整合 | `/30000s` denominator 確認 (29.97 NDF/DF) | `1001` の倍数チェック                     |

これら 4 ゲートを通れば「import 通る」 確率が大幅に上がる。 通らない場合は一段ずつ症状を切り分け。

## 4. Transcoded Media のキャッシュ管理

FCPは import / playback 時に自動でトランスコードや analysis を行い `Transcoded Media/` `Analysis Files/` を生成する。これが library 肥大化の主因。

### 削除して空き容量を取り戻す

```bash
# まず通常は GUI で十分:
# Final Cut Pro を終了 → Finder で対象 Event フォルダを確認 → Transcoded Media をゴミ箱へ

# どうしてもコマンドでやるなら（上の「破壊的操作ゲート」を全部クリアしてから）
osascript -e 'tell application "Final Cut Pro" to quit' || true

DEST_TM="/path/to/<library>.fcpbundle/<EventName>/Transcoded Media"
DEST_AF="/path/to/<library>.fcpbundle/<EventName>/Analysis Files"
ls -ld "$DEST_TM" "$DEST_AF"   # ここでパスが想定通りか人間が確認する

rm -rf "$DEST_TM" "$DEST_AF"
```

### FCP内から削除

`File → Delete Generated Library Files…` で対話的に:

- All proxy media
- All optimized media
- All render files
- All Analysis Files

を選択削除可。これは安全なやり方。

### 自動生成を抑制

`Final Cut Pro → Settings → Playback`:

- **Background tasks**: optimized/proxy media の生成タイミング制御
- **Background render**: OFFにすると render files が自動生成されなくなる（ただし再生がカクつく）

## 5. Project / Event のバックアップ

### XML export での保全

`File → Export XML…` で `.fcpxmld` バンドルを作る。これが**最も safe な project スナップショット**。

- 中身は plain XML (`Info.fcpxml`) なので diff / merge 可
- library が壊れても XML から re-import で project を復元できる
- バックアップは **バンドル全体（フォルダ）** をコピー: `cp -R foo.fcpxmld foo.fcpxmld.YYYY-MM-DD.bak`

### library 自体のスナップショット

```bash
# FCPを閉じてから
cp -R /path/to/<library>.fcpbundle /path/to/<library>.fcpbundle.YYYY-MM-DD.bak
```

ただしサイズが大きいので、Transcoded を消してからコピーすると軽い。

## 6. 既知の落とし穴

- **「Copy to library」を OFF にしたつもりが Storage Locations だった**: 別設定、混同しやすい
- **import後に Original Media が library 内にある**: ON状態で import済み。手動 rm で削除可、ただし FCP は途切れる場合あり (再import 推奨)
- **SD 抜き差しで library が壊れる**: src パスが切れる。外付け SSD にコピーして src 書き換えで安定化
- **Transcoded Media を削除したらFCPが激重**: 起動後に再生成中。バックグラウンドで完了するまで待つ
- **同じ project名で複数 Event 作成**: FCP 内では区別つくが、 file system では `<library>.fcpbundle/<EventName>/<Project>/` と階層が深く混乱
- **新生成 fcpxml に独自 uid を付ける**: 既に library に登録済の file を異なる uid で参照すると import error (`The media already exists in the library with a different unique identifier`)。 既存 backup から uid を抽出するか、 uid 属性を**省略する** (FCPXML 1.13 で uid は #IMPLIED)
- **xmllint だけで通せたつもりになる**: DTD valid でも uid 衝突や物理 path 切れで import 落ちる。 import 前ゲート 4項目 (DTD / uid / path / frame整合) を全部通す

## 関連スキル

- **dji-fcpxml**: 基本のFCPXML仕様 (asset.start / format / TC変換)
- **fcp-spine-edit**: spine編集後に library media のリフレッシュが必要な時
- **fcp-titles / fcp-image-overlay**: overlay 編集後の re-import 手順

## 関連メモリ

- `feedback_fcpxmld_bundle.md` — `.fcpxmld` バンドル形式を作業基準にする運用
- `feedback_fcpxml_uid_consistency.md` — asset uid は library 既存 entry と一致 / 不明なら uid 省略
