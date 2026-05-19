# references

## `fcp-canonical-export-1.13.fcpxml`

Final Cut Pro から Export XML（FCPXML 1.13）した **実サンプル**。

- `media-rep@src` や `library@location` は `<PROJECT_ROOT>` プレースホルダ。clone 後は自分の `file://` に置き換える。
- macOS の `<bookmark>` 要素は **公開版では除去**（ローカルパスが base64 で埋まるため）。自環境の正規形が必要なら FCP から再 export する。
- 数値（`start` / `duration` / `format@frameDuration`）と要素構造が本リポジトリの正規形の参照。

新規プロジェクトでは、まず FCP で1クリップだけ import → export し、自環境用の canonical を別ファイルとして追加してよい。
