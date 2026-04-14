from typing import Any

from pydantic import BaseModel


class SlackUrlVerification(BaseModel):
    token: str
    challenge: str
    type: str


class SlackEventMessage(BaseModel):
    type: str
    channel: str | None = None
    user: str | None = None
    text: str | None = None
    ts: str | None = None
    bot_id: str | None = None
    display_as_bot: bool | None = None
    subtype: str | None = None
    files: list[dict[str, Any]] | None = None


class SlackEventCallback(BaseModel):
    token: str | None = None
    type: str
    team_id: str | None = None
    api_app_id: str | None = None
    event: SlackEventMessage | None = None
    challenge: str | None = None
    event_id: str | None = None
    event_time: int | None = None
