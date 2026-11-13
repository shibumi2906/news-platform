FROM golang:1.25-alpine AS builder

RUN apk add --no-cache git
WORKDIR /src
RUN git init \
    && git fetch --depth 1 https://github.com/minio/minio.git 7aac2a2c5b7c882e68c1ce017d8256be2feea27f \
    && git checkout --detach FETCH_HEAD
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -o /out/minio .

FROM alpine:3.23
RUN apk add --no-cache ca-certificates curl
COPY --from=builder /out/minio /usr/local/bin/minio
COPY --from=builder /src/LICENSE /usr/share/licenses/minio/LICENSE
ENTRYPOINT ["minio"]
