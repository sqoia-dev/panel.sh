# panel.sh: Private White-Label Digital Signage Platform

panel.sh (also referred to as Anthias) is a self-hosted digital signage platform built around Dockerized services for content management, playback, and device orchestration.

## Architecture at a Glance
- **NGINX** (`anthias-nginx`) forwards requests to the backend, serves static assets, and proxies WebSocket traffic.
- **Web app** (`anthias-server`) provides the user-facing UI and Django backend.
- **Viewer** (`anthias-viewer`) renders scheduled content on connected screens.
- **Celery** (`anthias-celery`) handles asynchronous jobs such as asset cleanup.
- **WebSocket** (`anthias-websocket`) bridges real-time communication from NGINX to the backend.
- **Redis** supplies caching, message brokering, and data storage; SQLite is used for persistent asset metadata.

## Local Development
The repository ships with a containerized development environment to keep tooling consistent.

### Prerequisites
- Docker with Buildx enabled (you may need `docker buildx create --use`).
- Git and a POSIX-compatible shell.

### Start the development stack
Run the helper script from the repo root:

```bash
./bin/start_development_server.sh
```

This installs the required Python (via `pyenv`) and Poetry toolchain inside a Docker container and brings up the default services. Once running, visit `http://localhost:8000`.

Stop the stack when finished:

```bash
docker compose -f docker-compose.dev.yml down
```

### Web assets
Webpack runs inside the `anthias-server` container:

```bash
docker compose -f docker-compose.dev.yml exec anthias-server npm run dev
```

Frontend linting/formatting helpers:

```bash
docker compose -f docker-compose.dev.yml exec anthias-server npm run lint:check
docker compose -f docker-compose.dev.yml exec anthias-server npm run format:check
```

### Django admin access
Create a superuser inside the dev stack to access `/admin/`:

```bash
export COMPOSE_FILE=docker-compose.dev.yml
docker compose exec anthias-server python manage.py createsuperuser
```

## Testing
Build and start the test services, then run the suites:

```bash
poetry run python -m tools.image_builder \
  --dockerfiles-only \
  --disable-cache-mounts \
  --service celery \
  --service redis \
  --service test

docker compose -f docker-compose.test.yml up -d --build

docker compose -f docker-compose.test.yml exec anthias-test bash ./bin/prepare_test_environment.sh -s

# Unit tests
 docker compose -f docker-compose.test.yml exec anthias-test ./manage.py test --exclude-tag=integration
# Integration tests
 docker compose -f docker-compose.test.yml exec anthias-test ./manage.py test --tag=integration
```

## Python linting
`ruff` is used for linting. To run it locally with Poetry:

```bash
poetry install --only=dev-host
poetry run ruff check .
```

You can also run the CI lint workflow locally with [`act`](https://nektosact.com/):

```bash
act -W .github/workflows/python-lint.yaml
```

## Additional resources
- [Developer documentation](docs/developer-documentation.md) for deeper component details and workflows.
- [QA checklist](docs/qa-checklist.md) for manual verification guidance.
- [Docs README](docs/README.md) for operational notes such as log collection.
