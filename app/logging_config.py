import logging
import re
import sys

import structlog
import structlog.typing

# Anything matching these patterns gets redacted regardless of which field it's in.
# This is intentionally broad (key-name match AND value-pattern match) so a developer
# can't accidentally leak a secret by putting it in a field name we didn't anticipate.
_REDACT_KEY_PATTERN = re.compile(r"(api[_-]?key|password|secret|signature|x-amz-signature)", re.IGNORECASE)
_REDACT_VALUE_PATTERN = re.compile(r"(X-Amz-Signature=[^&\s]+|AWS4-HMAC-SHA256[^\s]*)", re.IGNORECASE)


def _redact_processor(
    logger: structlog.typing.WrappedLogger, method_name: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    for key in list(event_dict.keys()):
        if _REDACT_KEY_PATTERN.search(key):
            event_dict[key] = "[REDACTED]"
            continue
        value = event_dict[key]
        if isinstance(value, str) and _REDACT_VALUE_PATTERN.search(value):
            event_dict[key] = _REDACT_VALUE_PATTERN.sub("[REDACTED]", value)
    return event_dict


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
