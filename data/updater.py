"""롤체지지/메타 사이트 크롤링으로 데이터 자동 업데이트"""
import json
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import CHAMPIONS_JSON, META_JSON

logger = logging.getLogger(__name__)

LOLCHESS_URL = "https://lolchess.gg/meta"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def update_meta(source_url: str = LOLCHESS_URL) -> dict:
    """
    메타 덱 데이터를 크롤링하여 업데이트.
    Returns: {"success": bool, "message": str, "updated_at": str}
    """
    try:
        resp = requests.get(source_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 참고: 실제 파싱은 사이트 구조에 따라 조정 필요
        # 현재는 프레임워크만 구현
        decks = _parse_meta_decks(soup)

        if decks:
            current = {}
            if META_JSON.exists():
                with open(META_JSON, "r", encoding="utf-8") as f:
                    current = json.load(f)

            current["decks"] = decks
            current["last_updated"] = datetime.now().isoformat()
            current["source"] = source_url

            with open(META_JSON, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)

            return {"success": True, "message": f"{len(decks)}개 덱 업데이트 완료",
                    "updated_at": current["last_updated"]}
        else:
            return {"success": False, "message": "파싱된 덱이 없습니다. 사이트 구조가 변경되었을 수 있습니다."}

    except requests.RequestException as e:
        logger.error(f"크롤링 실패: {e}")
        return {"success": False, "message": f"크롤링 실패: {e}"}


def _parse_meta_decks(soup: BeautifulSoup) -> list[dict]:
    """
    메타 덱 파싱 (사이트 구조에 따라 구현 필요).
    현재는 빈 리스트 반환 — 실제 사이트 DOM 확인 후 채워야 함.
    """
    # TODO: 롤체지지 DOM 구조에 맞춰 파싱 구현
    # 예시 구조:
    # decks = []
    # for card in soup.select(".comp-card"):
    #     deck = {
    #         "name": card.select_one(".comp-name").text.strip(),
    #         "tier": card.select_one(".tier-badge").text.strip(),
    #         ...
    #     }
    #     decks.append(deck)
    return []


def get_last_updated() -> str:
    """마지막 업데이트 시각 반환"""
    try:
        with open(META_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("last_updated", "알 수 없음")
    except (FileNotFoundError, json.JSONDecodeError):
        return "업데이트 기록 없음"


if __name__ == "__main__":
    result = update_meta()
    print(json.dumps(result, ensure_ascii=False, indent=2))
