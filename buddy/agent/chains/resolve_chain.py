import json
from pathlib import Path
from typing import Literal, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field

from buddy.agent.state import GeoResult


def _load_prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.prompt").read_text().strip()


class ResolveDecision(BaseModel):
    need_more_info: bool = Field(
        default=False, description="候補が絞れず追加質問が必要か"
    )
    additional_question: str = Field(default="")
    chosen_lat: Optional[float] = Field(default=None)
    chosen_lon: Optional[float] = Field(default=None)
    chosen_name: str = Field(default="")
    reasoning: str = Field(default="", description="この判断に至った根拠")


class ResolveChain:
    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def __call__(
        self, state: dict
    ) -> Command[Literal["human_feedback", "fetch_radar"]]:
        query = state.get("original_query", "")
        candidates = state.get("candidates", [])
        web_hits = state.get("web_hits", [])
        decision = self._run(query, candidates, web_hits)

        if decision.need_more_info or decision.chosen_lat is None:
            return Command(
                goto="human_feedback",
                update={
                    "need_feedback": True,
                    "ask_user": decision.additional_question,
                    "messages": [
                        {"role": "assistant", "content": decision.additional_question}
                    ],
                },
            )

        result = GeoResult(
            query=query,
            resolved_name=decision.chosen_name,
            lat=decision.chosen_lat,
            lon=decision.chosen_lon,
            reasoning=decision.reasoning,
        )
        final_msg = (
            f"『{query}』→ **{result.resolved_name}**"
            f"（緯度: {result.lat:.6f} / 経度: {result.lon:.6f}）の"
            f"雨雲レーダーを確認します..."
        )
        return Command(
            goto="fetch_radar",
            update={
                "result": result,
                "need_feedback": False,
                "messages": [{"role": "assistant", "content": final_msg}],
            },
        )

    def _run(
        self, query: str, candidates: list[dict], web_hits: list[dict]
    ) -> ResolveDecision:
        prompt = ChatPromptTemplate.from_template(_load_prompt("resolve"))
        chain = prompt | self.llm.with_structured_output(
            ResolveDecision, method="function_calling"
        )
        return chain.invoke(
            {
                "query": query,
                "candidates": json.dumps(candidates, ensure_ascii=False, indent=2),
                "web_hits": json.dumps(web_hits, ensure_ascii=False, indent=2),
            }
        )
