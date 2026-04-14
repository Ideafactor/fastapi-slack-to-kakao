import re

import httpx
from loguru import logger

from app.config import settings


class SlackRateLimitError(Exception):
    """슬랙 API Rate Limit(429) 에러. retry_after 초 포함."""

    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(f"Slack rate limited, retry after {retry_after}s")


def _check_slack_response(resp: httpx.Response, context: str) -> dict:
    """슬랙 API 응답 검사. 429는 SlackRateLimitError, 그 외 오류는 RuntimeError."""
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "60"))
        logger.warning(f"[Slack] Rate limited on {context}, retry_after={retry_after}s")
        raise SlackRateLimitError(retry_after=retry_after)

    data = resp.json()
    if not data.get("ok"):
        error = data.get("error", "unknown_error")
        logger.error(f"[Slack] {context} failed: {error}")
        raise RuntimeError(f"Slack {context} failed: {error}")
    return data


class SlackService:
    BASE_URL = "https://slack.com/api"

    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}",
            "Content-Type": "application/json",
        }

    def _make_channel_name(self, user_key: str) -> str:
        """카카오 userKey → 슬랙 채널명 변환.

        슬랙 규칙: 영소문자, 숫자, 하이픈, 밑줄만 허용, 최대 80자.
        """
        safe = re.sub(r"[^a-z0-9]", "", user_key.lower())[:16]
        name = f"cs-kakao-{safe}" if safe else f"cs-kakao-{abs(hash(user_key)) % 10**8}"
        return name[:80]

    def create_channel(self, user_key: str) -> dict:
        """슬랙 채널 생성 후 채널 ID와 이름 반환."""
        channel_name = self._make_channel_name(user_key)
        with httpx.Client() as client:
            resp = client.post(
                f"{self.BASE_URL}/conversations.create",
                headers=self._headers,
                json={"name": channel_name, "is_private": False},
                timeout=10,
            )
        data = _check_slack_response(resp, "conversations.create")
        channel = data["channel"]
        logger.info(f"Slack channel created: {channel['id']} ({channel_name}) for {user_key}")
        return {"channel_id": channel["id"], "channel_name": channel_name}

    def post_message(
        self,
        channel_id: str,
        text: str,
        username: str | None = None,
        icon_url: str | None = None,
    ) -> str:
        """슬랙 채널에 메시지 전송. 슬랙 ts(타임스탬프) 반환."""
        payload: dict = {"channel": channel_id, "text": text}
        if username:
            payload["username"] = username
        if icon_url:
            payload["icon_url"] = icon_url

        with httpx.Client() as client:
            resp = client.post(
                f"{self.BASE_URL}/chat.postMessage",
                headers=self._headers,
                json=payload,
                timeout=10,
            )
        data = _check_slack_response(resp, "chat.postMessage")
        ts: str = data["ts"]
        logger.info(f"Message posted to {channel_id} ts={ts}")
        return ts

    def upload_file(
        self,
        channel_id: str,
        data: bytes,
        filename: str,
        mimetype: str,
        title: str | None = None,
    ) -> str:
        """슬랙 파일 업로드 (3단계 신규 API).

        1. files.getUploadURLExternal → upload_url, file_id 획득
        2. upload_url에 바이너리 POST
        3. files.completeUploadExternal로 채널에 결합 → ts 반환
        """
        # 1단계: 업로드 URL 획득
        with httpx.Client() as client:
            resp = client.post(
                f"{self.BASE_URL}/files.getUploadURLExternal",
                headers=self._headers,
                json={"filename": filename, "length": len(data)},
                timeout=10,
            )
        meta = _check_slack_response(resp, "files.getUploadURLExternal")
        upload_url: str = meta["upload_url"]
        file_id: str = meta["file_id"]

        # 2단계: 바이너리 데이터 업로드
        with httpx.Client() as client:
            resp = client.post(
                upload_url,
                content=data,
                headers={"Content-Type": mimetype},
                timeout=60,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Slack file binary upload failed: HTTP {resp.status_code}")

        # 3단계: 채널에 파일 결합
        complete_payload: dict = {
            "files": [{"id": file_id, "title": title or filename}],
            "channel_id": channel_id,
        }
        with httpx.Client() as client:
            resp = client.post(
                f"{self.BASE_URL}/files.completeUploadExternal",
                headers=self._headers,
                json=complete_payload,
                timeout=10,
            )
        result = _check_slack_response(resp, "files.completeUploadExternal")
        ts: str = result.get("files", [{}])[0].get("timestamp", "")
        logger.info(f"File uploaded to {channel_id}: {filename} ({len(data)} bytes)")
        return ts

    def archive_channel(self, channel_id: str) -> None:
        """슬랙 채널 아카이브."""
        with httpx.Client() as client:
            resp = client.post(
                f"{self.BASE_URL}/conversations.archive",
                headers=self._headers,
                json={"channel": channel_id},
                timeout=10,
            )
        try:
            _check_slack_response(resp, "conversations.archive")
        except RuntimeError as e:
            # already_archived는 무해한 오류 — 경고만 출력
            logger.warning(f"conversations.archive: {e} | channel={channel_id}")
