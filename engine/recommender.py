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

    def get_shop_advice(self, my_champions: list[str],
                        shop_champions: list[str],
                        recommended_decks: list[dict],
                        level: int = 7,
                        gold: int = 50,
                        opponent_champions: list[list[str]] = None) -> dict:
        """
        상점 추천 분석.
        Returns: {
            shop_advice: [{name, name_kr, cost, action, emoji, reason, priority, deck_name}],
            reroll_advice: {should_reroll, emoji, reason, detail},
            level_advice: {should_level, reason}
        }
        """
        if opponent_champions is None:
            opponent_champions = []

        pool = self.calculate_pool(opponent_champions)
        my_set = set(my_champions)
        # Count owned copies for upgrade detection
        my_counts: dict[str, int] = {}
        for name in my_champions:
            my_counts[name] = my_counts.get(name, 0) + 1

        # Top 3 recommended decks
        top_decks = recommended_decks[:3] if recommended_decks else []
        secondary_decks = recommended_decks[3:] if len(recommended_decks) > 3 else []

        # Build needed-champion sets per deck with role info
        def _deck_needs(deck):
            """Returns set of needed champion names for a deck"""
            needed_names = set()
            for ni in deck.get("needed_champions", []):
                needed_names.add(ni["name"])
            return needed_names

        top_needed = {}  # champion -> deck info
        for deck in top_decks:
            for ni in deck.get("needed_champions", []):
                name = ni["name"]
                if name not in top_needed:
                    top_needed[name] = deck

        secondary_needed = {}
        for deck in secondary_decks:
            for ni in deck.get("needed_champions", []):
                name = ni["name"]
                if name not in secondary_needed and name not in top_needed:
                    secondary_needed[name] = deck

        # Determine carry champions from meta decks (last 2-3 champs in deck list are usually carries)
        carry_champions = set()
        for deck in self.meta_decks:
            champs = deck.get("champions", deck.get("core_champions", []))
            if len(champs) >= 2:
                # Higher cost champions in the deck are typically carries
                for cname in champs:
                    c = self._champ_map.get(cname)
                    if c and c.get("cost", 1) >= 4:
                        carry_champions.add(cname)

        # Analyze each shop champion
        shop_advice = []
        core_missing_count = 0

        for shop_name in shop_champions:
            champ = self._champ_map.get(shop_name)
            if not champ:
                shop_advice.append({
                    "name": shop_name,
                    "name_kr": shop_name,
                    "cost": 0,
                    "action": "pass",
                    "emoji": "❌",
                    "reason": "알 수 없는 챔피언",
                    "priority": 0,
                    "deck_name": "",
                })
                continue

            name_kr = champ.get("name_kr", shop_name)
            cost = champ.get("cost", 1)
            priority = 0
            action = "pass"
            emoji = "❌"
            reason = "추천 덱에 불필요"
            deck_name = ""

            # Check upgrade (already owned)
            if shop_name in my_set:
                count = my_counts.get(shop_name, 1)
                if count < 3:
                    star = 2 if count < 3 else 3
                    action = "upgrade"
                    emoji = "⭐"
                    reason = f"{star}성 업그레이드 진행 ({count}/3)"
                    priority = 85 if shop_name in carry_champions else 70
                    if shop_name in top_needed or shop_name in carry_champions:
                        priority = 95
                elif count < 9:
                    star = 3 if count >= 3 else 2
                    action = "upgrade"
                    emoji = "⭐"
                    reason = f"3성 업그레이드 진행 ({count}/9)"
                    priority = 80 if shop_name in carry_champions else 60

            # Check if needed in top decks
            elif shop_name in top_needed:
                deck = top_needed[shop_name]
                deck_name = deck.get("deck_name", "")
                is_carry = shop_name in carry_champions
                if is_carry:
                    action = "buy"
                    emoji = "✅"
                    reason = f"{deck_name} 핵심 캐리"
                    priority = 100
                else:
                    action = "buy"
                    emoji = "✅"
                    reason = f"{deck_name} 필요 유닛"
                    priority = 80
                core_missing_count += 1

            # Check secondary decks
            elif shop_name in secondary_needed:
                deck = secondary_needed[shop_name]
                deck_name = deck.get("deck_name", "")
                action = "consider"
                emoji = "🤔"
                reason = f"{deck_name} 유닛 (2순위)"
                priority = 40

            # Not needed anywhere
            else:
                action = "pass"
                emoji = "❌"
                reason = "추천 덱에 불필요"
                priority = 0

            shop_advice.append({
                "name": shop_name,
                "name_kr": name_kr,
                "cost": cost,
                "action": action,
                "emoji": emoji,
                "reason": reason,
                "priority": priority,
                "deck_name": deck_name,
            })

        # Sort by priority
        shop_advice.sort(key=lambda x: -x["priority"])

        # Reroll advice
        reroll_advice = self._get_reroll_advice(
            my_champions, top_decks, level, gold, pool, core_missing_count
        )

        # Level advice
        level_advice = self._get_level_advice(level, gold, top_decks)

        return {
            "shop_advice": shop_advice,
            "reroll_advice": reroll_advice,
            "level_advice": level_advice,
        }

    def _get_reroll_advice(self, my_champions, top_decks, level, gold, pool,
                           core_missing_count) -> dict:
        """리롤 추천 여부 판단"""
        # Interest threshold
        if gold >= 50:
            return {
                "should_reroll": False,
                "emoji": "❌",
                "reason": "이자 유지",
                "detail": f"골드 {gold}g — 50g 이자 유지 추천. 리롤보다 경제 관리 우선",
            }

        # Check if key champions are findable at current level
        needed_costs = []
        for deck in top_decks[:1]:  # Top deck
            for ni in deck.get("needed_champions", []):
                champ = self._champ_map.get(ni["name"])
                if champ:
                    needed_costs.append(champ.get("cost", 1))

        if not needed_costs:
            return {
                "should_reroll": False,
                "emoji": "❌",
                "reason": "필요 유닛 없음",
                "detail": "추천 덱이 거의 완성됨. 리롤 불필요",
            }

        # Check shop odds for needed costs
        odds = SHOP_ODDS.get(level, [0]*5)
        avg_needed_cost = sum(needed_costs) / len(needed_costs)
        primary_cost = max(set(needed_costs), key=needed_costs.count)
        cost_odds = odds[primary_cost - 1] if primary_cost <= 5 else 0

        if cost_odds < 0.10:
            # Very low probability — recommend leveling
            return {
                "should_reroll": False,
                "emoji": "❌",
                "reason": f"레벨업 추천",
                "detail": f"레벨 {level}에서 {primary_cost}코 등장 확률 {cost_odds*100:.0f}% — 레벨업 후 리롤 추천",
            }

        if core_missing_count >= 2 and gold >= 20 and cost_odds >= 0.15:
            return {
                "should_reroll": True,
                "emoji": "✅",
                "reason": f"핵심 유닛 {core_missing_count}개 부족",
                "detail": f"{primary_cost}코 등장 확률 {cost_odds*100:.0f}% — 골드 여유 있으면 리롤 추천",
            }

        if gold < 20:
            return {
                "should_reroll": False,
                "emoji": "❌",
                "reason": "골드 부족",
                "detail": f"골드 {gold}g — 경제 회복 후 리롤",
            }

        return {
            "should_reroll": False,
            "emoji": "🤔",
            "reason": "상황 판단 필요",
            "detail": f"핵심 유닛 {core_missing_count}개 부족, {primary_cost}코 확률 {cost_odds*100:.0f}%",
        }

    def _get_level_advice(self, level, gold, top_decks) -> dict:
        """레벨업 vs 리롤 조언"""
        if level >= 9:
            return {"should_level": False, "reason": "이미 고레벨 — 리롤로 덱 완성"}

        # Check what costs the top deck needs
        needed_costs = []
        for deck in top_decks[:1]:
            for ni in deck.get("needed_champions", []):
                champ = self._champ_map.get(ni["name"])
                if champ:
                    needed_costs.append(champ.get("cost", 1))

        if not needed_costs:
            return {"should_level": True, "reason": "덱 거의 완성 — 레벨업으로 전투력 강화"}

        primary_cost = max(set(needed_costs), key=needed_costs.count)
        current_odds = SHOP_ODDS.get(level, [0]*5)
        next_odds = SHOP_ODDS.get(level + 1, [0]*5)

        curr_pct = current_odds[primary_cost - 1] if primary_cost <= 5 else 0
        next_pct = next_odds[primary_cost - 1] if primary_cost <= 5 else 0

        if next_pct > curr_pct * 1.3 and gold >= 20:
            return {
                "should_level": True,
                "reason": f"레벨{level+1}에서 {primary_cost}코 확률 {curr_pct*100:.0f}%→{next_pct*100:.0f}% 상승"
            }

        return {
            "should_level": False,
            "reason": f"현재 레벨에서 {primary_cost}코 확률 {curr_pct*100:.0f}%로 충분"
        }

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
