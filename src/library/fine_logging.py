"""Logging

Based on: https://github.com/mCodingLLC/VideosSampleCode/blob/master/videos/135_modern_logging

Example json to load with def setup_logging:

{
  "version": 1,
  "disable_existing_loggers": false,
  "formatters": {
    "simple": {
      "format": "[%(levelname)s|%(module)s|L%(lineno)d] %(asctime)s: %(message)s",
      "datefmt": "%Y-%m-%dT%H:%M:%S%z"
    },
    "json": {
      "()": "mylogger.MyJSONFormatter",
      "fmt_keys": {
        "level": "levelname",
        "message": "message",
        "timestamp": "timestamp",
        "logger": "name",
        "module": "module",
        "function": "funcName",
        "line": "lineno",
        "thread_name": "threadName"
      }
    }
  },
  "handlers": {
    "stderr": {
      "class": "logging.StreamHandler",
      "level": "WARNING",
      "formatter": "simple",
      "stream": "ext://sys.stderr"
    },
    "file_json": {
      "class": "logging.handlers.RotatingFileHandler",
      "level": "DEBUG",
      "formatter": "json",
      "filename": "logs/my_app.log.jsonl",
      "maxBytes": 10000,
      "backupCount": 3
    }
  },
  "loggers": {
    "root": {
      "level": "DEBUG"
    }
  }
}
"""

import datetime as dt
import json
import logging
import logging.config
import logging.handlers
from pathlib import Path
from typing import override

LOG_RECORD_BUILTIN_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JSONFormatter(logging.Formatter):
    def __init__(
        self,
        *,
        fmt_keys: dict[str, str] | None = None,
    ):
        super().__init__()
        self.fmt_keys = fmt_keys if fmt_keys is not None else {}

    @override
    def format(self, record: logging.LogRecord) -> str:
        message = self._prepare_log_dict(record)
        return json.dumps(message, default=str)

    def _prepare_log_dict(self, record: logging.LogRecord):
        always_fields = {
            "message": record.getMessage(),
            "timestamp": dt.datetime.fromtimestamp(
                record.created, tz=dt.timezone.utc
            ).isoformat(),
        }
        if record.exc_info is not None:
            always_fields["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info is not None:
            always_fields["stack_info"] = self.formatStack(record.stack_info)

        message = {
            key: msg_val
            if (msg_val := always_fields.pop(val, None)) is not None
            else getattr(record, val)
            for key, val in self.fmt_keys.items()
        }
        message.update(always_fields)

        for key, val in record.__dict__.items():
            if key not in LOG_RECORD_BUILTIN_ATTRS:
                message[key] = val

        return message


class DependencyFilter(logging.Filter):
    """Filter to only keep third party logrecords above `param`.

    logrecord: https://docs.python.org/3/library/logging.html#logrecord-attributes
    logging levels: https://docs.python.org/3/library/logging.html
    custom level handling: https://docs.python.org/3/howto/logging-cookbook.html#custom-handling-of-levels
    custom filters: https://docs.python.org/3/howto/logging-cookbook.html#configuring-filters-with-dictconfig
    """

    def __init__(self, param: int):
        self.param = param

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        is_1st_party = record.name.startswith("money") or record.name == "__main__"
        is_3rd_party = not is_1st_party
        if is_3rd_party:
            allow = record.levelno >= self.param
            return allow
        else:
            return True


def setup_logging(config_file: Path):
    with config_file.open("r") as f:
        config = json.load(f)

    logging.config.dictConfig(config)
