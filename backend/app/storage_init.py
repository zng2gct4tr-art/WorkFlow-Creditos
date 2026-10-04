"""Idempotent private-container initialization; preserve existing access policies."""

import time
from .documents import ensure_bucket


def initialize():
    for attempt in range(12):
        try:
            ensure_bucket()
            print("Private document storage initialized with encryption.")
            return
        except Exception:
            if attempt == 11:
                raise RuntimeError(
                    "Private document storage unavailable or insecure; startup blocked."
                ) from None
            time.sleep(2)


if __name__ == "__main__":
    initialize()
