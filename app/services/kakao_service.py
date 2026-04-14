import httpx
from loguru import logger


class KakaoService:
    """카카오 상담톡 API 클라이언트 (아웃바운드 메시지 전송용)."""

    def __init__(self, api_url: str, admin_key: str) -> None:
        self._api_url = api_url
        self._admin_key = admin_key
        self._headers = {
            "Authorization": f"KakaoAK {admin_key}",
            "Content-Type": "application/json",
        }

    def send_image(self, user_key: str, image_data: bytes, mimetype: str) -> None:
        """카카오 상담톡으로 이미지 발송 (multipart/form-data)."""
        import io

        files = {"file": (f"image.{mimetype.split('/')[-1]}", io.BytesIO(image_data), mimetype)}
        headers = {"Authorization": f"KakaoAK {self._admin_key}"}
        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{self._api_url}/message/image",
                    headers=headers,
                    data={"userKey": user_key},
                    files=files,
                    timeout=15,
                )
            resp.raise_for_status()
            logger.info(f"Kakao image sent to {user_key} ({len(image_data)} bytes)")
        except httpx.HTTPError as e:
            logger.error(f"Kakao send_image failed: {e} | user_key={user_key}")
            raise

    def send_message(self, user_key: str, text: str) -> None:
        """카카오 상담톡으로 텍스트 메시지 발송."""
        payload = {
            "userKey": user_key,
            "message": {"text": text},
        }
        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{self._api_url}/message/send",
                    headers=self._headers,
                    json=payload,
                    timeout=5,
                )
            resp.raise_for_status()
            logger.info(f"Kakao message sent to {user_key}")
        except httpx.HTTPError as e:
            logger.error(f"Kakao send_message failed: {e} | user_key={user_key}")
            raise
