"""Nightshift AGI REST API wrapper."""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"cancelled", "completed", "accepted", "in_progress", "closed", "rejected"}


class NightshiftClient:
    """Thin wrapper around the Nightshift AGI job marketplace API."""

    def __init__(self, base_url: str, session_cookie: str, profile_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.profile_id = profile_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Cookie": session_cookie,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_open_jobs(self) -> list[dict[str, Any]]:
        """Return all currently open jobs, or [] on error."""
        url = f"{self.base_url}/api/v1/jobs"
        try:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # API may return a list directly or {"jobs": [...]}
            if isinstance(data, list):
                jobs = data
            else:
                jobs = data.get("jobs", data.get("data", []))
            # Filter client-side since the API status query param is unreliable
            available = [j for j in jobs if j.get("status") not in _TERMINAL_STATUSES]
            logger.info("Fetched %d job(s), %d available.", len(jobs), len(available))
            return available
        except requests.HTTPError as exc:
            logger.error(
                "list_open_jobs failed: %s — body: %s",
                exc,
                exc.response.text[:500] if exc.response is not None else "n/a",
            )
            return []
        except requests.RequestException as exc:
            logger.error("list_open_jobs failed: %s", exc)
            return []

    def accept_job(self, job_id: str) -> bool:
        """Accept a job. Returns True on success."""
        url = f"{self.base_url}/api/v1/jobs/{job_id}/status"
        payload = {"status": "accepted", "providerProfileId": self.profile_id}
        try:
            resp = self._session.patch(url, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info("Accepted job %s", job_id)
            return True
        except requests.HTTPError as exc:
            # 409 = already accepted by someone else — not a fatal error
            if exc.response is not None and exc.response.status_code == 409:
                logger.warning("Job %s already accepted (409), skipping", job_id)
            else:
                logger.error("accept_job %s failed: %s", job_id, exc)
            return False
        except requests.RequestException as exc:
            logger.error("accept_job %s failed: %s", job_id, exc)
            return False

    def submit_proof(self, job_id: str, proof_text: str) -> bool:
        """Submit completion proof for a job. Returns True on success."""
        url = f"{self.base_url}/api/v1/jobs/{job_id}/proofs"
        payload = {"proofText": proof_text}
        try:
            resp = self._session.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info("Proof submitted for job %s", job_id)
            return True
        except requests.RequestException as exc:
            logger.error("submit_proof %s failed: %s", job_id, exc)
            return False
