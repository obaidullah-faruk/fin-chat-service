import os
import secrets

from fastapi import Header, HTTPException, status


def verify_internal_caller(
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
) -> None:
    expected_key = os.environ.get("INTERNAL_API_KEY", "")
    if not expected_key or not x_internal_key or not secrets.compare_digest(x_internal_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal access only",
        )

