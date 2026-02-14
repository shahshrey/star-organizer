<div align="center">

<img src="assets/banner.png" alt="Star Organizer — AI-powered GitHub Stars organization" width="100%"/>

<br/>
<br/>

<a href="https://github.com/shahshrey/star-organizer/stargazers"><img src="https://img.shields.io/github/stars/shahshrey/star-organizer?style=flat&logo=github&logoColor=white&color=gold" alt="GitHub Stars"/></a>
<a href="https://github.com/shahshrey/star-organizer/network/members"><img src="https://img.shields.io/github/forks/shahshrey/star-organizer?style=flat&logo=github&logoColor=white&color=blue" alt="Forks"/></a>
<a href="https://github.com/shahshrey/star-organizer/issues"><img src="https://img.shields.io/github/issues/shahshrey/star-organizer?style=flat&logo=github&logoColor=white&color=red" alt="Issues"/></a>
<a href="LICENSE"><img src="https://img.shields.io/github/license/shahshrey/star-organizer?style=flat&color=green" alt="License"/></a>
<a href="https://python.org"><img src="https://img.shields.io/badge/python-3.10+-3776AB?style=flat&logo=python&logoColor=white" alt="Python 3.10+"/></a>
<a href="https://platform.openai.com"><img src="https://img.shields.io/badge/GPT--4.1-412991?style=flat&logo=openai&logoColor=white" alt="GPT-4.1"/></a>

<br/>
<br/>

<p>
<strong>One command to fetch, categorize, and sync 1,200+ starred repos into 32 GitHub Lists.</strong>
</p>

<p>
  <a href="#-quickstart">Quickstart</a> •
  <a href="#-features">Features</a> •
  <a href="#%EF%B8%8F-how-it-works">How It Works</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-configuration">Configuration</a> •
  <a href="#-contributing">Contributing</a>
</p>

</div>

<br/>

<div align="center">
  <img src="assets/before-after.png" alt="Before and After — from chaos to organized GitHub Lists" width="100%"/>
</div>

<br/>

## 🌟 Why Star Organizer?

You starred that amazing library three months ago. Now you need it, but it's buried under 1,200 other repos. Sound familiar?

**Star Organizer** fixes this in under 5 minutes:

```bash
pip install -e .
star-organizer
```

