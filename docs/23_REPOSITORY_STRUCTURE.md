# Структура репозитория

**Статус:** Draft 0.1

```text
project_root/
├── apps/
│   ├── integrator-api/
│   ├── site-api/
│   ├── integrator-admin/
│   ├── site-admin/
│   └── public-web/
├── services/
│   ├── source-worker/
│   ├── browser-worker/
│   ├── parser-runner/
│   ├── processing-worker/
│   ├── ai-worker/
│   ├── translation-worker/
│   ├── delivery-worker/
│   ├── editorial-worker/
│   ├── publication-worker/
│   ├── distribution-worker/
│   ├── analytics-worker/
│   ├── billing-worker/
│   └── advertising-worker/
├── packages/
│   ├── python/common/
│   ├── python/contracts/
│   ├── python/integrator-domain/
│   ├── python/site-domain/
│   ├── typescript/api-client/
│   ├── typescript/ui/
│   └── schemas/
├── migrations/
│   ├── integrator/
│   └── site/
├── prompts/
│   ├── registry.yaml
│   ├── operations/
│   └── evals/
├── tests/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   ├── security/
│   └── fixtures/
├── deploy/
│   ├── compose/
│   ├── docker/
│   ├── scripts/windows/
│   └── scripts/linux/
├── docs/
│   └── adr/
├── .github/workflows/
├── .env.example
├── pyproject.toml
├── package.json
├── pnpm-workspace.yaml
└── README.md
```

## Правила границ

Apps композиционно подключают domain/application/infrastructure, но домен не импортирует FastAPI, SQLAlchemy models провайдера или frontend. Integrator и site migrations раздельны. Общий package содержит только действительно общие primitives/contracts; запрещена скрытая shared DB model. Workers могут использовать общий image, но имеют отдельные entrypoints.

Каждый модуль содержит `domain`, `application`, `infrastructure`, `api` где применимо, и соседние tests. Точное дерево создаётся в первом implementation prompt без изменения этих границ.

