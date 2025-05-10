## notion_df

<!--

[//]: # (TODO: introduction)

Automate your Notion documents. Create your own routine with the human-friendly editor.  
Notion 편집을 자동화하세요. 에디터 도구를 이용해 여러분만의 편집 루틴을 직접 만들 수 있습니다.
-->

### Setup Runtime

```sh
# MacOS
brew install hatch

# Ubuntu
sudo apt install pipx
pipx ensurepath
pipx install hatch

# ---
hatch env create
```

#### Run

```sh
# Interactive
hatch shell

# One-time
hatch run python -m app.routine.main
```

#### Test

```sh
## Ruff
RUFF_VERSION=0.8.2
# Add to your PATH: ${HOME}/.local/bin
# https://github.com/astral-sh/ruff/releases
curl --proto '=https' --tlsv1.2 -LsSf https://github.com/astral-sh/ruff/releases/download/${RUFF_VERSION}/ruff-installer.sh | sh
ruff --version
# ruff-lsp is feature for IDE. Details: https://github.com/astral-sh/ruff-lsp
brew install --ignore-dependencies ruff-lsp

## Cloc
# https://github.com/AlDanial/cloc
brew install cloc
```
