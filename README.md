# ⚔️ TFT 가이드

TFT(전략적 팀 전투) 실시간 게임 가이드 클라이언트.

화면 캡처 → 챔피언 인식 → 메타 덱 매칭 → AI 분석까지 올인원.

## 설치

```bash
cd tft-guide
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 실행

```bash
python main.py
```

브라우저에서 http://localhost:5000 접속.

### 옵션

```
--port 5000            웹 서버 포트
--llm-url URL          LLM API 엔드포인트 (OpenAI 호환)
--capture-interval 2   화면 캡처 주기(초)
--no-capture           화면 캡처 비활성화
```

## 기능

- **챔피언 선택 & 덱 추천**: 보유 챔피언 선택 → 메타 덱 매칭률/완성 가능성 계산
- **챔피언 풀 계산**: 상대 덱 입력 → 남은 풀에서 상점 확률 계산
- **AI 분석**: LLM 서버(Ollama 등) 연결 시 게임 상황 분석
- **화면 캡처**: mss 기반 실시간 캡처 (템플릿 이미지 추가 시 자동 인식)
- **데이터 업데이트**: 롤체지지 크롤링

## 구조

| 모듈 | 역할 |
|------|------|
| `capture/` | mss 화면 캡처 |
| `recognition/` | OpenCV 챔피언 인식 |
| `data/` | 챔피언/메타 데이터 + 크롤러 |
| `engine/` | 덱 추천 엔진 |
| `llm/` | LLM API 클라이언트 |
| `ui/` | Flask 웹 UI |

## 챔피언 인식 설정

`data/templates/` 폴더에 챔피언 아이콘 PNG 파일을 추가:
- 파일명: `{영문이름}.png` (예: `Jinx.png`)
- 크기: 약 60x60px 권장

## 요구사항

- Python 3.11+
- macOS / Windows
