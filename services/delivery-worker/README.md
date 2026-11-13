# delivery-worker

Delivers immutable canonical package versions to active Site connections over signed HTTP. Each request carries the package-version idempotency key, Integrator instance ID, signing-key ID, timestamp, and HMAC-SHA256 signature.

The worker validates structured Site acknowledgements, preserves compatibility with empty successful responses, applies durable bounded retries with exponential backoff, and moves exhausted deliveries to a visible dead-letter state. Replay uses targeted outbox events and the original wire idempotency key, so it can fill missed versions without duplicating Site state.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DELIVERY_WORKER_BATCH_SIZE` | `50` | Maximum pending outbox rows per poll |
| `DELIVERY_HTTP_TIMEOUT_SECONDS` | `15` | Per-request HTTP timeout |
| `DELIVERY_MAX_ATTEMPTS` | `10` | Durable outer attempt budget |
| `DELIVERY_RETRY_BACKOFF_SECONDS` | `30` | Exponential backoff base |

Operational replay, dead-letter retry, and key rotation are exposed through the secured Integrator Admin API documented in `NEWS_INTEGRATOR_INTERFACE.md`. Secrets must never appear in responses, logs, metrics, or audit details.
