import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from loguru import logger

from app.config import settings


class S3Service:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        self._bucket = settings.S3_BUCKET_NAME
        self._base_url = settings.S3_PUBLIC_BASE_URL.rstrip("/")

    def upload(self, data: bytes, filename: str, mimetype: str) -> str:
        """파일을 S3에 업로드하고 공개 URL 반환.

        대용량 파일(동영상, PDF 등)을 카카오로 전송할 수 없을 때 S3에 보관하고
        다운로드 링크를 텍스트로 전송하는 fallback 용도.
        """
        key = f"attachments/{uuid.uuid4().hex}/{filename}"
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=mimetype,
                # 공개 읽기 허용 (버킷 정책으로 관리 권장)
            )
            url = f"{self._base_url}/{key}"
            logger.info(f"S3 upload success: {url} ({len(data)} bytes)")
            return url
        except (BotoCoreError, ClientError) as e:
            logger.error(f"S3 upload failed: {e}")
            raise

    def is_configured(self) -> bool:
        return bool(self._bucket and settings.AWS_ACCESS_KEY_ID)
