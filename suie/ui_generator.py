"""Web UI generator for displaying patches"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
from jinja2 import Template


logger = logging.getLogger(__name__)


class UIGenerator:
    """Generates a static HTML page with interactive JavaScript"""

    def __init__(self, output_path: str, hide_inactive_default: bool = True,
                 expected_checks: Optional[List[str]] = None):
        """
        Initialize the UI generator

        Args:
            output_path: Path where HTML file should be written
            hide_inactive_default: Whether to hide inactive series by default
            expected_checks: List of expected check names
        """
        self.output_path = output_path
        self.hide_inactive_default = hide_inactive_default
        self.expected_checks = expected_checks or []

    def generate(self, series_scores: List[Dict], delegates: List[str]):
        """
        Generate the HTML UI

        Args:
            series_scores: List of series with scores and metadata
            delegates: List of possible delegates for filtering
        """
        # Prepare data for template
        template_data = {
            'series_list': series_scores,
            'delegates': delegates,
            'hide_inactive_default': self.hide_inactive_default,
            'expected_checks': self.expected_checks,
            'generated_at': datetime.now(timezone.utc).isoformat()
        }

        # Generate HTML
        html = self._render_template(template_data)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        # Write to file
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info("Generated UI at %s", self.output_path)

    def _render_template(self, data: Dict) -> str:
        """Render the HTML template"""
        template = Template(HTML_TEMPLATE)
        return template.render(**data)


# HTML template with embedded JavaScript
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suie - Patch Review Queue</title>
    <style>
        :root {
            /* Light mode colors */
            --bg-primary: #ffffff;
            --bg-secondary: #f6f8fa;
            --bg-hover: #f6f8fa;
            --text-primary: #24292e;
            --text-secondary: #586069;
            --text-link: #0366d6;
            --border-color: #e1e4e8;
            --border-input: #d1d5da;
            --shadow: rgba(0,0,0,0.1);
        }

        [data-theme="dark"] {
            /* Dark mode colors */
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-hover: #1c2128;
            --text-primary: #c9d1d9;
            --text-secondary: #8b949e;
            --text-link: #58a6ff;
            --border-color: #30363d;
            --border-input: #30363d;
            --shadow: rgba(0,0,0,0.3);
        }

        @media (prefers-color-scheme: dark) {
            :root:not([data-theme="light"]) {
                --bg-primary: #0d1117;
                --bg-secondary: #161b22;
                --bg-hover: #1c2128;
                --text-primary: #c9d1d9;
                --text-secondary: #8b949e;
                --text-link: #58a6ff;
                --border-color: #30363d;
                --border-input: #30363d;
                --shadow: rgba(0,0,0,0.3);
            }
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 14px;
            line-height: 1.5;
            color: var(--text-primary);
            background-color: var(--bg-secondary);
            padding: 20px;
            transition: background-color 0.3s ease, color 0.3s ease;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        header {
            background: var(--bg-primary);
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 6px;
            box-shadow: 0 1px 3px var(--shadow);
        }

        h1 {
            font-size: 24px;
            margin-bottom: 10px;
        }

        .controls {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
            margin-top: 15px;
        }

        .control-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        label {
            font-weight: 500;
        }

        select, input[type="checkbox"] {
            padding: 6px 10px;
            border: 1px solid var(--border-input);
            border-radius: 6px;
            background: var(--bg-primary);
            color: var(--text-primary);
        }

        input[type="checkbox"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }

        button {
            padding: 6px 12px;
            border: 1px solid var(--border-input);
            border-radius: 6px;
            background: var(--bg-primary);
            color: var(--text-primary);
            cursor: pointer;
            font-size: 13px;
            transition: opacity 0.2s;
        }

        button:hover {
            opacity: 0.8;
        }

        .series-list {
            background: var(--bg-primary);
            border-radius: 6px;
            box-shadow: 0 1px 3px var(--shadow);
        }

        .series-row {
            border-bottom: 1px solid var(--border-color);
            cursor: pointer;
            transition: background-color 0.2s;
        }

        .series-row:hover {
            background-color: var(--bg-hover);
        }

        .series-row.inactive {
            opacity: 0.6;
        }

        .series-row.hidden {
            display: none;
        }

        .series-header {
            padding: 12px 20px;
            display: grid;
            grid-template-columns: 80px 150px 1fr 100px 120px 200px 30px;
            gap: 15px;
            align-items: center;
        }

        .series-id {
            font-weight: 600;
            color: var(--text-link);
        }

        .series-author {
            color: var(--text-secondary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .series-title {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .series-age {
            color: var(--text-secondary);
            font-size: 13px;
        }

        .series-checks {
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }

        .check-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }

        .check-success {
            background-color: #dcffe4;
            color: #0e6027;
        }

        [data-theme="dark"] .check-success {
            background-color: #1a3d2a;
            color: #56d364;
        }

        .check-fail {
            background-color: #ffeef0;
            color: #d73a49;
        }

        [data-theme="dark"] .check-fail {
            background-color: #3d1319;
            color: #ff7b72;
        }

        .check-warning {
            background-color: #fff5e6;
            color: #e67700;
        }

        [data-theme="dark"] .check-warning {
            background-color: #3d2a1a;
            color: #ff9f40;
        }

        .check-missing {
            background-color: #f1f8ff;
            color: #0366d6;
        }

        [data-theme="dark"] .check-missing {
            background-color: #1a2d3d;
            color: #58a6ff;
        }

        .check-passing {
            background-color: #dcffe4;
            color: #0e6027;
            border: 1px solid #34d058;
        }

        [data-theme="dark"] .check-passing {
            background-color: #1a3d2a;
            color: #56d364;
            border: 1px solid #238636;
        }

        .check-badge.clickable {
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }

        .check-badge.clickable:hover {
            opacity: 0.8;
            text-decoration: underline;
        }

        .delegate-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background-color: #e1e4e8;
            color: #24292e;
        }

        .expand-icon {
            transition: transform 0.2s;
            font-size: 18px;
            color: #586069;
        }

        .series-row.expanded .expand-icon {
            transform: rotate(90deg);
        }

        .patches-container {
            display: none;
            background-color: var(--bg-hover);
            border-top: 1px solid var(--border-color);
        }

        .series-row.expanded .patches-container {
            display: block;
        }

        .patch-row {
            padding: 10px 20px 10px 60px;
            border-bottom: 1px solid var(--border-color);
            display: grid;
            grid-template-columns: 1fr 100px 200px 150px;
            gap: 15px;
            align-items: start;
        }

        .patch-row:last-child {
            border-bottom: none;
        }

        .patch-info {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .patch-name {
            font-size: 13px;
            font-weight: 500;
        }

        .failed-check-item {
            font-size: 12px;
            padding: 4px 8px;
            margin: 2px 0;
            background: #ffeef0;
            border-left: 3px solid #d73a49;
            border-radius: 3px;
            color: #d73a49;
        }

        .failed-check-item.warning {
            background: #fff5e6;
            border-left-color: #e67700;
            color: #e67700;
        }

        [data-theme="dark"] .failed-check-item {
            background: #3d1319;
            color: #ff7b72;
            border-left-color: #ff7b72;
        }

        [data-theme="dark"] .failed-check-item.warning {
            background: #3d2a1a;
            color: #ff9f40;
            border-left-color: #ff9f40;
        }

        .failed-check-item.clickable {
            cursor: pointer;
        }

        .failed-check-item.clickable:hover {
            opacity: 0.8;
            background: #ffd7dc;
        }

        [data-theme="dark"] .failed-check-item.clickable:hover {
            background: #4d1a21;
        }

        .failed-check-context {
            font-weight: 600;
        }

        .failed-check-description {
            color: var(--text-secondary);
            margin-left: 8px;
        }

        .patch-score {
            color: var(--text-secondary);
            font-size: 12px;
        }

        .score-comments {
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        .stats {
            margin-top: 10px;
            padding: 10px;
            background: var(--bg-hover);
            border-radius: 6px;
            font-size: 13px;
            color: var(--text-secondary);
        }

        @media (max-width: 1000px) {
            .series-header {
                grid-template-columns: 60px 120px 1fr 80px 100px 130px 30px;
                gap: 10px;
                font-size: 13px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Suie - Patch Review Queue</h1>
            <div class="stats">
                Generated at: <span id="generated-time"></span> |
                Total series: <span id="total-series"></span> |
                Visible: <span id="visible-series"></span>
            </div>
            <div class="controls">
                <div class="control-group">
                    <input type="checkbox" id="hide-inactive" {% if hide_inactive_default %}checked{% endif %}>
                    <label for="hide-inactive">Hide inactive series</label>
                </div>
                <div class="control-group">
                    <label for="delegate-filter">Delegate:</label>
                    <select id="delegate-filter">
                        <option value="">All</option>
                        {% for delegate in delegates %}
                        <option value="{{ delegate }}">{{ delegate }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="control-group">
                    <button id="theme-toggle" title="Toggle dark mode">🌓</button>
                </div>
            </div>
        </header>

        <div class="series-list" id="series-list">
            <!-- Series will be inserted here by JavaScript -->
        </div>
    </div>

    <script>
        // Data embedded from Python
        // All dates are in ISO 8601 format with UTC timezone (from Patchwork API)
        const seriesData = {{ series_list | tojson }};
        const generatedAt = "{{ generated_at }}";

        // Initialize UI
        document.addEventListener('DOMContentLoaded', () => {
            initializeTheme();
            initializeUI();
            loadFiltersFromURL();
            renderSeries();
            updateStats();

            // Event listeners
            document.getElementById('hide-inactive').addEventListener('change', renderSeries);
            document.getElementById('delegate-filter').addEventListener('change', onDelegateChange);
            document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
        });

        function initializeTheme() {
            // Load theme preference from localStorage or use system preference
            const savedTheme = localStorage.getItem('theme');
            const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

            if (savedTheme) {
                document.documentElement.setAttribute('data-theme', savedTheme);
            } else if (systemPrefersDark) {
                document.documentElement.setAttribute('data-theme', 'dark');
            }
        }

        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        }

        function initializeUI() {
            // Display generated time with relative time
            const genTime = new Date(generatedAt);
            document.getElementById('generated-time').textContent = formatRelativeTime(genTime);
            document.getElementById('total-series').textContent = seriesData.length;
        }

        function loadFiltersFromURL() {
            // Read URL parameters
            const urlParams = new URLSearchParams(window.location.search);
            const delegate = urlParams.get('delegate');

            // Set delegate filter if present in URL
            if (delegate) {
                const delegateSelect = document.getElementById('delegate-filter');
                // Check if this delegate exists in the options
                const option = Array.from(delegateSelect.options).find(opt => opt.value === delegate);
                if (option) {
                    delegateSelect.value = delegate;
                }
            }
        }

        function updateURL() {
            // Update URL with current filter state
            const delegateFilter = document.getElementById('delegate-filter').value;
            const url = new URL(window.location);

            if (delegateFilter) {
                url.searchParams.set('delegate', delegateFilter);
            } else {
                url.searchParams.delete('delegate');
            }

            // Update URL without page reload
            window.history.pushState({}, '', url);
        }

        function onDelegateChange() {
            updateURL();
            renderSeries();
        }

        function renderSeries() {
            const container = document.getElementById('series-list');
            const hideInactive = document.getElementById('hide-inactive').checked;
            const delegateFilter = document.getElementById('delegate-filter').value;

            container.innerHTML = '';
            let visibleCount = 0;

            seriesData.forEach(series => {
                // Apply filters
                if (hideInactive && series.is_inactive) {
                    return;
                }

                if (delegateFilter) {
                    const hasDelegateMatch = series.patches.some(patch =>
                        patch.delegate === delegateFilter
                    );
                    if (!hasDelegateMatch) {
                        return;
                    }
                }

                visibleCount++;
                container.appendChild(createSeriesRow(series));
            });

            document.getElementById('visible-series').textContent = visibleCount;
        }

        function createSeriesRow(series) {
            const row = document.createElement('div');
            row.className = 'series-row' + (series.is_inactive ? ' inactive' : '');

            const header = document.createElement('div');
            header.className = 'series-header';

            // Series ID
            const idEl = document.createElement('div');
            idEl.className = 'series-id';
            idEl.textContent = `#${series.id}`;
            header.appendChild(idEl);

            // Author
            const authorEl = document.createElement('div');
            authorEl.className = 'series-author';
            authorEl.textContent = series.author;
            authorEl.title = series.author;
            header.appendChild(authorEl);

            // Title
            const titleEl = document.createElement('div');
            titleEl.className = 'series-title';
            titleEl.textContent = series.title;
            titleEl.title = series.title;
            header.appendChild(titleEl);

            // Age
            const ageEl = document.createElement('div');
            ageEl.className = 'series-age';
            ageEl.textContent = formatRelativeTime(new Date(series.date));
            header.appendChild(ageEl);

            // Delegates
            const delegatesEl = document.createElement('div');
            delegatesEl.className = 'series-checks';
            if (series.delegates && series.delegates.length > 0) {
                series.delegates.forEach(delegate => {
                    const badge = document.createElement('span');
                    badge.className = 'delegate-badge';
                    badge.textContent = delegate;
                    badge.title = `Delegate: ${delegate}`;
                    delegatesEl.appendChild(badge);
                });
            }
            header.appendChild(delegatesEl);

            // Checks
            const checksEl = document.createElement('div');
            checksEl.className = 'series-checks';

            series.checks_summary.failed.forEach(check => {
                const badge = document.createElement('span');
                badge.className = 'check-badge check-fail';
                badge.textContent = check;
                badge.title = `Check failed: ${check}`;
                checksEl.appendChild(badge);
            });

            series.checks_summary.warning.forEach(check => {
                const badge = document.createElement('span');
                badge.className = 'check-badge check-warning';
                badge.textContent = check;
                badge.title = `Check warning: ${check}`;
                checksEl.appendChild(badge);
            });

            series.checks_summary.missing.forEach(check => {
                const badge = document.createElement('span');
                badge.className = 'check-badge check-missing';
                badge.textContent = check;
                badge.title = `Check missing: ${check}`;
                checksEl.appendChild(badge);
            });

            // Show passing checks summary
            if (series.checks_summary.passing > 0) {
                const passingBadge = document.createElement('span');
                passingBadge.className = 'check-badge check-passing';
                passingBadge.textContent = `✓ ${series.checks_summary.passing}`;
                passingBadge.title = `${series.checks_summary.passing} checks passing`;
                checksEl.appendChild(passingBadge);
            }

            header.appendChild(checksEl);

            // Expand icon
            const expandEl = document.createElement('div');
            expandEl.className = 'expand-icon';
            expandEl.textContent = '›';
            header.appendChild(expandEl);

            // Patches container
            const patchesContainer = document.createElement('div');
            patchesContainer.className = 'patches-container';

            series.patches.forEach(patch => {
                const patchRow = document.createElement('div');
                patchRow.className = 'patch-row';

                // Patch info column (name + failed checks)
                const patchInfoEl = document.createElement('div');
                patchInfoEl.className = 'patch-info';

                const nameEl = document.createElement('div');
                nameEl.className = 'patch-name';
                nameEl.textContent = patch.name;
                patchInfoEl.appendChild(nameEl);

                // Display failed checks as rows under patch name
                if (patch.checks_failed.length > 0) {
                    patch.checks_failed.forEach(check => {
                        // Handle both old string format and new object format
                        const isObject = typeof check === 'object';
                        const context = isObject ? check.context : check;
                        const description = isObject ? check.description : '';
                        const targetUrl = isObject ? check.target_url : '';
                        const state = isObject ? check.state : 'fail';

                        const failedCheckEl = document.createElement('div');
                        failedCheckEl.className = 'failed-check-item';
                        if (state === 'warning') {
                            failedCheckEl.classList.add('warning');
                        }

                        const contextSpan = document.createElement('span');
                        contextSpan.className = 'failed-check-context';
                        contextSpan.textContent = context;
                        failedCheckEl.appendChild(contextSpan);

                        if (description) {
                            const descSpan = document.createElement('span');
                            descSpan.className = 'failed-check-description';
                            descSpan.textContent = description;
                            failedCheckEl.appendChild(descSpan);
                        }

                        // Make clickable if URL is available
                        if (targetUrl) {
                            failedCheckEl.classList.add('clickable');
                            failedCheckEl.title = 'Click to view details';
                            failedCheckEl.addEventListener('click', (e) => {
                                e.stopPropagation(); // Don't trigger row expansion
                                window.open(targetUrl, '_blank');
                            });
                        }

                        patchInfoEl.appendChild(failedCheckEl);
                    });
                }

                patchRow.appendChild(patchInfoEl);

                // Delegate badge
                const delegateEl = document.createElement('div');
                if (patch.delegate) {
                    const delegateBadge = document.createElement('span');
                    delegateBadge.className = 'delegate-badge';
                    delegateBadge.textContent = patch.delegate;
                    delegateBadge.title = `Delegate: ${patch.delegate}`;
                    delegateEl.appendChild(delegateBadge);
                }
                patchRow.appendChild(delegateEl);

                // Checks column (only missing and passing summary)
                const checksEl = document.createElement('div');
                checksEl.className = 'series-checks';

                if (patch.checks_missing.length > 0) {
                    patch.checks_missing.forEach(check => {
                        const badge = document.createElement('span');
                        badge.className = 'check-badge check-missing';
                        badge.textContent = check;
                        checksEl.appendChild(badge);
                    });
                }

                // Show passing checks summary for patch
                if (patch.checks_passing > 0) {
                    const passingBadge = document.createElement('span');
                    passingBadge.className = 'check-badge check-passing';
                    passingBadge.textContent = `✓ ${patch.checks_passing}`;
                    passingBadge.title = `${patch.checks_passing} checks passing`;
                    checksEl.appendChild(passingBadge);
                }

                patchRow.appendChild(checksEl);

                const scoreEl = document.createElement('div');
                scoreEl.className = 'patch-score';
                scoreEl.textContent = `Score: ${patch.score.toFixed(2)}`;

                if (patch.score_comments.length > 0) {
                    const commentsEl = document.createElement('div');
                    commentsEl.className = 'score-comments';
                    commentsEl.textContent = patch.score_comments.join('; ');
                    scoreEl.appendChild(commentsEl);
                }

                patchRow.appendChild(scoreEl);

                patchesContainer.appendChild(patchRow);
            });

            // Click to expand
            header.addEventListener('click', () => {
                row.classList.toggle('expanded');
            });

            row.appendChild(header);
            row.appendChild(patchesContainer);

            return row;
        }

        function formatRelativeTime(date) {
            // Date objects store time as milliseconds since epoch (timezone-agnostic)
            // So this comparison works correctly regardless of user's local timezone
            const now = new Date();
            const diff = now - date;
            const seconds = Math.floor(diff / 1000);
            const minutes = Math.floor(seconds / 60);
            const hours = Math.floor(minutes / 60);
            const days = Math.floor(hours / 24);

            if (days > 0) {
                return `${days}d ago`;
            } else if (hours > 0) {
                return `${hours}h ago`;
            } else if (minutes > 0) {
                return `${minutes}m ago`;
            } else {
                return 'just now';
            }
        }

        function updateStats() {
            // Update stats periodically (every minute)
            setInterval(() => {
                const genTime = new Date(generatedAt);
                document.getElementById('generated-time').textContent = formatRelativeTime(genTime);
            }, 60000);
        }
    </script>
</body>
</html>
"""
