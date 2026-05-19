# ドメイン別ワークフロースキル（任意）

`fcp-six-skills` は **FCPXML 実装プロトコル** に特化している。旅行 Vlog・企業 PV など、企画〜納品までのフェーズ管理は **別スキル** で足す。

## 分離の理由

- 実装スキル: カメラ・fps・XML 構造はプロジェクト横断で再利用可能
- ワークフロースキル: 設計書パス、尺、BGM 方針、納品先はプロジェクト固有

## 足し方（例）

1. 自リポジトリまたは private skills に `my-vlog-workflow/SKILL.md` を置く
2. frontmatter の `description` で「Vlog」「編集」「納品」等のトリガーを書く
3. 本文で「XML 編集は `dji-fcpxml`、字幕は `fcp-titles`…」と **本セットへの委譲** を明記
4. 設計書・素材ルートは **環境変数またはプロジェクト相対パス** で記述（`~/Desktop/...` のハードコードは避ける）

## 推奨ディレクトリ（実装スキル側の前提）

```
<PROJECT_ROOT>/
├── <name>.fcpbundle/     # FCP ライブラリ
├── Video/                # 映像素材（ライブラリ外コピー推奨）
├── MusicSE/              # BGM / 環境音 / SE
├── Graphics/             # PNG / SVG オーバーレイ
├── edit/                 # .fcpxml / .fcpxmld / バックアップ
└── docs/                 # 設計書・ショットリスト（ワークフロースキルが参照）
```

`dji-fcpxml` の `media-rep@src` は常に **実在パスの file:// URI** にすること。プレースホルダのまま import しない。
