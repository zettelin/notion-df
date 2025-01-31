RUFF_VERSION=0.8.2
install.ruff:
	# Add to your PATH: ${HOME}/.local/bin
	# https://github.com/astral-sh/ruff/releases
	curl --proto '=https' --tlsv1.2 -LsSf https://github.com/astral-sh/ruff/releases/download/${RUFF_VERSION}/ruff-installer.sh | sh
	ruff --version
	# ruff-lsp is feature for IDE. Details: https://github.com/astral-sh/ruff-lsp
	brew install --ignore-dependencies ruff-lsp

test: test.ruff test.pylint test.mypy test.unit

test.pylint:
	pylint notion_df/

test.mypy:
	mypy notion_df/

test.unit:
	pytest tests/

test.vulture:
	vulture

test.ruff:
	ruff format --check ./
	ruff check ./
