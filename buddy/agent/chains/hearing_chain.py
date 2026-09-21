from datetime import datetime
from pathlib import Path
from typing import Literal

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field


def _load_prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.prompt").read_text().strip()


class Hearing(BaseModel):
    is_need_human_feedback: bool = Field(default=False, description="追加質問が必要か")
    additional_question: str = Field(
        default="", description="ユーザーへの追加質問（不要なら空文字）"
    )
    normalized_query: str = Field(
        default="",
        description="検索に使うために正規化した地点名（例: 『109』→『渋谷 109』）。曖昧なら空文字。",
    )


class HearingChain:
    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def __call__(
        self, state: dict
    ) -> Command[Literal["human_feedback", "search_location"]]:
        messages = state.get("messages", [])
        hearing = self._run(messages)

        if hearing.is_need_human_feedback:
            return Command(
                goto="human_feedback",
                update={
                    "need_feedback": True,
                    "ask_user": hearing.additional_question,
                    "messages": [
                        {"role": "assistant", "content": hearing.additional_question}
                    ],
                },
            )

        # 直近の human メッセージを原クエリとして採用
        original = next(
            (
                m.content
                for m in reversed(messages)
                if getattr(m, "type", "") == "human"
            ),
            "",
        )
        return Command(
            goto="search_location",
            update={
                "need_feedback": False,
                "original_query": hearing.normalized_query or original,
            },
        )

    def _run(self, messages: list[BaseMessage]) -> Hearing:
        prompt = ChatPromptTemplate.from_template(_load_prompt("hearing"))
        chain = prompt | self.llm.with_structured_output(
            Hearing, method="function_calling"
        )
        return chain.invoke(
            {
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "conversation_history": self._format(messages),
            }
        )

    @staticmethod
    def _format(messages: list[BaseMessage]) -> str:
        return "\n".join(
            f"{m.type}: {m.content}" for m in messages if getattr(m, "content", None)
        )
