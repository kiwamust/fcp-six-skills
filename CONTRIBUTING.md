# Contributing

## 方針

- **再利用可能なプロトコル** を優先する（個人プロジェクトのパス・設計書名は入れない）
- 変更は **再現手順** とセットで（FCP export との差分、テスト、失敗時の症状）
- 推測で属性を足さない。不明なら「FCP 正規 export を取って写経」を README / SKILL に書く

## 開発

```bash
git clone https://github.com/kiwamust/fcp-six-skills.git
cd fcp-six-skills
./scripts/install.sh claude   # 任意: ローカル symlink
cd skills/dji-fcpxml && python3 tests/test_rewrite.py
```

PR では `dji-fcpxml` のテストが CI で通ることを確認する。

## スキル追加・分割

新スキルを足す場合:

1. `skills/<name>/SKILL.md`（frontmatter + 単一責任）
2. README の一覧と依存図を更新
3. 既存スキルの「関連スキル」からリンク
4. `scripts/install.sh` は `skills/*/` を自動列挙するため変更不要

## パス表記

| OK                                    | NG                             |
| ------------------------------------- | ------------------------------ |
| `<PROJECT_ROOT>/Video/foo.MP4`        | `/Volumes/.../srilanka/...`    |
| `file:///path/to/media.mp4`（汎用例） | `~/Desktop/work/.../設計書.md` |
| 「任意のワークフロースキル」          | 私有 skill 名への必須依存      |

`references/*.fcpxml` 内の実パスは **サンプル export** として残してよい（`references/README.md` を参照）。
