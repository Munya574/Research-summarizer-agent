# Research Summarizer Agent

An autonomous agent that polls the [Nightshift AGI](https://nightshift-agi.com) job marketplace, accepts research-paper summarization jobs, fetches each paper, summarizes it with Claude, and submits the result as proof of completion.

## How it works

```
Poll Nightshift (every 30 s)
  └─ Filter jobs whose title/description mention research keywords
       └─ Accept job  →  extract paper URL  →  fetch HTML  →  Claude summary  →  submit proof
```

### Summary format

Every submitted proof includes:

| Section | Description |
|---|---|
| **One-Liner** | Single sentence capturing the core contribution |
| **Problem** | The gap or challenge the paper addresses |
| **Method** | Key techniques or approach used |
| **Key Findings** | Most important results / conclusions |
| **Limitations** | Weaknesses or future work noted by the authors |
| **Who Should Read This** | Ideal audience and why |

---

## Prerequisites

- Python 3.11 or later
- An [Anthropic API key](https://console.anthropic.com/)
- A Nightshift AGI account with a provider profile

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd Research-summarizer-agent
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
ANTHROPIC_API_KEY=sk-ant-...          # from console.anthropic.com
NIGHTSHIFT_SESSION_COOKIE=sb-xxx-auth-token=...  # see below
NIGHTSHIFT_PROFILE_ID=your-profile-id
NIGHTSHIFT_BASE_URL=https://nightshift-agi.com   # leave as-is
```

#### Getting your Nightshift session cookie

1. Log in to [nightshift-agi.com](https://nightshift-agi.com) in your browser.
2. Open DevTools → **Application** (Chrome) or **Storage** (Firefox) → Cookies.
3. Find the cookie whose name starts with `sb-` and ends with `-auth-token`.
4. Copy the **name=value** pair (e.g. `sb-abc-auth-token=eyJ...`) into `NIGHTSHIFT_SESSION_COOKIE`.

#### Finding your profile ID

Go to your Nightshift profile page. The ID appears in the URL:
`https://nightshift-agi.com/profile/YOUR_PROFILE_ID`

---

## Running the agent

```bash
python agent.py
```

The agent logs its activity to stdout. Press **Ctrl+C** to stop.

```
2026-05-20 14:00:00 [INFO] agent — Research Summarizer Agent running. Poll interval: 30s, max 3 jobs/cycle.
2026-05-20 14:00:00 [INFO] agent — No new research jobs found (total open: 5).
2026-05-20 14:00:30 [INFO] agent — Found 1 new research job(s); processing 1 this cycle.
2026-05-20 14:00:30 [INFO] agent — [job-123] Starting — Summarize this arXiv paper: ...
2026-05-20 14:00:30 [INFO] nightshift_client — Accepted job job-123
2026-05-20 14:00:31 [INFO] agent — [job-123] Fetching paper from https://arxiv.org/abs/2301.00001
2026-05-20 14:00:33 [INFO] agent — [job-123] Summarizing with Claude (3842 chars of content)
2026-05-20 14:00:36 [INFO] nightshift_client — Proof submitted for job job-123
2026-05-20 14:00:36 [INFO] agent — [job-123] Completed successfully
```

---

## File overview

| File | Purpose |
|---|---|
| `agent.py` | Main polling loop and job orchestration |
| `nightshift_client.py` | Nightshift REST API wrapper (list / accept / submit) |
| `summarizer.py` | Paper fetching (requests + BeautifulSoup) and Claude summarization |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |

---

## Rate limits & concurrency

| Limit | Value |
|---|---|
| Nightshift poll interval | 30 seconds (~2 req/min) |
| Jobs processed per cycle | 3 (free-tier: max 5 concurrent) |
| Claude model | `claude-sonnet-4-6` |

The system prompt is cached via Anthropic's prompt caching feature, reducing token costs on repeated summarizations.

---

## Troubleshooting

**`Missing required env vars`** — make sure `.env` is present and all three variables are set.

**`HTTP 401` from Nightshift** — your session cookie has expired. Log in again and update `NIGHTSHIFT_SESSION_COOKIE`.

**`HTTP 409` on accept** — another agent accepted the job first; it is skipped automatically.

**`URL returns a raw PDF`** — the job posted a direct PDF link. arXiv PDF links are auto-converted to abstract pages, but other raw PDFs are skipped with an error proof.

**No jobs appearing** — verify the job titles/descriptions on Nightshift contain words like `summarize`, `paper`, `arxiv`, `research`, `article`, or `study`.
