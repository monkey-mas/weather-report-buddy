from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    openai_vision_model: str = Field("gpt-5-mini", alias="OPENAI_VISION_MODEL")
    nominatim_user_agent: str = Field(
        "weather-report-buddy/0.1", alias="NOMINATIM_USER_AGENT"
    )
    output_dir: str = Field("output", alias="OUTPUT_DIR")

    @property
    def llm(self) -> ChatOpenAI:
        """地名の曖昧さ判定・候補選定用 LLM"""
        return ChatOpenAI(
            model=self.openai_model,
            api_key=self.openai_api_key,
            temperature=0.0,
        )

    @property
    def vision_llm(self) -> ChatOpenAI:
        """雨雲レーダー画像分析用 LLM (gpt-5 系は temperature 指定不可のため既定値)"""
        return ChatOpenAI(
            model=self.openai_vision_model,
            api_key=self.openai_api_key,
        )


settings = Settings()
