# Suie - Patchwork Patch Ranking Application

Suie is a Python application that mirrors state from a Patchwork instance and ranks patches by how ready they are to be applied. It provides an interactive web UI for reviewing active patch series.

## Features

- **State Mirroring**: Tracks patches, series, checks, and comments from Patchwork via the REST API
- **Event Polling**: Continuously monitors for changes using the Patchwork events API
- **Interactive Web UI**: Static HTML page with JavaScript for browsing and filtering patches
- **Configurable Scoring**: Uses a Python DSL for defining patch ranking rules
- **Developer Database**: Maps developers to companies and tracks reviewer scores

## Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy the sample configuration and customize it:

```bash
cp config.yaml.sample config.yaml
# Edit config.yaml with your Patchwork instance details
```

## Configuration

Edit `config.yaml` to configure:

- **Patchwork API**: URL, project, and user agent
- **State**: How far back to look for active series (default: 7 days)
- **UI**: Output path, expected checks, display options
- **Scoring**: Path to your custom scoring function
- **Database**: Paths to mailmap and developer statistics files

## Usage

### Initialize and run continuously

```bash
python run.py --config config.yaml
```

This will:
1. Initialize state by fetching recent series
2. Generate the initial web UI
3. Poll for events every 5 minutes (configurable)
4. Regenerate UI when state changes

### Initialize only (no polling)

```bash
python run.py --config config.yaml --init-only
```

### Custom poll interval

```bash
python run.py --config config.yaml --poll-interval 600  # Poll every 10 minutes
```

## Web UI

After running, open `output/index.html` in your browser to see:

- List of active series sorted by priority
- Series metadata (ID, author, title, age, delegates)
- Delegate badges showing who is assigned to patches
- Check status (failed/missing checks highlighted)
- Expandable rows to see individual patches with their delegates
- Filters for inactive series and delegates

The UI automatically calculates relative timestamps (e.g., "2h ago").

### UI Features:

- **Dark Mode**: Toggle between light and dark themes
  - Automatically detects system preference on first load
  - Preference saved in browser's localStorage
  - Smooth transition animations
- **Series View**: Shows series ID, author, title, age, score, state, assigned delegates, and check status
  - **Score**: Numeric priority score (lower = higher priority)
  - **State**: Series state badge (e.g., new, accepted, rejected, superseded)
    - Determined from patch states: accepted (green), rejected (red), under-review (orange), new (blue), archived/superseded (gray)
    - Shows "accepted (partial)" if some patches are accepted and others are not
  - Check status aggregated across all patches (per check type):
    - **Missing**: If any patch is missing the check
    - **Failed/Warning**: If any patch failed/warned (and none are missing)
    - **Passing**: Only if ALL patches passed the check
  - Automatically deduplicates retried checks (keeps only the latest result)
  - Failed/missing checks shown individually for quick identification
  - Passing checks summarized as "✓ N" to save space
- **Patch Details**: Expand any series to see individual patches with:
  - Patch name with failed checks displayed as rows underneath:
    - Each failed check shows: check name + description
    - Clickable to open target URL (e.g., CI build page)
    - Styled with red accent for visibility
  - Assigned delegate (if any)
  - Reviewers (extracted from Reviewed-by, Acked-by, Tested-by tags)
  - Check summary showing only missing checks and passing count
  - Score and scoring comments
- **Filtering**: Filter by delegate to see only series with patches assigned to specific people
  - Delegate filter updates the URL (e.g., `?delegate=john`)
  - Bookmarkable/shareable filtered views
- **Hide Inactive**: Toggle to hide archived or completed series

## Custom Scoring

Create your own scoring function to customize patch ranking. See `scoring/example_scorer.py` for a template.

Your scoring function receives a `ScoringContext` object with:

- `patch`: The patch being scored
- `series`: The series containing the patch
- `checks`: Raw list of checks for this patch (for advanced use)
- `comments`: List of comments on this patch
- `cover_letter`: Series cover letter (if any)
- `cover_comments`: Comments on the cover letter
- `dev_db`: Developer database for looking up scores and companies

**Check Information (Structured):**

- `check_outcomes`: Dictionary mapping expected check names to outcomes (`pass`, `warning`, `fail`, `missing`)
  - Only includes checks from the `expected_checks` configuration
  - Automatically handles check deduplication (keeps latest result)
- `additional_checks`: List of check dictionaries for checks not in `expected_checks` config
  - Useful for discovering new/unexpected checks

**Helper Methods:**

- `context.get_author_email()`
- `context.get_author_company()`
- `context.get_author_reviewer_score()`
- `context.get_external_review_tags()` - Review tags from outside author's company
- `context.has_external_reviews()`
- `context.get_check_status(context_name)` - (Legacy) Get raw check status
- `context.get_failed_checks()` - (Legacy) Get raw failed checks
- `context.get_missing_checks(expected_checks)` - (Legacy) Get missing checks

**Scoring:**

Return a numeric score (lower = higher priority). Add diagnostic comments via `patch_score.add_comment()`.

Example:
```python
def score_patch(context, patch_score):
    score = 0.0

    # Process expected checks from configuration
    for check_name, outcome in context.check_outcomes.items():
        if outcome == 'fail':
            score += 200
        elif outcome == 'warning':
            score += 50
        elif outcome == 'missing':
            score += 100

    # Check for unexpected check failures
    if context.additional_checks:
        additional_failed = [c for c in context.additional_checks
                            if c.get('state') in ['fail', 'warning']]
        if additional_failed:
            score += 50

    return score
```

## Request Logging

All Patchwork API requests are logged to `output/patchwork_requests.json` with:

- Timestamp
- URL
- Duration (milliseconds)
- Object count
- Errors (if any)

This helps track API usage and debug issues.

## Project Structure

```
suie/
├── config.yaml.sample       # Sample configuration
├── requirements.txt         # Python dependencies
├── run.py                   # Main entry point
├── README.md                # This file
├── prompts/                 # Sample data files
│   ├── patchwork.yaml       # Patchwork API specification
│   ├── db.json.sample       # Sample mailmap/corpmap
│   └── ml-stats.json.sample # Sample developer statistics
├── scoring/                 # Scoring functions
│   └── example_scorer.py    # Example scoring function
└── suie/                    # Main package
    ├── __init__.py
    ├── main.py              # Application entry point
    ├── patchwork_client.py  # Patchwork API client
    ├── state.py             # State manager
    ├── poller.py            # Event poller
    ├── scoring.py           # Scoring engine
    └── ui_generator.py      # Web UI generator
```

## Development

To modify the UI:

- Edit the `HTML_TEMPLATE` in `suie/ui_generator.py`
- The template uses Jinja2 syntax for server-side rendering
- JavaScript in the template handles client-side interactivity

To modify scoring:

- Create a new Python file with your scoring function
- Update `config.yaml` to point to your function
- The function receives a `ScoringContext` and returns a float

## License

This is free and unencumbered software released into the public domain.
