# Codex vs Claude Code 比較キット（実務2本勝負の再現用）

YouTube「11分 vs 111分｜Codex と Claude Code 実務比較【GPT-6.1】」で使った、**同じ仕事を Codex と Claude Code に同じ指示で丸投げして比べる**ための一式です。指示文・受け入れテスト・架空の領収書データ・両者が実際に作ったツール・相互レビューの結果・採点スクリプトが入っています。

> 動画では3本勝負でしたが、2本目（既存リポジトリの実バグ修正）は非公開リポジトリの中身なので、このキットには入れていません。入っているのは **ROUND 1（新規ツール作成）と ROUND 3（相手のコードをレビュー）** です。

## 先に結論（2026年10月13日・各お題1回ずつの計測）

| | Claude Code（Opus 5.5・effort max） | Codex（GPT-6.1 Sol・reasoning ultra） |
|---|---|---|
| R1 完了までの時間 | 110分47秒（テスト全通過は36分。その後、自分で別エージェントを立てて弱点探しと修正） | 10分50秒 |
| R1 受け入れテスト（8件） | 8/8 | 8/8 |
| R1 渡していないサンプル（3件・9項目） | 9/9 | 9/9 |
| R1 意地悪サンプル（12件・36項目） | 36/36 | 35/36（「R8.9.27」の略記の和暦だけ空欄） |
| R1 本体の行数 | 1,031行 | 212行（＋Swift 35行） |
| R3 相手のコードから見つけた不具合（全件、人が再現を確認） | 16件（Codex作をレビュー・30分） | 17件（Claude作をレビュー・15分） |

- **どちらのツールも、経理にそのまま使える品質ではありません。** 相互レビューの結論は両者とも「このままでは会計用に使わない／下書き用途まで」でした（`results/round3/*/REVIEW.md`）。ポイント値引き後の支払額・0円・外税・傾いた写真などで、間違った値を黙って出します。
- 数字は **1回ずつの計測** です。混雑による失敗や当たり外れがあるので、自分で比べるなら2〜3回やって中央値を見てください。
- 実行時は両方とも作者の普段の個人設定（Claude Code の `CLAUDE.md`、Codex の `AGENTS.md` など）が効いた状態でした。素の状態の比較ではありません（個人設定の中身はこのキットに入れていません）。

## 中身

```
prompts/            指示文（両者に一字一句同じものを渡した）
  round1.md           R1: 領収書 PDF/画像 → CSV の CLI を作る
  round3.md           R3: 相手が作ったツールをコードレビューする
  round3_SPEC.md      R3 でレビュー対象と一緒に渡した仕様
task/round1/        R1 の作業フォルダの初期状態（これをコピーして両者に渡す）
  samples/            架空の領収書7件（＋無視されるべき memo.txt）
  tests/test_acceptance.py  受け入れテスト（AI に書き換えさせない）
data/
  holdout/            渡していない追加サンプル3件＋expected.csv（テストに合わせただけの作り込みを見抜く用）
  hard/               人が作った意地悪サンプル12件＋expected.csv
results/
  round1/claude/      Claude Code が作ったツール（receipt2csv.py・テスト）
  round1/codex/       Codex が作ったツール（receipt2csv.py・receipt_ocr.swift・テスト・README）
  round3/claude/      Claude Code が Codex 作をレビューした REVIEW.md と再現用ファイル（target/ はレビュー対象のコピー）
  round3/codex/       Codex が Claude 作をレビューした REVIEW.md と再現用ファイル
  judge/r3/           レビュー指摘を人が再現した記録・相互の意地悪入力の照合結果
scoring/
  run_engine.py       1エンジンを1回走らせ、生ログ・時刻つきログ・所要時間を残す
  score.py            ツール × 期待値CSV で項目ごとに採点
  cross.py            R3 で両者が作った意地悪入力を、両方のツールに通す
  verify_lines.py     行リストからテキストPDFを作ってツールに通す（レビュー指摘の確認用）
  stats.py / timeline.py  ログから使用量・発言の時刻を抜く
  make_receipts.py / make_holdout.py / make_hard.py  架空サンプルの生成スクリプト
  ocr_check.swift     macOS の文字認識で画像を読むだけの確認用
```

データはすべて架空です（実在の店舗・個人情報は使っていません）。

## 自分の環境で同じ比較をする

### 共通の前提
1. **両方ともサブスクでログイン**する（課金プランが前提です。無料版では本来の実力は比べられません）
   - Claude Code: `claude` を起動して `/login`
   - Codex: `codex login` で ChatGPT アカウントを選ぶ
2. **APIキーの環境変数が残っていないか確認**する。残っていると従量課金になることがあります
   - Mac / Linux / WSL: `env | grep API_KEY`
   - Windows（PowerShell）: `Get-ChildItem Env: | findstr API_KEY`
