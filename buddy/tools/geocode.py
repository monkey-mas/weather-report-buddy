"""外部サービス呼び出し: Nominatim (OSM) と DuckDuckGo Web 検索"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from ddgs import DDGS

from buddy.settings import settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim の利用ポリシーで 1 req/sec を厳守
_LAST_CALL_TS: float = 0.0
_MIN_INTERVAL_SEC = 1.1


@dataclass
class GeoCandidate:
    display_name: str
    lat: float
    lon: float
    type: str  # "city", "building" 等
    importance: float  # Nominatim が返す重要度 (0.0-1.0)
    raw: dict

    def to_summary(self) -> str:
        return f"{self.display_name} (lat={self.lat:.6f}, lon={self.lon:.6f})"


def _throttle() -> None:
    global _LAST_CALL_TS
    elapsed = time.time() - _LAST_CALL_TS
    if elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _LAST_CALL_TS = time.time()


def nominatim_geocode(query: str, limit: int = 5) -> list[GeoCandidate]:
    """Nominatim で geocoding。日本語クエリ可。"""
    _throttle()
    headers = {"User-Agent": settings.nominatim_user_agent}
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": str(limit),
        "addressdetails": "1",
        "accept-language": "ja",
    }
    try:
        resp = httpx.get(NOMINATIM_URL, params=params, headers=headers, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Nominatim 呼び出し失敗: {e}") from e

    results: list[GeoCandidate] = []
    for item in resp.json():
        try:
            results.append(
                GeoCandidate(
                    display_name=item.get("display_name", ""),
                    lat=float(item["lat"]),
                    lon=float(item["lon"]),
                    type=item.get("type", ""),
                    importance=float(item.get("importance", 0.0)),
                    raw=item,
                )
            )
        except (KeyError, ValueError):
            continue
    return results


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo で検索。通称→正式名称の解決用。"""
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results, region="jp-jp"))
    except Exception as e:
        # 検索失敗はフェイタルではない（LLM 知識にフォールバック）
        return [{"error": str(e)}]
