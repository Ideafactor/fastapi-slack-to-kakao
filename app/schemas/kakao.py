from typing import Any

from pydantic import BaseModel, Field


class KakaoUserInfo(BaseModel):
    id: str | None = None
    user_key: str | None = Field(None, alias="userKey")
    nickname: str | None = None
    profile_thumbnail_image: str | None = None

    @property
    def identifier(self) -> str:
        """카카오 고객 고유 식별자 반환 (user_key 우선)"""
        return self.user_key or self.id or ""

    model_config = {"populate_by_name": True}


class KakaoMessage(BaseModel):
    text: str | None = None
    type: str | None = None
    # 미디어 파일 정보
    media_url: str | None = None
    media_type: str | None = None  # 'image', 'video', 'file' 등
    media_name: str | None = None
    media_size: int | None = None


class KakaoWebhookPayload(BaseModel):
    """카카오 상담톡 웹훅 페이로드 (인포뱅크 비즈고 API 기준)"""

    event: str | None = None
    user_key: str | None = Field(None, alias="userKey")
    app_user_id: str | None = None
    channel_id: str | None = None
    chat_id: str | None = None
    message: KakaoMessage | None = None
    user_info: KakaoUserInfo | None = None
    timestamp: str | None = None
    extra: dict[str, Any] | None = None

    @property
    def identifier(self) -> str:
        return self.user_key or self.app_user_id or ""

    @property
    def text(self) -> str:
        if self.message and self.message.text:
            return self.message.text
        return ""

    @property
    def nickname(self) -> str:
        if self.user_info and self.user_info.nickname:
            return self.user_info.nickname
        return self.identifier[:8] if self.identifier else "Unknown"

    model_config = {"populate_by_name": True}