3. お題ごとにフォルダを2つ作り、同じ初期ファイルを入れる
   ```sh
   cp -R task/round1 work/claude && cp -R task/round1 work/codex
   ```

### MacBook など手元の PC（macOS）
```sh
npm i -g @anthropic-ai/claude-code @openai/codex
# ターミナルを2つ開いて、同時にスタート
cd work/claude && time claude -p "$(cat ../../prompts/round1.md)" --output-format stream-json --verbose > ../claude.jsonl
cd work/codex  && time codex exec --json "$(cat ../../prompts/round1.md)" > ../codex.jsonl
```
- `scoring/run_engine.py` を使うと、時刻つきログと所要時間（`.meta.json`）まで残ります: `python3 scoring/run_engine.py claude work/claude prompts/round1.md logs/r1-claude`
- 今回は**確認なし**で動かしました（Claude Code は `--dangerously-skip-permissions`、Codex は `--dangerously-bypass-approvals-and-sandbox`）。付けるなら**必ず使い捨てのフォルダで**。付けない場合は、許可を求められて答えた回数を「口を出した回数」として数えてください
- モデルと推論の深さは今回 `claude --model opus --effort max`、Codex は `~/.codex/config.toml` の `model = "gpt-6.1-sol"`・reasoning effort `ultra` でした。どちらも各社の最上位モデル（Fable 5.1／GPT-6 Astra）ではなく、普段使いの主力モデルです

### Windows
- **WSL（Ubuntu）を入れる**と上の手順がそのまま使えます
- ただし R1 のお題は macOS の文字認識（Vision）を使ってよい前提です。Windows では指示文の「macOS 標準の Vision フレームワーク」を「Windows 標準の文字認識（Windows.Media.Ocr）」に書き換えるか、画像の入らないお題（CSV の整形・集計など）に変えてください

### クラウド版（PC を置いておけない人）
- Codex: chatgpt.com/codex ／ Claude Code: claude.ai/code
- このキットを自分の GitHub リポジトリに入れて両方につなぎ、同じ指示文を貼る → それぞれのブランチ・差分を比べる。時間はタスクの開始と完了の時刻で測る
- クラウドは実行環境（OS・ネット接続・入っているライブラリ）がローカルと違います。R1 は macOS 前提なので、クラウドでは OCR の要らないお題に変えるのが無難です

## 採点する

```sh
# 1) 受け入れテスト（各作業フォルダの中で）
python3 -m unittest discover -s tests -v
# 2) 渡していないサンプル・意地悪サンプル（キット直下で。パスは絶対パスで渡す）
python3 scoring/score.py work/claude "$PWD/data/holdout/expected.csv" "$PWD/data/holdout/receipts"
python3 scoring/score.py work/claude "$PWD/data/hard/expected.csv"    "$PWD/data/hard/receipts"
```
- 同梱の結果で試すなら `work/claude` を `results/round1/claude` に変えるだけです（holdout 9/9・hard 36/36 と 35/36 が再現されます）

### R3（相互レビュー）
1. 新しいフォルダに `target/` を作り、**相手が作った**ツール一式を入れる（`prompts/round3_SPEC.md` を `target/SPEC.md` として置く）
2. `prompts/round3.md` を同時に流す
3. 出てきた `REVIEW.md` の指摘を、**人が1件ずつ再現して**本物かどうかを数える（今回は 33件すべて本物でした）
4. おまけ: `python3 scoring/cross.py` で、両者が作った意地悪入力を両方のツールに通せます。ただし各自「相手のツールが落ちるもの」を選んで作っているので、相手に効くのは当然で、ツールの優劣の証拠にはなりません

## 公平に比べるコツ（やってみて分かったこと）
- 合格テストは**先に人が書いて**両方に同じものを渡す。そのうえで**渡していないサンプル**でも採点する
- 「◯分で切り上げて」「テストが通ったら終わり」と書かないと、Claude Code は自分で範囲を広げることがある。時間も比べるなら、両方の指示文に同じ上限を書く
- 1回だけだと、混雑による失敗（今回は Codex が 503 で1回止まった）や当たり外れがある。各2〜3回やって中央値で比べる
- レビューは**作った方と別のAI**にやらせると効く。どちらも自分のテストは全部通していたのに、相手からは16〜17件の不具合が出た

## 必要なもの
- Python 3（標準ライブラリ）、PyMuPDF（`pip install pymupdf`）、Pillow、macOS（R1 の画像OCRに Vision を使う）
- サンプル生成スクリプトはヒラギノフォント（macOS）を使います。他の OS では同梱済みのサンプルをそのまま使ってください

## ライセンス
MIT（`LICENSE`）。AI が作ったコードを含みます。品質は上の結論のとおりで、実務にそのまま使わないでください。
