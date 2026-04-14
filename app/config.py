from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    KAKAO_ADMIN_KEY: str
    KAKAO_API_URL: str = "https://kakao-api.example.com"  # 실제 상담톡 API URL로 교체 필요

    SLACK_BOT_TOKEN: str
    SLACK_SIGNING_SECRET: str
    SLACK_TRIAGE_CHANNEL_ID: str = ""

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET_NAME: str = ""
    S3_PUBLIC_BASE_URL: str = ""

    # 카카오 이미지 제한 (bytes)
    KAKAO_IMAGE_MAX_BYTES: int = 500 * 1024  # 500KB


settings = Settings()
