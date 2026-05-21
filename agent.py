"""Main polling loop — ties NightshiftClient and summarizer together."""

import logging
import os
import time

from dotenv import load_dotenv

from nightshift_client import NightshiftClient
from summarizer import extract_url_from_text, fetch_paper_content, summarize_paper

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agent")

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

RESEARCH_KEYWORDS = frozenset(
    {"summarize", "summary", "paper", "arxiv", "research", "article", "study", "abstract"}
)
MAX_JOBS_PER_CYCLE = 3   # free-tier cap: process at most 3 per poll cycle
POLL_INTERVAL = 30       # seconds between polls (~30 req/min guard)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _is_research_job(job: dict) -> bool:
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return any(kw in text for kw in RESEARCH_KEYWORDS)


def _process_job(client: NightshiftClient, job: dict, api_key: str) -> None:
    job_id = job.get("id", "?")
    title = job.get("title", "")
    description = job.get("description", "")

    logger.info("[%s] Starting — %s", job_id, title)

    if not client.accept_job(job_id):
        logger.warning("[%s] Could not accept job, skipping", job_id)
        return

    url = extract_url_from_text(description)
    if not url:
        _fail(client, job_id, "No paper URL found in the job description.")
        return

    logger.info("[%s] Fetching paper from %s", job_id, url)
    try:
        content = fetch_paper_content(url)
    except RuntimeError as exc:
        _fail(client, job_id, f"Failed to fetch paper: {exc}")
        return

    logger.info("[%s] Summarizing with Claude (%d chars of content)", job_id, len(content))
    try:
        summary = summarize_paper(content, title=title, api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        _fail(client, job_id, f"Summarization error: {exc}")
        return

    proof = f"# Research Summary: {title}\n\nSource: {url}\n\n{summary}"
    if client.submit_proof(job_id, proof):
        logger.info("[%s] Completed successfully", job_id)
    else:
        logger.error("[%s] Proof submission failed — work may be lost", job_id)


def _fail(client: NightshiftClient, job_id: str, reason: str) -> None:
    logger.error("[%s] %s", job_id, reason)
    client.submit_proof(job_id, f"Error: {reason}")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    session_cookie = os.environ.get("NIGHTSHIFT_SESSION_COOKIE")
    profile_id = os.environ.get("NIGHTSHIFT_PROFILE_ID")
    base_url = os.environ.get("NIGHTSHIFT_BASE_URL", "https://nightshift-agi.com")

    missing = [k for k, v in {
        "ANTHROPIC_API_KEY": api_key,
        "NIGHTSHIFT_SESSION_COOKIE": session_cookie,
        "NIGHTSHIFT_PROFILE_ID": profile_id,
    }.items() if not v]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")

    client = NightshiftClient(base_url, session_cookie, profile_id)
    seen_ids: set[str] = set()

    logger.info("Research Summarizer Agent running. Poll interval: %ds, max %d jobs/cycle.",
                POLL_INTERVAL, MAX_JOBS_PER_CYCLE)

    while True:
        try:
            _poll_once(client, seen_ids, api_key)
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as exc:  # noqa: BLE001
            logger.error("Unhandled error in poll loop: %s", exc, exc_info=True)
            time.sleep(POLL_INTERVAL)


def _poll_once(client: NightshiftClient, seen_ids: set[str], api_key: str) -> None:
    all_jobs = client.list_open_jobs()
    new_research = [
        j for j in all_jobs
        if _is_research_job(j) and j.get("id") not in seen_ids
    ]

    if not new_research:
        logger.info("No new research jobs found (total open: %d).", len(all_jobs))
        return

    batch = new_research[:MAX_JOBS_PER_CYCLE]
    logger.info(
        "Found %d new research job(s); processing %d this cycle.",
        len(new_research), len(batch),
    )

    for job in batch:
        seen_ids.add(job["id"])
        try:
            _process_job(client, job, api_key)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] Unexpected error: %s", job.get("id", "?"), exc, exc_info=True)


if __name__ == "__main__":
    main()
