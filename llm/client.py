"""OpenAI 호환 LLM API 클라이언트"""
import json
import logging
from typing import Optional

import requests

from config import LLM_API_URL, LLM_MODEL, LLM_TIMEOUT

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 TFT(전략적 팀 전투) 전문 코치입니다.
현재 게임 상황을 분석하고, 최적의 전략을 한국어로 조언해주세요.
덱 추천, 아이템 조합, 포지셔닝, 경제 관리 등을 포함해주세요."""


class LLMClient:
    """OpenAI 호환 API 클라이언트 (Ollama, vLLM 등)"""

    def __init__(self, api_url: Optional[str] = None, model: Optional[str] = None):
        self.api_url = (api_url or LLM_API_URL).rstrip("/")
        self.model = model or LLM_MODEL
        self.timeout = LLM_TIMEOUT
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """LLM 서버 연결 확인"""
        try:
            resp = requests.get(f"{self.api_url}/models", timeout=5)
            self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def analyze_game(self, my_champions: list[str],
                     recommendations: list[dict],
                     opponent_info: str = "",
                     level: int = 7, gold: int = 0) -> Optional[str]:
        """게임 상황 분석 요청"""
        context = f"""현재 상황:
- 레벨: {level}, 골드: {gold}
- 내 챔피언: {', '.join(my_champions) if my_champions else '없음'}
- 상대 정보: {opponent_info or '없음'}

추천 엔진 결과 (상위 3개):
"""
        for i, rec in enumerate(recommendations[:3], 1):
            needed = [n["name"] for n in rec.get("needed_champions", [])]
            context += f"{i}. {rec['deck_name']} (티어 {rec['tier']}, 매칭률 {rec['match_rate']:.0%})"
            if needed:
                context += f" - 필요: {', '.join(needed)}"
            context += "\n"

        return self._chat(context)

    def _chat(self, user_message: str) -> Optional[str]:
        """채팅 완성 API 호출"""
        try:
            resp = requests.post(
                f"{self.api_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1024,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"LLM 요청 실패: {e}")
            return None
