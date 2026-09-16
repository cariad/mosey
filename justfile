local: markdown lint typing test

fix:
  uv run ruff check --fix .
  uv run ruff format .
  uv run rumdl check --fix .

lint:
  uv run ruff check .
  uv run ruff format --check .

markdown:
  uv run rumdl check .

test:
  uv run pytest

typing:
  uv run pyright
