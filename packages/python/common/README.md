# common

Shared foundation utilities used by every app and service: config, logging,
errors, ids, time, db engine/session helpers, outbox interface.

## Logging

`common.logging` provides a single logging setup shared by all services,
backed by [Loguru](https://github.com/Delgan/loguru):

- **JSON on stdout only.** `configure_logging(log_level)` removes Loguru's
  default sink and installs exactly one JSON sink writing to stdout. No file
  sinks are ever configured — containers must not own log files; log
  collection happens at the platform layer.
- **Level via environment variable.** Callers pass `settings.log_level`
  (sourced from `LOG_LEVEL`, see `common.config.BaseAppSettings`) into
  `configure_logging`. Level names are case-insensitive.
- **Correlation ID propagation.** `bind_correlation_id(correlation_id)` sets a
  `ContextVar` that `_json_sink` reads on every log line and includes as
  `correlation_id` when present. `get_correlation_id()` reads the current
  value.

Usage:

```python
from common.logging import configure_logging, get_logger

configure_logging(settings.log_level)
logger = get_logger(__name__)
logger.info("startup", instance_id=settings.instance_id)
```

Each JSON line has the shape:

```json
{"timestamp": "2026-08-06T12:00:00.123456Z", "level": "INFO", "event": "startup", "logger": "integrator_api.main", "correlation_id": "...", "instance_id": "..."}
```

`timestamp` and `correlation_id` are always UTC ISO-8601 / present-when-bound
respectively; any other keyword arguments passed to `logger.info(...)` etc.
are merged in as-is.
