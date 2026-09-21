"""smoke test: lockfile からの clean install でアプリがロードできること。

uv sync --locked が保証するのは、ロックされた依存が「インストールできる」
ことまでで、それらが今もこのコードの呼ぶ API を提供しているかは別の話。
ここではその差が実際に効く。langgraph / langchain-core の深い import パスを
掴んでおり、依存の1つは既に改名を経験している（duckduckgo_search -> ddgs）。

buddy.agent.graph の import は、たまたま import 以上のことをする。モジュール
直下で WeatherBuddyAgent を組み立てるため、Settings を読み、ChatOpenAI を2つ
構築し、LangGraph のグラフを compile するところまで走る。依存の更新で最初に
壊れる部分が、1行の import でまとめて動く。

ネットワークには出ない。ChatOpenAI は構築時に API を叩かず、キーが存在する
ことだけを要求する。CI では .env.example がそれを供給する。
"""


def test_agent_graph_builds():
    from buddy.agent.graph import agent

    assert agent is not None
