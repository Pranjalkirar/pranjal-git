# PromoScout AI

This repository hosts the code-only prototype for Kuku AI Generalist Problem 1. It discovers 20-60 second candidate promo windows from timestamped microdrama screenplays.

> The supplied screenplay pack and all derived dialogue/raw outputs are confidential and intentionally excluded.

## Run

```bash
python run_promoscout.py /path/to/screenplay-pack.zip --out promoscout_run --mode baseline
```

Python 3.10+; baseline pipeline uses only the standard library. See `README_kuku_P1.md` for architecture, assumptions, evaluation and limitations.
