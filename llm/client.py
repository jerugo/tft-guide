"""OpenAI 호환 LLM API 클라이언트 + 룰 기반 폴백"""
import logging
from typing import Optional

import requests

from config import LLM_API_URL, LLM_MODEL, LLM_TIMEOUT

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 TFT(전략적 팀 전투) 전문 코치입니다.
현재 게임 상황을 분석하고, 최적의 전략을 한국어로 조언해주세요.
다음 형식으로 답변하세요:

📋 현재 상황 분석
🎯 추천 행동 (구체적으로 3가지)
💰 경제 관리 조언
⚔️ 포지셔닝 팁

간결하고 실전적인 조언을 해주세요."""


def rule_based_advice(my_champions: list[str], level: int = 7,
                      gold: int = 0, recommendations: list[dict] = None) -> str:
    """LLM 없이 룰 기반 조언 생성"""
    advice = []
    n = len(my_champions)

    # 경제 조언
    if gold >= 50:
        advice.append("💰 50골드 이자 유지 중! 레벨업이나 리롤에 투자하세요.")
    elif gold >= 30:
        advice.append("💰 이자 벌기 좋은 구간입니다. 50골드까지 모아보세요.")
    elif gold < 10 and level >= 7:
        advice.append("💰 골드가 부족합니다. 연패/연승 보너스를 활용하세요.")

    # 레벨 조언
    if level <= 5 and n >= 4:
        advice.append("📈 아직 초반! 2코스트 위주로 보드를 채우세요.")
    elif level >= 8 and n < 6:
        advice.append("⚠️ 보드가 비었습니다! 당장 유닛을 배치하세요.")

    # 추천 덱 관련
    if recommendations and len(recommendations) > 0:
        top = recommendations[0]
        match_rate = top.get("match_rate", 0)
        name = top.get("deck_name", "")
        needed = top.get("needed_champions", [])

        if match_rate >= 0.6:
            advice.append(f"🎯 '{name}' 덱이 {match_rate*100:.0f}% 매칭! 완성을 노려보세요.")
            if needed:
                need_names = [n_c.get("name", "") for n_c in needed[:3]]
                advice.append(f"🔍 필요 챔피언: {', '.join(need_names)}")
        elif match_rate < 0.3 and n >= 3:
            advice.append("🔄 방향 전환을 고려해보세요. 현재 챔피언과 맞는 덱이 적습니다.")

    if not advice:
        advice.append("🎮 챔피언을 더 모아보세요! 방향이 잡히면 구체적 조언을 드리겠습니다.")

    return "\n".join(advice)


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
                     level: int = 7, gold: int = 0) -> dict:
        """
        게임 상황 분석 요청.
        Returns: {"analysis": str, "source": "llm"|"rule"}
        """
        # LLM 시도
        llm_result = self._try_llm(my_champions, recommendations,
                                    opponent_info, level, gold)
        if llm_result:
            return {"analysis": llm_result, "source": "llm"}

        # 폴백: 룰 기반
        rule_result = rule_based_advice(my_champions, level, gold, recommendations)
        return {"analysis": rule_result, "source": "rule"}

    def _try_llm(self, my_champions, recommendations,
                 opponent_info, level, gold) -> Optional[str]:
        """LLM API 호출 시도"""
        context = f"""현재 상황:
- 레벨: {level}, 골드: {gold}
- 내 챔피언: {', '.join(my_champions) if my_champions else '없음'}
- 상대 정보: {opponent_info or '없음'}

추천 엔진 결과 (상위 3개):
"""
        for i, rec in enumerate(recommendations[:3], 1):
            needed = [n["name"] for n in rec.get("needed_champions", [])]
            context += (
                f"{i}. {rec['deck_name']} (티어 {rec['tier']}, "
                f"매칭률 {rec['match_rate']:.0%})"
            )
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
