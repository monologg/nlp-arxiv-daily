import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _reset_fetcher_module_state(monkeypatch):
    """Clear module-level caches and neutralize tenacity waits so tests don't
    bleed state or actually sleep between retry attempts.

    - `_DAILY_CLIENT`: shared arxiv client across keywords
    - `_hf_last_call_ts`: HuggingFace Papers throttle window
    - tenacity `.wait` on retried functions: replaced with wait_none()
    """
    from tenacity import wait_none

    from nlp_arxiv_daily import fetcher

    monkeypatch.setattr(fetcher, "_DAILY_CLIENT", None, raising=False)
    monkeypatch.setattr(fetcher, "_hf_last_call_ts", 0.0, raising=False)
    for fn in (
        getattr(fetcher, "fetch_papers", None),
        getattr(fetcher, "fetch_papers_in_range", None),
        getattr(fetcher, "_hf_lookup", None),
    ):
        retry_state = getattr(fn, "retry", None)
        if retry_state is not None:
            retry_state.wait = wait_none()
