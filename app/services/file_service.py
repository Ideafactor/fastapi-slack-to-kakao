import io
import mimetypes

import httpx
from loguru import logger
from PIL import Image

from app.config import settings

# 카카오가 허용하는 이미지 MIME 타입
KAKAO_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif"}
# 슬랙→카카오 전송 가능한 최대 이미지 크기 (bytes)
KAKAO_IMAGE_MAX_BYTES = settings.KAKAO_IMAGE_MAX_BYTES


class FileService:
    def download(self, url: str, headers: dict | None = None) -> tuple[bytes, str]:
        """URL에서 파일 바이너리를 다운로드. (data, mimetype) 반환."""
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(url, headers=headers or {})
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "application/octet-stream")
        # 'image/jpeg; charset=...' 형태에서 mimetype만 추출
        mimetype = content_type.split(";")[0].strip()
        return resp.content, mimetype

    def download_slack_file(self, url: str) -> tuple[bytes, str]:
        """슬랙 private URL에서 파일 다운로드 (Bearer 인증 필요)."""
        headers = {"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"}
        return self.download(url, headers=headers)

    def compress_image_for_kakao(self, data: bytes, mimetype: str) -> tuple[bytes, str]:
        """카카오 이미지 크기 제한(500KB)에 맞게 압축.

        1. 이미 제한 이하이면 그대로 반환
        2. JPEG quality를 점진적으로 낮춰 압축
        3. quality 최소(20)에도 초과하면 해상도 축소 후 재시도
        """
        if len(data) <= KAKAO_IMAGE_MAX_BYTES:
            return data, mimetype

        try:
            img = Image.open(io.BytesIO(data))
            # RGBA → RGB 변환 (JPEG는 알파채널 미지원)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                mimetype = "image/jpeg"

            # 1단계: quality 조정
            for quality in range(85, 15, -10):
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                compressed = buf.getvalue()
                if len(compressed) <= KAKAO_IMAGE_MAX_BYTES:
                    logger.info(
                        f"Image compressed via quality={quality}: "
                        f"{len(data)} → {len(compressed)} bytes"
                    )
                    return compressed, "image/jpeg"

            # 2단계: 해상도 축소 (비율 유지)
            scale = 0.8
            while scale >= 0.2:
                new_w = int(img.width * scale)
                new_h = int(img.height * scale)
                resized = img.resize((new_w, new_h), Image.LANCZOS)
                buf = io.BytesIO()
                resized.save(buf, format="JPEG", quality=60, optimize=True)
                compressed = buf.getvalue()
                if len(compressed) <= KAKAO_IMAGE_MAX_BYTES:
                    logger.info(
                        f"Image resized to {new_w}x{new_h} scale={scale:.1f}: "
                        f"{len(data)} → {len(compressed)} bytes"
                    )
                    return compressed, "image/jpeg"
                scale -= 0.2

        except Exception as e:
            logger.error(f"Image compression failed: {e}")

        # 압축 실패 — 호출자에서 S3 fallback 처리
        raise ValueError(f"Cannot compress image to under {KAKAO_IMAGE_MAX_BYTES} bytes")

    def is_image(self, mimetype: str) -> bool:
        return mimetype.startswith("image/")

    def get_extension(self, filename: str, mimetype: str) -> str:
        ext = mimetypes.guess_extension(mimetype) or ""
        if not ext and "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1]
        return ext.lstrip(".")
