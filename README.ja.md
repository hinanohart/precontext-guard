# precontext-guard

> AI アシスタントの "コンテキストウィンドウ" に秘密情報が流れ込む前に、
> その元になるコマンド自体を実行前に止める。

`precontext-guard` は [Claude Code](https://docs.anthropic.com/claude-code)
の `PreToolUse` フックとして動く 1 ファイルのスクリプトです。アシスタント
が `Bash` を実行しようとした瞬間、コマンド文字列を検査して、**「実行され
たら標準出力にそのまま秘密情報が出るような形」のものだけ拒否**します。

例:

- `gh auth token` — GitHub の個人アクセストークンが直接 stdout に出る
- `cat .env` — `.env` の中身を全部 stdout に出す
- `echo $OPENAI_API_KEY` — 環境変数の値を出す
- `aws sts get-session-token` — STS のクレデンシャルを返す
- `op read 'op://...' --reveal` — 1Password の保存済み秘密を出す

これらが拒否されると、トークンの値はチャットの履歴・モデルプロバイダの
リクエストペイロード・付随するログ／リプレイ機構のどこにも記録されません。

`gitleaks` や `trufflehog` のように **コミット後／push 前に git ツリーを
スキャン** するツールは違うレイヤーを守ります。`precontext-guard` は
**コマンドが実行される前** で止めるので、より上流です。両方併用するのが
推奨。

詳しくは [README.md](README.md) (英語) と
[docs/threat-model.md](docs/threat-model.md) を参照してください。

---

## 30 秒インストール

```bash
git clone https://github.com/OWNER/precontext-guard.git
chmod +x precontext-guard/precontext-guard
```

`~/.claude/settings.json` に
`examples/settings.json.fragment` の内容をマージしてください。

実行時依存はありません (Python 3.10 以降の標準ライブラリのみ)。

---

## ブロック時の表示

```
[precontext-guard] BLOCKED — gh auth token prints the literal access token;
capture it via '!' prefix in your own shell instead.

How to run it safely:
  - From your own shell directly: prefix the command with '!' so it runs
    locally and its output never reaches the assistant.
        e.g.  ! gh ...
  - Or capture into an environment variable first, then have the
    assistant use that variable by name (without ever reading its
    value):
        ! read -rs MY_TOKEN; export MY_TOKEN
        # in chat afterwards:  invoke as $MY_TOKEN
```

(エラー文は assistant が読んで再試行を判断する目的で英語固定です。)

---

## 設定

| 環境変数            | 役割                                                              |
| ------------------ | ----------------------------------------------------------------- |
| `PCG_OVERRIDE=1`   | 次の 1 回だけバイパス (1 ショット例外)。                            |
| `PCG_RULES_FILE`   | `allow`/`deny` パターンを追記する JSON 設定ファイルへのパス。       |
| `PCG_LOG_DIR`      | 監査ログの出力先。既定: `$XDG_STATE_HOME/precontext-guard`。         |

監査ログ (`audit.jsonl`) はローカルファイルのみで、ネットワーク送信は
一切ありません。

---

## 制限事項 (重要)

- **正規表現はあくまで heuristic**: 攻撃者が `bash -c 'ca''t .e''nv'`
  のように難読化すれば抜けられます。事故防止用の guard rail であって、
  能動的攻撃への防御ではありません。
- **複合コマンド** (`bash -c "..."`, `eval`, here-doc) は単一文字列
  として検査されるので、難読化に弱い。
- **allow リストは意図的に狭い**: 想定外の安全コマンドは "gray-allow"
  として通しつつ監査ログに記録します。デフォルト deny にしたい場合は
  `PCG_RULES_FILE` で allow を絞り、最後に `.*` の deny を追加して
  ください。
- **正しい秘密管理の代替ではありません**。短命トークン、スコープ限定
  クレデンシャル、シークレットマネージャ等を別途使ってください。

---

## ライセンス

[Apache-2.0](LICENSE)
