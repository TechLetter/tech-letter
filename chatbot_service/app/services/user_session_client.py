from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(slots=True)
class UserSessionClient:
    base_url: str
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "UserSessionClient":
        return cls(
            base_url=os.getenv("USER_SERVICE_BASE_URL", "http://user_service:8002").rstrip(
                "/"
            )
        )

    def get_session(self, *, user_code: str, session_id: str) -> dict[str, Any]:
        query = urlencode({"user_code": user_code})
        url = f"{self.base_url}/api/v1/chatbot/sessions/{session_id}?{query}"
        with urlopen(url, timeout=self.timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def update_memory(
        self,
        *,
        user_code: str,
        session_id: str,
        summary: str,
        covered_message_count: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        query = urlencode({"user_code": user_code})
        url = f"{self.base_url}/api/v1/chatbot/sessions/{session_id}/memory?{query}"
        body = json.dumps(
            {
                "summary": summary,
                "covered_message_count": covered_message_count,
                "status": status,
                "error_message": error_message,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            response.read()
