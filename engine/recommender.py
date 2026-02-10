"""TFT 덱 추천 엔진"""
import json
from typing import Optional, Union

from config import CHAMPION_POOL, SHOP_ODDS, CHAMPIONS_JSON, META_JSON


def _load_json(path) -> Optional[Union[dict, list]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


class DeckRecommender:
    """메타 덱 기반 추천 엔진"""

    def __init__(self):
        self.champions = _load_json(CHAMPIONS_JSON) or []
        self.meta_decks = (_load_json(META_JSON) or {}).get("decks", [])
        # name → champion data lookup
        self._champ_map = {c["name"]: c for c in self.champions}

    def reload_data(self):
        self.champions = _load_json(CHAMPIONS_JSON) or []
        self.meta_decks = (_load_json(META_JSON) or {}).get("decks", [])
        self._champ_map = {c["name"]: c for c in self.champions}

    def calculate_pool(self, opponent_champions: list[list[str]]) -> dict[str, int]:
        """
        챔피언 풀 잔여 수 계산.
        opponent_champions: 각 상대의 챔피언 이름 리스트들
        Returns: {champion_name: remaining_copies}
        """
        pool = {}
        for champ in self.champions:
            name = champ["name"]
            cost = champ["cost"]
            pool[name] = CHAMPION_POOL.get(cost, 0)

        # 상대가 보유한 챔피언 제외 (각 복사본 1개씩)
        for opp in opponent_champions:
            for name in opp:
                if name in pool:
                    pool[name] = max(0, pool[name] - 1)

        return pool

    def shop_probability(self, champion_name: str, level: int,
                         pool: dict[str, int]) -> float:
        """특정 챔피언이 상점에 등장할 확률 (슬롯 1개 기준)"""
        champ = self._champ_map.get(champion_name)
        if not champ or level not in SHOP_ODDS:
            return 0.0

        cost = champ["cost"]
        cost_odds = SHOP_ODDS[level][cost - 1]

        if cost_odds == 0:
            return 0.0

        # 해당 코스트 챔피언들의 총 잔여 수
        total_in_cost = sum(
            pool.get(c["name"], 0)
            for c in self.champions if c["cost"] == cost
        )
        if total_in_cost == 0:
            return 0.0

        champ_remaining = pool.get(champion_name, 0)
        return cost_odds * (champ_remaining / total_in_cost)

    def recommend(self, my_champions: list[str],
                  opponent_champions: list[list[str]] = None,
                  level: int = 7) -> list[dict]:
        """
        덱 추천.
        Returns: sorted list of {deck_name, tier, win_rate, match_rate,
                  needed_champions, completion_score, ...}
        """
        if opponent_champions is None:
            opponent_champions = []

        pool = self.calculate_pool(opponent_champions)
        my_set = set(my_champions)
        results = []

        for deck in self.meta_decks:
            core = set(deck.get("core_champions", []))
            total_needed = len(core)
            if total_needed == 0:
                continue

            owned = core & my_set
            needed = core - my_set
            match_rate = len(owned) / total_needed

            # 필요 챔피언별 상점 확률
            needed_info = []
            prob_product = 1.0
            for name in needed:
                prob = self.shop_probability(name, level, pool)
                remaining = pool.get(name, 0)
                needed_info.append({
                    "name": name,
                    "shop_probability": round(prob, 4),
                    "remaining_in_pool": remaining,
                })
                prob_product *= (1 - prob)

            # 완성 가능성 스코어 (매칭률 + 획득 용이성)
            acquisition_score = 1 - prob_product if needed else 1.0
            completion_score = match_rate * 0.6 + acquisition_score * 0.4

            results.append({
                "deck_name": deck.get("name", "Unknown"),
                "tier": deck.get("tier", "?"),
                "win_rate": deck.get("win_rate", 0),
                "pick_rate": deck.get("pick_rate", 0),
                "synergies": deck.get("synergies", []),
                "core_items": deck.get("core_items", []),
                "match_rate": round(match_rate, 2),
                "owned_champions": sorted(owned),
                "needed_champions": needed_info,
                "completion_score": round(completion_score, 4),
            })

        results.sort(key=lambda r: -r["completion_score"])
        return results

    def get_pool_status(self, opponent_champions: list[list[str]] = None) -> dict:
        """코스트별 풀 현황 반환"""
        pool = self.calculate_pool(opponent_champions or [])
        by_cost = {}
        for champ in self.champions:
            cost = champ["cost"]
            if cost not in by_cost:
                by_cost[cost] = []
            by_cost[cost].append({
                "name": champ["name"],
                "name_kr": champ.get("name_kr", champ["name"]),
                "remaining": pool.get(champ["name"], 0),
                "total": CHAMPION_POOL.get(cost, 0),
            })
        return by_cost
