# weather-report-buddy 仕様書

[English](SPEC.md) | 日本語

## 概要

ユーザーが入力した場所について、気象庁の高解像度降水ナウキャスト（今後60分の雨雲レーダー）を取得・分析し、実用的なアドバイス（傘の要否、外出タイミング等）を返す AI エージェントアプリ。

## UI

- **Streamlit チャットUI**（`st.chat_message` / `st.chat_input`）
- 会話の流れ:
  1. アシスタントが場所を尋ねる
  2. ユーザーが場所を入力（入力があるまで次へ進まない）
  3. 場所が曖昧な場合、アシスタントが聞き返す（例:「府中市は東京と広島のどちらですか？」）
  4. 場所確定後、緯度経度・レーダー合成画像・アドバイスをチャット上に表示

## アーキテクチャ

- **LangGraph** によるエージェントグラフ

分岐は静的エッジではなく、各ノードが返す `Command(goto=...)` で決まる。

```
START           ──→ user_hearing
user_hearing    ──→ human_feedback   (入力が曖昧)
user_hearing    ──→ search_location  (入力が明確)
human_feedback  ──→ user_hearing     (回答後は入口に関係なく必ずここへ戻る)
search_location ──→ resolve          (Nominatim / 必要なら Web 検索で候補取得)
resolve         ──→ human_feedback   (候補が1件に絞れない)
resolve         ──→ fetch_radar      (1件に確定)
fetch_radar     ──→ analyze          (現在〜+60分 / 10分刻みの合成画像を取得)
analyze         ──→ END              (advice / rationale を UI に表示)
```

聞き返し（`interrupt()`）の入口は **`user_hearing` と `resolve` の2箇所**ある。
`human_feedback` はどちらから来ても `user_hearing` へ戻るため、resolve 由来の
聞き返しでも曖昧さ判定からやり直しになる。

## 各ステップの仕様

### 1. 場所ヒアリング（user_hearing / human_feedback）
- LLM（gpt-4o-mini）が入力の曖昧さを判定。曖昧なら `interrupt()` でユーザーに質問を返し、回答を待つ
- 場所の入力がない限り後続ステップは実行しない

### 2. ジオコーディング（search_location / resolve）
- Nominatim (OpenStreetMap) で緯度経度候補を取得（1req/sec スロットル、User-Agent 必須）
- 候補不足時は DuckDuckGo 検索（`ddgs`）で通称を解決
- LLM が候補から最適な1件を選定し、理由を付与
- 候補が絞れない場合は `interrupt()` でユーザーに聞き返す（`need_more_info`）

### 3. 雨雲レーダー取得（fetch_radar）
- 気象庁ナウキャスト（`product=nowc`, `element=hrpns`）の PNG タイルを取得
- 緯度経度→Webメルカトルタイル座標変換、タイルモザイク合成
- 対象: 現在〜+60分、10分刻み（計7フレーム）
- 出力: 地図と重ねた合成画像（現在地マーカー付き）を `output/` に保存

### 4. 分析・アドバイス（analyze）
- 合成画像群を Base64 で OpenAI Vision モデル（gpt-5-mini）へ送信
- システムプロンプトで降水強度凡例・現在地マーカー優先・移動方向分析を指示
- Structured Outputs で構造化:
  - `advice`: ユーザー向け結論（1-2文。傘の要否、出発時刻調整など）
  - `rationale`: 根拠（1-3文。雨雲の位置・移動・強度変化）

## LLM 構成

| 用途 | モデル |
|---|---|
| 場所の曖昧さ判定・候補選定 | gpt-4o-mini |
| レーダー画像分析 | gpt-5-mini |

- OpenAI API キー1つで動作。`.env` で管理（`OPENAI_API_KEY`）

## スコープ外（今回はやらない）

- 長時間予報（rasrf / 15時間先）
- ナウキャスト以外の気象データ（気温、警報等）
- 会話履歴の永続化・複数地点の同時監視

## 技術スタック

- Python 3.11+ / uv（pyproject.toml）
- streamlit, langgraph, langchain-openai, langchain-core, pydantic, pydantic-settings, httpx, ddgs, python-dotenv, Pillow