That's it. An interactive menu guides you through the entire process — GPT-4.1 reads every repo's README, creates 32 perfectly tailored categories, and syncs them directly to your [GitHub Lists](https://docs.github.com/en/get-started/exploring-projects-on-github/saving-repositories-with-stars#organizing-starred-repositories-with-lists).

<br/>

## ✨ Features

<table>
<tr>
<td width="50%">

### ⚡ Blazing Fast
50 concurrent AI workers, 15 metadata workers, 8 sync workers. Your entire star collection processed in minutes, not hours.

### 🧠 AI-Powered
GPT-4.1 analyzes each repo's README, description, and topics to build categories that actually match *your* interests.

### 🔄 Incremental
Already ran it once? Next time it only processes newly starred repos. No re-categorization of existing stars.

</td>
<td width="50%">

### 🖥️ Interactive CLI
Built with Typer, Rich, and Questionary. A persistent menu session with arrow-key navigation, spinners, progress output, and a category preview table.

### 🛡️ Fault Tolerant
Adaptive rate limiting, batch splitting on errors, and checkpoint saves every 20 repos. Crashes mid-run? Pick up where you left off.

### 📋 GitHub Lists Native
Syncs directly to GitHub's built-in Lists feature via GraphQL. No external tools, no third-party services.

</td>
</tr>
</table>

<br/>

## 🚀 Quickstart

### 1. Prerequisites

| | Requirement | Purpose |
|---|---|---|
| 🐍 | [Python 3.10+](https://python.org) | Runtime |
| 🔧 | [GitHub CLI (`gh`)](https://cli.github.com/) | GraphQL API access for syncing Lists |
| 🔑 | [GitHub PAT](https://github.com/settings/tokens) | REST API access (`read:user` scope) |
| 🤖 | [OpenAI API Key](https://platform.openai.com/api-keys) | AI categorization |

### 2. Install

```bash
git clone https://github.com/shahshrey/star-organizer.git
cd star-organizer
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env → add GITHUB_TOKEN and OPENAI_API_KEY
```

```bash
gh auth login     # Authenticate GitHub CLI
gh auth status    # Verify
```

### 4. Run

```bash
star-organizer    # Interactive mode — menu guides you through everything
```

```text
╭──────────────────────────────────────────────────────────╮
│                    ⭐ Star Organizer                     │
╰─────────── Organize your GitHub stars with AI ───────────╯

? What would you like to do?
❯ Organize my stars (full pipeline)
  Organize only (skip GitHub sync)
  Sync only (push existing categories to GitHub)
  Reset & re-organize everything
  Preview current categories
  Exit
```

Use arrow keys to navigate, Enter to select. The session stays alive after each action — select **Exit** for a clean shutdown.

<br/>

## 📖 Usage

### Interactive Mode (default)

Just run with no arguments. The menu loops after each action so you can preview categories, run the pipeline, then preview again — all in one session:

```bash
star-organizer        # Opens interactive menu
star-organizer -i     # Force interactive mode
```

### Flag Mode

All flags work for scripting and CI. Passing any flag skips the interactive menu:
Use `-i` / `--interactive` to force the interactive menu even when other flags are present, and use `--no-interactive` to force non-interactive execution.

```bash
star-organizer --reset                        # Full reset + categorize + sync
star-organizer --reset --backup               # Reset with backup
star-organizer --organize-only --test-limit 5 # Test with 5 repos, no sync
star-organizer --sync-only                    # Sync existing categories to GitHub
star-organizer --no-interactive               # Force flag mode, run full pipeline
```

### CLI Flags

| Flag | Description |
|:---|:---|
| `--reset` | Full reset — delete all lists, re-categorize everything, re-sync |
| `--backup` | Back up `organized_stars.json` before resetting |
| `--organize-only` | Only categorize repos, skip GitHub sync |
| `--sync-only` | Only sync existing `organized_stars.json` to GitHub |
| `--test-limit N` | Limit to N starred repos (great for testing) |
| `-i` / `--interactive` | Force interactive menu mode |
| `--no-interactive` | Force non-interactive flag mode |
| `-v` / `--verbose` | Show detailed log output during pipeline |
| `--output-file PATH` | Custom output path for organized stars JSON |
| `--state-file PATH` | Custom path for sync state file |

You can also run as a Python module:

```bash
python -m star_organizer
```

<br/>

## ⚙️ How It Works

<div align="center">
  <img src="assets/pipeline.png" alt="Pipeline Architecture — 5 phases from fetch to save" width="100%"/>
</div>

<br/>

<details>
<summary><strong>📖 Detailed phase breakdown</strong></summary>

<br/>

| Phase | Description | Concurrency |
|---|---|---|
| **1 — Fetch** | Fetch all starred repos from GitHub REST API + load previous state from disk | Concurrent I/O |
| **2 — Metadata** | Extract README content + topics for every repo | 15 workers |
| **3 — AI Categorize** | Create 32 categories via a single LLM call, then assign each repo to its best-fit category | 50 workers, checkpoints every 20 |
| **4 — Sync** | Delete old lists, resolve repo IDs, create new lists, add repos to lists — with pipelined concurrency | 8 workers, delete/resolve run in parallel |
| **5 — Save** | Write `organized_stars.json` + sync state to disk | — |

</details>

<br/>

### Rate Limit Budget

> Star Organizer stays well within GitHub's API limits, even for large star collections.

| API | Limit | Used (~1,200 stars) | Headroom |
|:---|:---|:---|:---|
| GitHub REST | 5,000 req/hr | ~510 requests | 🟢 ~90% remaining |
| GitHub GraphQL | 5,000 pts/hr | ~100 points | 🟢 ~98% remaining |
| OpenAI | Fully parallelized | ~1,200 calls | 🟢 No throttling |

<br/>

## 🔧 Configuration

All tunable constants live in [`star_organizer/models.py`](star_organizer/models.py):

<details>
<summary><strong>View all configuration options</strong></summary>

<br/>

| Constant | Default | Description |
|:---|:---|:---|
| `MAX_GITHUB_LISTS` | `32` | Maximum categories (GitHub's hard limit) |
| `PARALLEL_CATEGORIZATION_WORKERS` | `50` | Concurrent OpenAI API calls |
| `PARALLEL_METADATA_WORKERS` | `15` | Concurrent GitHub README fetches |
| `MAX_SYNC_WORKERS` | `8` | Concurrent GraphQL sync operations |
| `BATCH_SAVE_INTERVAL` | `20` | Checkpoint save frequency during categorization |
| `ADD_BATCH_SIZE` | `10` | Repos per GraphQL add-to-list mutation |
| `REPO_LOOKUP_BATCH_SIZE` | `40` | Repos per GraphQL ID resolution query |
| `RATE_LIMIT_ITEM` | `0.3` | Min seconds between GraphQL requests |

</details>

<br/>

## 📁 Project Structure

```
star_organizer/
├── __main__.py        → python -m entry point
├── main.py            → Interactive CLI (Typer + Questionary + Rich)
├── pipeline.py        → Pipeline orchestration (phase 1–4 logic)
├── display.py         → Rich terminal output (banners, tables, spinners)
├── models.py          → Constants, Pydantic models, types
├── rate_limiter.py    → Thread-safe adaptive rate limiter
├── store.py           → JSON I/O for organized stars + sync state
├── github_client.py   → GitHub REST API (stars, READMEs)
├── github_sync.py     → GitHub GraphQL API (lists, mutations)
└── categorizer.py     → AI categorization (creation + assignment)
```

| Output File | Description |
|:---|:---|
| `organized_stars.json` | All categories with descriptions and assigned repos |
| `.sync_to_github_state.json` | Tracks which repos have been synced to GitHub Lists |

<br/>

## 🗺️ Roadmap

- [x] AI-powered categorization with GPT-4.1
- [x] Full sync to GitHub Lists via GraphQL
- [x] Incremental mode for new stars
- [x] Fault-tolerant pipeline with checkpoints
- [x] Interactive CLI with Typer, Rich, and Questionary
- [ ] Support for custom category count
- [ ] Alternative LLM providers (Anthropic, local models)
- [ ] Web UI for previewing categories before sync
- [ ] Export to other formats (Markdown, CSV)

See the [open issues](https://github.com/shahshrey/star-organizer/issues) for a full list.

<br/>

## 🤝 Contributing

Contributions are welcome! Please open an [issue](https://github.com/shahshrey/star-organizer/issues) first to discuss what you'd like to change.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push and open a Pull Request

<br/>

## 📄 License

This project is licensed under the [MIT License](LICENSE).

<br/>

---

<div align="center">

**Built with**

<a href="https://python.org"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/></a>
<a href="https://platform.openai.com"><img src="https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI"/></a>
<a href="https://langchain.com"><img src="https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangChain"/></a>
<a href="https://docs.pydantic.dev"><img src="https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic"/></a>
<a href="https://typer.tiangolo.com"><img src="https://img.shields.io/badge/Typer-009688?style=for-the-badge&logoColor=white" alt="Typer"/></a>
<a href="https://rich.readthedocs.io"><img src="https://img.shields.io/badge/Rich-000000?style=for-the-badge&logoColor=white" alt="Rich"/></a>

<br/>
<br/>

If this project helped you, consider giving it a ⭐

<a href="https://github.com/shahshrey/star-organizer/stargazers"><img src="https://img.shields.io/github/stars/shahshrey/star-organizer?style=social" alt="Star this repo"/></a>

</div>
