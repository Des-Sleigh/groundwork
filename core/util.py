"""Small shared utilities: structured logging and a retry decorator.

No third-party dependencies — keeps the core importable everywhere (tests,
offline, CI).
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import time
from typing import Callable, TypeVar

_T = TypeVar("_T")


def extract_json(text: str):
    """Best-effort parse of a JSON object/array from model output.

    Strips ```json fences, tolerates surrounding prose, and falls back to the
    first balanced {...} span. Returns the parsed value or None.
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        pass
    start = candidate.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(candidate)):
            if candidate[i] == "{":
                depth += 1
            elif candidate[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start:i + 1])
                    except (ValueError, TypeError):
                        break
        start = candidate.find("{", start + 1)
    return None


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("GROUNDWORK_LOG_LEVEL", "INFO").upper())
        logger.propagate = False
    return logger


def retry(attempts: int = 3, base_delay: float = 0.5, max_delay: float = 8.0,
          exceptions: tuple = (Exception,), sleep: Callable[[float], None] = time.sleep):
    """Retry a callable with exponential backoff.

    The Anthropic SDK already retries 429/5xx; this wraps *our* tool calls
    (search/fetch) which hit third-party services. `sleep` is injectable so
    tests don't actually wait.
    """

    def decorator(fn: Callable[..., _T]) -> Callable[..., _T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> _T:
            log = get_logger(fn.__module__)
            last: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:  # noqa: BLE001 — caller chooses the set
                    last = e
                    if attempt == attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    log.warning("%s failed (attempt %d/%d): %s; retrying in %.1fs",
                                fn.__name__, attempt, attempts, e, delay)
                    sleep(delay)
            assert last is not None
            raise last

        return wrapper

    return decorator
