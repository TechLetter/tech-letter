"""요약 모델 폴백 체인 저장소 통합 테스트."""

from __future__ import annotations

import pytest

from techletter.core.errors import InvalidRequestError
from techletter.core.llm.model_preferences import COLLECTION, ModelPreferenceStore
from techletter.core.llm.stats import ModelPurpose
from techletter.settings import RouterSettings

pytestmark = pytest.mark.integration


def _settings() -> RouterSettings:
    return RouterSettings(
        SUMMARY_MODEL_PREFERENCE="env/summary",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )


@pytest.fixture
async def store(mongo_db):
    await mongo_db[COLLECTION].delete_many({})
    return ModelPreferenceStore(mongo_db, _settings())


async def test_falls_back_to_settings_when_database_is_empty(store):
    """배포 직후에는 요약 기본값만 있고 다른 용도는 자동 모드다."""
    assert await store.preference(ModelPurpose.SUMMARY) == ["env/summary"]
    assert await store.preference(ModelPurpose.CHAT) == []
    assert await store.preference(ModelPurpose.PLANNER) == []
    assert store.settings_default(ModelPurpose.SUMMARY) == ["env/summary"]
    assert store.settings_default(ModelPurpose.CHAT) == []
    assert store.settings_default(ModelPurpose.PLANNER) == []


async def test_stored_preference_is_appended_after_settings_and_deduplicated(store):
    await store.set_preference(
        ModelPurpose.SUMMARY,
        ["db/one", "env/summary", "db/two", "db/one"],
    )

    assert await store.preference(ModelPurpose.SUMMARY) == [
        "env/summary",
        "db/one",
        "db/two",
    ]
    # 다른 용도는 그대로 설정값이어야 한다.
    assert await store.preference(ModelPurpose.CHAT) == []


async def test_setting_an_empty_list_reverts_to_settings(store):
    await store.set_preference(ModelPurpose.SUMMARY, ["db/one"])
    await store.set_preference(ModelPurpose.SUMMARY, [])

    assert await store.preference(ModelPurpose.SUMMARY) == ["env/summary"]


async def test_blank_entries_are_dropped(store):
    await store.set_preference(ModelPurpose.SUMMARY, ["  db/one  ", "", "   "])
    assert await store.preference(ModelPurpose.SUMMARY) == ["env/summary", "db/one"]


async def test_writing_invalidates_the_cache(store):
    """캐시 TTL을 기다리지 않고 바로 반영돼야 한다."""
    assert await store.preference(ModelPurpose.SUMMARY) == ["env/summary"]  # 캐시 채우기

    await store.set_preference(ModelPurpose.SUMMARY, ["db/fresh"])

    assert await store.preference(ModelPurpose.SUMMARY) == ["env/summary", "db/fresh"]


async def test_all_preferences_reports_the_single_summary_chain(store):
    await store.set_preference(ModelPurpose.SUMMARY, ["db/one"])

    rows = await store.all_preferences()

    assert rows == [
        {
            "purpose": "summary",
            "models": ["env/summary", "db/one"],
            "source": "database",
            "default_models": ["env/summary"],
        }
    ]


@pytest.mark.parametrize("purpose", [ModelPurpose.CHAT, ModelPurpose.PLANNER])
async def test_only_summary_preference_can_be_saved(store, purpose: ModelPurpose) -> None:
    with pytest.raises(InvalidRequestError):
        await store.set_preference(purpose, ["db/one"])
