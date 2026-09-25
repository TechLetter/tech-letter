"""글 주제 목록.

필터·트렌드·챗봇 조건이 모두 이 목록을 쓴다. DB의 `aisummary.categories`에는
**한국어 이름**을 저장하고, 모델에게는 표기가 흔들리지 않는 slug로 받는다.

목록을 바꾸면 `techletter backfill topics`로 다시 분류한다 — 목록 밖의 값을 가진
글이 대상이 되므로 버전 필드가 따로 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "OTHER",
    "TOPICS",
    "TOPIC_NAMES",
    "Topic",
    "normalize_topics",
    "topic_prompt_lines",
]


@dataclass(frozen=True, slots=True)
class Topic:
    slug: str
    name: str
    definition: str


TOPICS = (
    Topic(
        "llm-apps", "LLM 활용·프롬프트", "LLM API·프롬프트로 제품 기능이나 업무 도구를 만든 사례"
    ),
    Topic(
        "ai-agents",
        "AI 에이전트·MCP",
        "AI 에이전트 설계, 도구 호출, MCP, 멀티 에이전트, LLM 기반 워크플로 자동화",
    ),
    Topic("rag-search", "RAG·검색", "검색 증강 생성, 벡터 DB, 임베딩, 검색·랭킹 시스템"),
    Topic(
        "llm-serving",
        "LLM 서빙·추론",
        "서버 추론 엔진(vLLM 등), KV 캐시, 양자화, 모델 서빙 최적화",
    ),
    Topic(
        "on-device",
        "온디바이스·엣지 AI",
        "기기 내 추론, 모델 경량화·변환(TFLite·Core ML·MLX 등), NPU, 브라우저 추론",
    ),
    Topic(
        "model-training",
        "모델 학습·파인튜닝",
        "사전학습, 파인튜닝, 강화학습(DPO·GRPO), 분산 학습, 데이터 라벨링",
    ),
    Topic(
        "ai-research", "AI 연구·모델 공개", "새 모델·논문·벤치마크 공개, 모델 아키텍처·AI 이론 연구"
    ),
    Topic("ai-coding", "AI 코딩 도구", "Claude Code·Cursor·Codex 등 AI로 개발하는 방식과 사례"),
    Topic(
        "multimodal",
        "멀티모달·비전·음성",
        "VLM, OCR, 음성 인식·합성, 이미지·영상 생성, 로보틱스",
    ),
    Topic("ai-ops", "AI 운영·평가", "LLMOps·MLOps, 모델 평가 체계, 가드레일, AI 관측"),
    Topic("gpu-infra", "GPU·AI 인프라", "GPU·가속기, CUDA, 분산 통신, HPC 클러스터"),
    Topic("kubernetes", "쿠버네티스·컨테이너", "K8s, EKS, 오토스케일링, 컨테이너 운영"),
    Topic("cloud", "클라우드 아키텍처", "클라우드 서비스 설계, 서버리스, 네트워크, 비용 최적화"),
    Topic(
        "platform-eng",
        "CI/CD·플랫폼 엔지니어링",
        "빌드·배포 파이프라인, GitOps, IaC, 사내 개발자 플랫폼",
    ),
    Topic("observability", "관측성·장애 대응", "모니터링, 로그·트레이싱, 장애 대응과 회고, SRE"),
    Topic(
        "security",
        "보안·인증",
        "인증·권한, 취약점, 개인정보 보호, 사기·이상 탐지, 공급망 보안, DevSecOps",
    ),
    Topic(
        "backend",
        "백엔드 설계·MSA",
        "서비스 구조와 의존 관계, API 설계, 도메인 설계, MSA, 분산 시스템",
    ),
    Topic("streaming", "메시징·스트리밍", "Kafka, 이벤트 기반 처리, CDC, 스트림 처리"),
    Topic("database", "데이터베이스·캐시", "RDB·NoSQL 운영, 쿼리 최적화, 캐시"),
    Topic(
        "data",
        "데이터 엔지니어링·분석",
        "데이터 파이프라인, 웨어하우스, 지표·A/B 테스트, 추천",
    ),
    Topic("frontend", "프론트엔드", "웹 프레임워크, 렌더링, 웹 성능"),
    Topic("mobile", "모바일", "iOS, Android, 크로스플랫폼"),
    Topic("design-ux", "디자인 시스템·UX", "디자인 시스템, UI 컴포넌트, UX 연구, 인터랙션 디자인"),
    Topic(
        "languages",
        "언어·알고리즘",
        "언어 기능, 런타임·컴파일러 내부, 알고리즘·코딩 테스트·수학 퍼즐 풀이",
    ),
    Topic("dev-productivity", "개발 생산성·테스트", "테스트·QA, 코드 리뷰, 개발 도구와 협업 방식"),
    Topic(
        "culture",
        "조직·문화·커리어",
        "팀 문화, 온보딩·회고 경험담, 커리어, 채용, 행사·컨퍼런스 참관기",
    ),
    Topic("quantum", "양자 컴퓨팅", "양자 알고리즘, 양자 하드웨어"),
    Topic("other", "기타", "위 어디에도 맞지 않는 글"),
)

TOPIC_NAMES = tuple(topic.name for topic in TOPICS)
OTHER = "기타"

# 모델이 slug 대신 이름을 돌려줘도 받아 준다.
_BY_KEY = {key: topic.name for topic in TOPICS for key in (topic.slug, topic.name.lower())}


def topic_prompt_lines() -> str:
    return "\n".join(f"{t.slug} | {t.name} | {t.definition}" for t in TOPICS)


def normalize_topics(values: Any, limit: int = 3) -> list[str]:
    """목록 밖의 값은 버린다. 하나도 안 남으면 `기타`."""
    if not isinstance(values, list):
        return [OTHER]
    kept: list[str] = []
    for value in values:
        name = _BY_KEY.get(str(value).strip().lower())
        if name and name not in kept:
            kept.append(name)
    return kept[:limit] or [OTHER]
