# weather-report-buddy 仕様書

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

```
user_hearing ──(曖昧)──> human_feedback (interrupt) ──> user_hearing
     │
  (明確)
     ▼
search_location (Nominatim で緯度経度候補取得)
     ▼
resolve (LLM が最適候補を選定)
     ▼
fetch_radar (気象庁ナウキャスト +60分 / 10分刻み の合成画像を取得)
     ▼
analyze (画像群を Vision LLM で分析 → advice / rationale)
     ▼
END (UI に表示)
```

## 各ステップの仕様

### 1. 場所ヒアリング（user_hearing / human_feedback）
- LLM（gpt-4o-mini）が入力の曖昧さを判定。曖昧なら `interrupt()` でユーザーに質問を返し、回答を待つ
- 場所の入力がない限り後続ステップは実行しない

### 2. ジオコーディング（search_location / resolve）
- Nominatim (OpenStreetMap) で緯度経度候補を取得（1req/sec スロットル、User-Agent 必須）
- 候補不足時は DuckDuckGo 検索で通称を解決
- LLM が候補から最適な1件を選定し、理由を付与

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

| 用途 | モデル | 備考 |
|---|---|---|
| 場所の曖昧さ判定・候補選定 | gpt-4o-mini | |
| レーダー画像分析 | gpt-5-mini | |

- OpenAI API キー1つで動作。`.env` で管理（`OPENAI_API_KEY`）

## スコープ外（今回はやらない）

- 長時間予報（rasrf / 15時間先）
- ナウキャスト以外の気象データ（気温、警報等）
- 会話履歴の永続化・複数地点の同時監視

## 技術スタック

- Python 3.11+ / uv（pyproject.toml）
- streamlit, langgraph, langchain-openai, pydantic, httpx, duckduckgo-search, python-dotenv, Pillow
