# 🌦️ Weather Report Buddy

ユーザーに教えてもらった場所の雨雲レーダー（今後60分の高解像度降水ナウキャスト）を取得・分析し、外出アドバイスをくれる AI エージェントアプリ。

仕様は [SPEC.md](SPEC.md)、実装方針は [PLAN.md](PLAN.md)、進捗は [TODO.md](TODO.md) を参照。

## 動作の流れ

1. チャットで場所を入力（曖昧な場合はエージェントが聞き返します）
2. Nominatim (OpenStreetMap) + LLM で緯度経度を確定
3. 気象庁ナウキャストの雨雲タイルを取得し、地理院地図と合成（現在〜+60分 / 10分刻み）
4. 時系列画像を Vision LLM が分析し、アドバイス（結論＋根拠）を表示

## セットアップ

```bash
cp .env.example .env
# .env に OPENAI_API_KEY と NOMINATIM_USER_AGENT（メールアドレス等）を設定

uv sync
```

## 実行

```bash
uv run streamlit run app.py
```

## 構成

```
app.py                        # Streamlit チャットUI
buddy/
├── settings.py               # 環境変数 (.env) 管理
├── tools/
│   ├── geocode.py            # Nominatim + DuckDuckGo
│   └── radar.py              # 気象庁ナウキャスト取得・地図合成
└── agent/
    ├── state.py              # LangGraph の状態定義
    ├── graph.py              # エージェントグラフ
    └── chains/
        ├── hearing_chain.py  # 場所入力の曖昧さ判定・聞き返し
        ├── resolve_chain.py  # 緯度経度候補の選定
        ├── analyze_chain.py  # レーダー画像の Vision 分析
        └── prompts/          # 各チェーンのプロンプト
```

## クレジット

- 雨雲レーダー: [気象庁](https://www.jma.go.jp/) 高解像度降水ナウキャスト
- 地図タイル: [国土地理院](https://maps.gsi.go.jp/development/ichiran.html)
- ジオコーディング: [Nominatim / OpenStreetMap](https://nominatim.org/)
