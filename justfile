local: markdown docs lint typing test

docs:
  uv run zensical build

fix:
  uv run ruff check --fix .
  uv run ruff format .
  uv run rumdl check --fix .

lint:
  uv run ruff check .
  uv run ruff format --check .

markdown:
  uv run rumdl check .

start-docs:
  uv run zensical serve

test:
  uv run pytest

typing:
  uv run pyright
