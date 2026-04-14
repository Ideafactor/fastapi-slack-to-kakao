import sys

from loguru import logger


def setup_logging() -> None:
    """JSON 구조화 로그 설정.

    - stdout에 JSON 포맷 출력
    - 레벨: INFO 이상 (개발 환경에서는 DEBUG)
    """
    logger.remove()  # 기본 핸들러 제거

    log_format = (
        "{{"
        '"time": "{time:YYYY-MM-DDTHH:mm:ss.SSSZ}", '
        '"level": "{level}", '
        '"message": "{message}", '
        '"name": "{name}", '
        '"function": "{function}", '
        '"line": {line}'
        "}}"
    )

    logger.add(
        sys.stdout,
        format=log_format,
        level="INFO",
        enqueue=True,       # 비동기 로깅 (이벤트 루프 블로킹 방지)
        backtrace=True,
        diagnose=False,     # 운영 환경에서 민감 정보 노출 방지
    )
