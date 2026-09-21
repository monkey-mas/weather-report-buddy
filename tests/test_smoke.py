"""Smoke test: the app can be loaded from a clean install of the lockfile.

`uv sync --locked` only proves the 77 dependencies *install*. It does not prove
they still expose the API this code calls. That gap is real here: this project
pins deep import paths into fast-moving libraries (langgraph, langchain-core),
and one of its dependencies has already been renamed once (duckduckgo_search ->
ddgs).

Importing buddy.agent.graph happens to exercise far more than an import:
the module builds a WeatherBuddyAgent at import time, which reads Settings,
constructs two ChatOpenAI clients, and compiles the LangGraph graph. So a
single import covers the parts most likely to break on a dependency upgrade.

No network call is made. Constructing ChatOpenAI does not contact the API;
it only requires that a key be present, which .env.example supplies in CI.
"""


def test_agent_graph_builds():
    from buddy.agent.graph import agent

    assert agent is not None
