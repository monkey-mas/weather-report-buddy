"""hearing チェーンの判定を単体で確認するデバッグスクリプト。

使い方: uv run python scripts/debug_hearing.py 虎ノ門駅 東京駅 府中市
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage

from buddy.agent.chains.hearing_chain import HearingChain
from buddy.settings import settings

chain = HearingChain(settings.llm)
for query in sys.argv[1:] or ["虎ノ門駅"]:
    hearing = chain._run([HumanMessage(content=query)])
    print(f"入力: {query!r}")
    print(f"  need_feedback: {hearing.is_need_human_feedback}")
    print(f"  additional_question: {hearing.additional_question!r}")
    print(f"  normalized_query: {hearing.normalized_query!r}")
