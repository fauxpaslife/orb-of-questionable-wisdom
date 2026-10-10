# Orb of Questionable Wisdom

A haunted Magic 8 Ball powered by local Ollama models. Ask a question, shake the orb, and receive statistically questionable advice.

## Windows setup

1. Install [Python 3.11+](https://www.python.org/downloads/windows/) and enable **Add Python to PATH**.
2. Install and start [Ollama 0.35+](https://ollama.com/download/windows).
3. Download the project ZIP and extract it to a folder you can write to.
4. Double-click **install.bat**; accept the optional local decision-model download, or run the printed `ollama pull` command later.
5. Double-click **start.bat**; the orb opens in your browser at `http://127.0.0.1:8768`.
6. Type a question, then drag the orb or focus it and press **Space**; keep the server terminal open.
7. Use the gear to select local models; Nemotron Nano is the default voice, with canned fallback.

The installer creates `.venv`, installs pinned Python dependencies, checks Ollama, and generates the launcher. Rerunning it preserves your settings and local data. Model downloads require your choice and may be several GB.

## What is available

The current P2 version includes the single-orb loop, settings, background discovery, prewarming, generated or canned voice, reduced motion, and labeled dice fallback. Seven confidence candles surround a larger floating orb with drifting murk. A seance reveal, optional local sound, and PNG share cards are available. The prophecy ledger, additional modes, and persona selection remain for later phases.

Decision models use `/v1/systemone`; voice models use `/api/chat`. The configured default oracle is `tev1:4b`; the selectable default voice is `nemotron-3-nano:4b`. Choose another installed local chat model or canned quips in settings. A slow or invalid voice response falls back to a canned line without delaying the reveal.

## How to read an omen

The selected decision model makes its own judgment from your question and the available context. Its interpretation gives the orb its character: changing decision models can change the verdict and confidence. Nemotron supplies the voice; it cannot change the chosen verdict.

“ASK LATER” is a legitimate judgment when the model finds insufficient evidence or no matching answer. Questions about an unknown future may receive it often—even confidently. The orb preserves that judgment instead of forcing a more entertaining answer.

Candles show the probability assigned to the **chosen verdict**, including “ASK LATER”: lit count is rounded from probability × 7. More candles mean stronger model confidence in that verdict, not a more positive answer. These probabilities are uncalibrated and do not establish real-world accuracy. Shake strength changes the theatrics only; it never changes the verdict.

## Privacy

Questions and inference stay on your machine. The server binds to `127.0.0.1`, cloud models are excluded, and the page has no telemetry, CDN, or external assets. Setup downloads Python packages and any models you explicitly approve. Settings/cache live in `data/orb.db`; they are excluded from the downloadable release.

Probabilities are **uncalibrated**. This is a toy, and its confidence does not measure real-world accuracy.

## Development

Install `requirements-dev.txt` for browser checks; `python -m unittest test_core test_install -v` runs the isolated behavior checks. `python build_release.py` creates a release ZIP from an explicit file list and scans its contents for credentials and personal paths. It excludes environments, databases, logs, test captures, and model benchmark reports. Local model integration checks are separate from the isolated tests.
