# Security Policy

## サポート対象

| ブランチ | サポート |
| --- | --- |
| `main` | あり |
| その他 | なし |

## 脆弱性の報告

**公開 Issue に exploit 手順や未公開の個人情報を書かないでください。**

1. [GitHub Security Advisories](https://github.com/kiwamust/fcp-six-skills/security/advisories/new) から **Private vulnerability report** を作成する  
2. 再現手順・影響範囲・想定修正案があれば記載する  
3. 48時間以内に受領の返信を目指す（対応 SLA はベストエフォート）

メール等の別経路が必要な場合は、Advisory 内で連絡先を共有してください。

## スコープ

| 対象 | 例 |
| --- | --- |
| 含む | `scripts/*.py` の意図しないファイル書き込み・パストラバーサル、悪意ある FCPXML テンプレの推奨 |
| 含まない | Final Cut Pro 本体、第三者 BGM/素材、利用者の `file://` メディアパス設計 |

## 利用者向け注意（リポジトリ利用時）

- **`scripts/install.sh` は信頼できる clone 元でのみ実行**（symlink を `~/.claude/skills` に作成する）
- **Issue / PR に実メディアの `file://` パス・`.fcpxmld` 全文・API キーを貼らない**
- `references/*.fcpxml` は構造サンプル。本番パスは各自の環境で FCP export から取得する
- エージェントに FCPXML を書かせる場合、**import 前にバックアップ**（`.fcpxmld` フォルダごと `cp -r`）

## 公開リポジトリのハードニング（メンテナ向け）

- `main` への **force push 禁止**・**CI 必須**（branch protection、`dji-fcpxml`）
- Secret scanning / push protection（GitHub 側）
- Dependabot security updates + GitHub Actions 週次更新
- CI は最小権限（`contents: read` のみ）
- Wiki 無効（スパム・改ざん面の削減）

初期コミット履歴に実パスが残っている場合がある。履歴から完全除去するには `git filter-repo` 等が必要（通常は最新版の redact で足りる）。
