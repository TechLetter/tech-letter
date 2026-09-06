"""선호목록 저장소 — DB가 설정을 덮어쓰되, 비어 있으면 설정으로 떨어진다."""

from __future__ import annotations

import pytest

from techletter.core.llm.model_preferences import COLLECTION, ModelPreferenceStore
from techletter.core.llm.stats import ModelPurpose
from techletter.settings import RouterSettings

pytestmark = pytest.mark.integration


def _settings() -> RouterSettings:
    return RouterSettings(
        SUMMARY_MODEL_PREFERENCE="env/summary",
        CHAT_MODEL_PREFERENCE="env/chat",
        CHAT_PLANNER_MODEL_PREFERENCE="",
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )


@pytest.fixture
async def store(mongo_db):
    await mongo_db[COLLECTION].delete_many({})
    return ModelPreferenceStore(mongo_db, _settings())


async def test_falls_back_to_settings_when_database_is_empty(store):
    """배포 직후 상태 — 어드민이 손대기 전까지 동작이 바뀌면 안 된다."""
    assert await store.preference(ModelPurpose.SUMMARY) == ["env/summary"]
    assert await store.preference(ModelPurpose.CHAT) == ["env/chat"]


async def test_planner_falls_back_to_chat_when_unset(store):
    assert await store.preference(ModelPurpose.PLANNER) == ["env/chat"]


async def test_stored_preference_overrides_settings(store):
    await store.set_preference(ModelPurpose.CHAT, ["db/one", "db/two"])

    assert await store.preference(ModelPurpose.CHAT) == ["db/one", "db/two"]
    # 다른 용도는 그대로 설정값이어야 한다.
    assert await store.preference(ModelPurpose.SUMMARY) == ["env/summary"]


async def test_setting_an_empty_list_reverts_to_settings(store):
    await store.set_preference(ModelPurpose.CHAT, ["db/one"])
    await store.set_preference(ModelPurpose.CHAT, [])

    assert await store.preference(ModelPurpose.CHAT) == ["env/chat"]


async def test_blank_entries_are_dropped(store):
    await store.set_preference(ModelPurpose.CHAT, ["  db/one  ", "", "   "])
    assert await store.preference(ModelPurpose.CHAT) == ["db/one"]


async def test_writing_invalidates_the_cache(store):
    """캐시 TTL을 기다리지 않고 바로 반영돼야 한다."""
    assert await store.preference(ModelPurpose.CHAT) == ["env/chat"]  # 캐시 채우기

    await store.set_preference(ModelPurpose.CHAT, ["db/fresh"])

    assert await store.preference(ModelPurpose.CHAT) == ["db/fresh"]


async def test_all_preferences_reports_where_each_came_from(store):
    await store.set_preference(ModelPurpose.CHAT, ["db/one"])

    rows = {r["purpose"]: r for r in await store.all_preferences()}

    assert rows["chat"]["models"] == ["db/one"]
    assert rows["chat"]["source"] == "database"
    assert rows["summary"]["models"] == ["env/summary"]
    assert rows["summary"]["source"] == "settings"
