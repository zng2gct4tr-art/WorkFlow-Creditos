import json, logging, sys
from collections import Counter
from datetime import datetime, timezone

requests = Counter()


class JsonFormatter(logging.Formatter):
    def format(self, record):
        fields = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("request_id", "status", "duration_ms", "document_id"):
            if hasattr(record, key):
                fields[key] = getattr(record, key)
        return json.dumps(fields, separators=(",", ":"))


def configure():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("workflow")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # Signed download tokens and password reset tokens must never enter access logs.
    logging.getLogger("uvicorn.access").disabled = True
