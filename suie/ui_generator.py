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
                 expected_checks: Optional[List[str]] = None,
                 tracking_scripts: Optional[List[str]] = None):
        """
        Initialize the UI generator

        Args:
            output_path: Path where HTML file should be written
            hide_inactive_default: Whether to hide inactive series by default
            expected_checks: List of expected check names
            tracking_scripts: List of tracking script HTML strings to insert in <head>
        """
        self.output_path = output_path
        self.hide_inactive_default = hide_inactive_default
        self.expected_checks = expected_checks or []
        self.tracking_scripts = tracking_scripts or []

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
        data['tracking_scripts'] = self.tracking_scripts
        return template.render(**data)


# HTML template with embedded JavaScript
HTML_TEMPLATE = """<!DOCTYPE html>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suie - Patch Review Queue</title>
    <link rel="icon" type="image/png" href="suie.png">
    {% for script in tracking_scripts %}
    {{ script | safe }}
    {% endfor %}
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
            max-width: 1800px;
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
            display: flex;
            align-items: center;
            gap: 10px;
        }

        h1 img {
            height: 1.2em;
            width: auto;
            vertical-align: middle;
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

        .series-list-header {
            padding: 12px 20px;
            display: grid;
            grid-template-columns: 120px 150px 1fr 100px 80px 120px 180px 200px 30px;
            gap: 15px;
            align-items: center;
            background-color: var(--bg-secondary);
            border-bottom: 2px solid var(--border-color);
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            color: var(--text-secondary);
            border-radius: 6px 6px 0 0;
        }

        .sortable-header {
            cursor: pointer;
            user-select: none;
            position: relative;
            padding-right: 16px;
        }

        .sortable-header:hover {
            color: var(--text-primary);
        }

        .sort-indicator {
            position: absolute;
            right: 0;
            font-size: 10px;
            opacity: 0.6;
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
            grid-template-columns: 120px 150px 1fr 100px 80px 120px 180px 200px 30px;
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

        .series-score {
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 500;
        }

        .series-state {
            font-size: 11px;
        }

        .state-badge {
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            white-space: nowrap;
        }

        .state-new {
            background-color: #ddf4ff;
            color: #0969da;
        }

        [data-theme="dark"] .state-new {
            background-color: #1a2d3d;
            color: #58a6ff;
        }

        .state-under-review {
            background-color: #fff5e6;
            color: #e67700;
        }

        [data-theme="dark"] .state-under-review {
            background-color: #3d2a1a;
            color: #ff9f40;
        }

        .state-accepted {
            background-color: #dcffe4;
            color: #0e6027;
        }

        [data-theme="dark"] .state-accepted {
            background-color: #1a3d2a;
            color: #56d364;
        }

        .state-rejected {
            background-color: #ffeef0;
            color: #d73a49;
        }

        [data-theme="dark"] .state-rejected {
            background-color: #3d1319;
            color: #ff7b72;
        }

        .state-superseded,
        .state-deferred,
        .state-not-applicable,
        .state-archived {
            background-color: #f6f8fa;
            color: #586069;
        }

        [data-theme="dark"] .state-superseded,
        [data-theme="dark"] .state-deferred,
        [data-theme="dark"] .state-not-applicable,
        [data-theme="dark"] .state-archived {
            background-color: #30363d;
            color: #8b949e;
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

        [data-theme="dark"] .delegate-badge {
            background-color: #30363d;
            color: #c9d1d9;
        }

        .reviewer-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background-color: #ddf4ff;
            color: #0969da;
        }

        [data-theme="dark"] .reviewer-badge {
            background-color: #1a2d3d;
            color: #58a6ff;
        }

        .reviewer-badge-original {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background-color: #f0f0f0;
            color: #606060;
            border: 1px solid #b0b0b0;
        }

        [data-theme="dark"] .reviewer-badge-original {
            background-color: #2a2a2a;
            color: #a0a0a0;
            border-color: #505050;
        }

        .reviewer-badge-comment {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            background-color: #ddf4ff;
            color: #0969da;
            border: 2px solid #54aeff;
        }

        [data-theme="dark"] .reviewer-badge-comment {
            background-color: #1a2d3d;
            color: #58a6ff;
            border-color: #58a6ff;
        }

        .reviewer-badge-full {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            background-color: #f0f0f0;
            color: #1b6635;
            border: 2px solid #34d058;
        }

        [data-theme="dark"] .reviewer-badge-full {
            background-color: #2a2a2a;
            color: #6bdb86;
            border-color: #3a7a4d;
        }

        .reviewer-badge-partial {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background-color: #f0f0f0;
            color: #606060;
            border: 1px solid #b0b0b0;
        }

        [data-theme="dark"] .reviewer-badge-partial {
            background-color: #2a2a2a;
            color: #a0a0a0;
            border-color: #505050;
        }

        .commenter-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background-color: #fff9e6;
            color: #b58600;
            border: 1px solid #d4a800;
        }

        [data-theme="dark"] .commenter-badge {
            background-color: #3d3520;
            color: #f0c040;
            border-color: #8a7000;
        }

        .patch-count-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background-color: #e1e4e8;
            color: #24292e;
            margin-right: 8px;
            min-width: 30px;
            display: inline-block;
            text-align: right;
        }

        [data-theme="dark"] .patch-count-badge {
            background-color: #30363d;
            color: #c9d1d9;
        }

        .tree-badge {
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            background-color: #e1e4e8;
            color: #24292e;
            margin-right: 8px;
        }

        [data-theme="dark"] .tree-badge {
            background-color: #30363d;
            color: #c9d1d9;
        }

        .company-badge {
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 500;
            background-color: #e8f4f8;
            color: #0969da;
            border: 1px solid #b8dae8;
            display: inline-block;
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        [data-theme="dark"] .company-badge {
            background-color: #1a2d3d;
            color: #58a6ff;
            border-color: #2d4a5e;
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
            grid-template-columns: 1fr 100px 180px 200px 150px;
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
                grid-template-columns: 60px 120px 1fr 80px 70px 90px 100px 130px 30px;
                gap: 10px;
                font-size: 13px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1><img src="suie.png" alt="Suie">Suie - Patch Review Queue</h1>
            <div class="stats">
                Generated at: <span id="generated-time"></span> |
                Series: <span id="visible-series"></span> / <span id="total-series"></span> |
                Patches: <span id="visible-patches"></span> / <span id="total-patches"></span>
            </div>
            <div class="controls">
                <div class="control-group">
                    <input type="checkbox" id="hide-inactive" {% if hide_inactive_default %}checked{% endif %}>
                    <label for="hide-inactive">Hide inactive series</label>
                </div>
                <div class="control-group">
                    <label for="min-age-filter">Min age:</label>
                    <select id="min-age-filter">
                        <option value="0">All</option>
                        <option value="3">3h+</option>
                        <option value="6">6h+</option>
                        <option value="9">9h+</option>
                        <option value="12">12h+</option>
                        <option value="15">15h+</option>
                        <option value="18">18h+</option>
                        <option value="21">21h+</option>
                        <option value="24">1d+</option>
                        <option value="48">2d+</option>
                        <option value="72">3d+</option>
                    </select>
                </div>
                <div class="control-group">
                    <label for="delegate-filter">Delegate:</label>
                    <select id="delegate-filter">
                        <option value="">All</option>
                        <option value="__none__">Unassigned</option>
                        {% for delegate in delegates %}
                        <option value="{{ delegate }}">{{ delegate }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="control-group">
                    <button id="fold-all" title="Collapse all expanded series">Fold All</button>
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

        // Sorting state
        let currentSort = {
            column: 'score',  // Default sort by score
            direction: 'asc'  // ascending (lower score = higher priority)
        };

        // Initialize UI
        document.addEventListener('DOMContentLoaded', () => {
            initializeTheme();
            initializeUI();
            loadFiltersFromURL();
            renderSeries();
            updateStats();

            // Event listeners
            document.getElementById('hide-inactive').addEventListener('change', renderSeries);
            document.getElementById('min-age-filter').addEventListener('change', renderSeries);
            document.getElementById('delegate-filter').addEventListener('change', onDelegateChange);
            document.getElementById('fold-all').addEventListener('click', foldAllSeries);
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

            // Count total patches
            const totalPatches = seriesData.reduce((sum, series) => sum + series.patches.length, 0);
            document.getElementById('total-patches').textContent = totalPatches;
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
            const minAgeFilter = parseInt(document.getElementById('min-age-filter').value);
            const delegateFilter = document.getElementById('delegate-filter').value;

            container.innerHTML = '';

            // Add header row with sortable columns
            const headerRow = document.createElement('div');
            headerRow.className = 'series-list-header';

            const headers = [
                {text: 'ID', sortable: true, key: 'id'},
                {text: 'Author', sortable: false},
                {text: 'Title', sortable: false},
                {text: 'Age', sortable: true, key: 'age'},
                {text: 'Score', sortable: true, key: 'score'},
                {text: 'State', sortable: false},
                {text: 'Reviews', sortable: true, key: 'reviews'},
                {text: 'Checks', sortable: true, key: 'checks'},
                {text: '', sortable: false}
            ];

            headers.forEach(header => {
                const headerCell = document.createElement('div');
                if (header.sortable) {
                    headerCell.className = 'sortable-header';
                    headerCell.textContent = header.text;

                    // Add sort indicator if this column is currently sorted
                    if (currentSort.column === header.key) {
                        const indicator = document.createElement('span');
                        indicator.className = 'sort-indicator';
                        indicator.textContent = currentSort.direction === 'asc' ? '▲' : '▼';
                        headerCell.appendChild(indicator);
                    }

                    headerCell.addEventListener('click', () => {
                        handleSort(header.key);
                    });
                } else {
                    headerCell.textContent = header.text;
                }
                headerRow.appendChild(headerCell);
            });

            container.appendChild(headerRow);

            // Filter and sort data
            let filteredSeries = seriesData.filter(series => {
                // Apply inactive filter
                if (hideInactive && series.is_inactive) {
                    return false;
                }

                // Apply minimum age filter (based on weekday hours)
                if (minAgeFilter > 0 && series.age_weekday_hours < minAgeFilter) {
                    return false;
                }

                // Apply delegate filter
                if (delegateFilter) {
                    if (delegateFilter === '__none__') {
                        const hasAnyDelegate = series.patches.some(patch => patch.delegate);
                        if (hasAnyDelegate) {
                            return false;
                        }
                    } else {
                        const hasDelegateMatch = series.patches.some(patch =>
                            patch.delegate === delegateFilter
                        );
                        if (!hasDelegateMatch) {
                            return false;
                        }
                    }
                }

                return true;
            });

            // Apply sorting if not default
            if (currentSort.column !== null) {
                filteredSeries = sortSeries(filteredSeries, currentSort.column, currentSort.direction);
            }

            let visibleCount = filteredSeries.length;
            let visiblePatchCount = filteredSeries.reduce((sum, s) => sum + s.patches.length, 0);

            filteredSeries.forEach(series => {
                container.appendChild(createSeriesRow(series));
            });

            document.getElementById('visible-series').textContent = visibleCount;
            document.getElementById('visible-patches').textContent = visiblePatchCount;
        }

        function handleSort(column) {
            // Cycle through: default direction -> opposite direction -> reset to score
            if (currentSort.column === column) {
                // Already sorting by this column
                const defaultDirection = (column === 'score' || column === 'checks') ? 'asc' : 'desc';

                if (currentSort.direction === defaultDirection) {
                    // Second click: toggle to opposite of default direction
                    currentSort.direction = defaultDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    // Third click: currently at opposite of default, reset to score
                    currentSort.column = 'score';
                    currentSort.direction = 'asc';
                }
            } else {
                // First click on this column - set default direction
                currentSort.column = column;
                if (column === 'score' || column === 'checks') {
                    currentSort.direction = 'asc';  // Lower is better
                } else {
                    currentSort.direction = 'desc';  // Higher/newer is better
                }
            }

            renderSeries();
        }

        function calculateReviewScore(series) {
            // Full review = +5, partial review = +1, open comments = -1
            let score = 0;
            score += (series.reviewers_full || []).length * 5;
            score += (series.reviewers_partial || []).length * 1;
            score -= (series.commenters || []).length * 1;
            return score;
        }

        function calculateCheckScore(series) {
            // Fails = +5, warnings = +1, missing checks = +10
            let score = 0;
            score += (series.checks_summary.failed || []).length * 5;
            score += (series.checks_summary.warning || []).length * 1;
            score += (series.checks_summary.missing || []).length * 10;
            return score;
        }

        function sortSeries(series, column, direction) {
            const sorted = [...series];

            sorted.sort((a, b) => {
                let aVal, bVal;

                switch (column) {
                    case 'id':
                        aVal = a.id;
                        bVal = b.id;
                        break;
                    case 'age':
                        aVal = a.age_total_hours;
                        bVal = b.age_total_hours;
                        break;
                    case 'score':
                        aVal = a.score;
                        bVal = b.score;
                        break;
                    case 'reviews':
                        aVal = calculateReviewScore(a);
                        bVal = calculateReviewScore(b);
                        break;
                    case 'checks':
                        aVal = calculateCheckScore(a);
                        bVal = calculateCheckScore(b);
                        break;
                    default:
                        return 0;
                }

                // Handle numeric comparison
                if (direction === 'asc') {
                    return aVal - bVal;
                } else {
                    return bVal - aVal;
                }
            });

            return sorted;
        }

        function createSeriesRow(series) {
            const row = document.createElement('div');
            row.className = 'series-row' + (series.is_inactive ? ' inactive' : '');

            const header = document.createElement('div');
            header.className = 'series-header';

            // Series ID + Links (column with ID on top, links below)
            const idLinksEl = document.createElement('div');
            idLinksEl.style.display = 'flex';
            idLinksEl.style.flexDirection = 'column';
            idLinksEl.style.gap = '4px';

            const idEl = document.createElement('div');
            idEl.className = 'series-id';
            idEl.textContent = `#${series.id}`;
            idLinksEl.appendChild(idEl);

            // Links container
            const linksEl = document.createElement('div');
            linksEl.style.display = 'flex';
            linksEl.style.gap = '8px';
            linksEl.style.fontSize = '11px';

            if (series.lore_url) {
                const loreLink = document.createElement('a');
                loreLink.href = series.lore_url;
                loreLink.textContent = 'Lore';
                loreLink.target = '_blank';
                loreLink.style.color = 'var(--text-link)';
                loreLink.style.textDecoration = 'none';
                loreLink.style.fontWeight = '500';
                loreLink.addEventListener('click', (e) => e.stopPropagation());
                loreLink.addEventListener('mouseover', () => loreLink.style.textDecoration = 'underline');
                loreLink.addEventListener('mouseout', () => loreLink.style.textDecoration = 'none');
                linksEl.appendChild(loreLink);
            }

            if (series.patchwork_url) {
                const pwLink = document.createElement('a');
                pwLink.href = series.patchwork_url;
                pwLink.textContent = 'PW';
                pwLink.target = '_blank';
                pwLink.style.color = 'var(--text-link)';
                pwLink.style.textDecoration = 'none';
                pwLink.style.fontWeight = '500';
                pwLink.addEventListener('click', (e) => e.stopPropagation());
                pwLink.addEventListener('mouseover', () => pwLink.style.textDecoration = 'underline');
                pwLink.addEventListener('mouseout', () => pwLink.style.textDecoration = 'none');
                linksEl.appendChild(pwLink);
            }

            idLinksEl.appendChild(linksEl);
            header.appendChild(idLinksEl);

            // Author (with company badge below)
            const authorEl = document.createElement('div');
            authorEl.className = 'series-author';
            authorEl.style.display = 'flex';
            authorEl.style.flexDirection = 'column';
            authorEl.style.gap = '4px';

            const authorNameEl = document.createElement('div');
            authorNameEl.textContent = series.author;
            authorNameEl.title = series.author;
            authorNameEl.style.overflow = 'hidden';
            authorNameEl.style.textOverflow = 'ellipsis';
            authorNameEl.style.whiteSpace = 'nowrap';
            authorEl.appendChild(authorNameEl);

            if (series.author_company) {
                const companyBadge = document.createElement('span');
                companyBadge.className = 'company-badge';
                companyBadge.textContent = series.author_company;
                companyBadge.title = `Company: ${series.author_company}`;
                authorEl.appendChild(companyBadge);
            }

            header.appendChild(authorEl);

            // Title container with title left-aligned and badges right-aligned
            const titleContainerEl = document.createElement('div');
            titleContainerEl.style.display = 'flex';
            titleContainerEl.style.justifyContent = 'space-between';
            titleContainerEl.style.alignItems = 'center';
            titleContainerEl.style.gap = '10px';
            titleContainerEl.style.minWidth = '0';  // Allow text truncation

            // Extract tree designation from title (first word in square brackets)
            let treeDesignation = null;
            let cleanTitle = series.title;
            const treeMatch = series.title.match(/^\[([^\]]+)\]\s*/);
            if (treeMatch) {
                treeDesignation = treeMatch[1];
                cleanTitle = series.title.substring(treeMatch[0].length);
            }

            // Title (left side)
            const titleEl = document.createElement('div');
            titleEl.className = 'series-title';
            titleEl.textContent = cleanTitle;
            titleEl.title = series.title;  // Use original title with tree for tooltip
            titleEl.style.overflow = 'hidden';
            titleEl.style.textOverflow = 'ellipsis';
            titleEl.style.whiteSpace = 'nowrap';
            titleEl.style.flex = '1';
            titleEl.style.minWidth = '0';
            titleContainerEl.appendChild(titleEl);

            // Badges container (right side)
            const badgesContainer = document.createElement('div');
            badgesContainer.style.display = 'flex';
            badgesContainer.style.alignItems = 'center';
            badgesContainer.style.gap = '0';  // No gap since badges have their own margin-right
            badgesContainer.style.flexShrink = '0';  // Don't shrink badges

            // Add tree designation badge if present
            if (treeDesignation) {
                const treeBadge = document.createElement('span');
                treeBadge.className = 'tree-badge';
                treeBadge.textContent = treeDesignation;
                treeBadge.title = `Tree: ${treeDesignation}`;
                badgesContainer.appendChild(treeBadge);
            }

            // Add version badge if version > 1
            if (series.version && series.version > 1) {
                const versionBadge = document.createElement('span');
                versionBadge.className = 'tree-badge';
                versionBadge.textContent = `v${series.version}`;
                versionBadge.title = `Version ${series.version}`;
                badgesContainer.appendChild(versionBadge);
            }

            // Add patch count badge only if more than 1 patch
            if (series.patches.length > 1) {
                const patchCountBadge = document.createElement('span');
                patchCountBadge.className = 'patch-count-badge';
                patchCountBadge.textContent = series.patches.length;
                patchCountBadge.title = `${series.patches.length} patches in this series`;
                badgesContainer.appendChild(patchCountBadge);
            }

            titleContainerEl.appendChild(badgesContainer);

            header.appendChild(titleContainerEl);

            // Age (with weekend time on separate line)
            const ageEl = document.createElement('div');
            ageEl.className = 'series-age';
            ageEl.style.display = 'flex';
            ageEl.style.flexDirection = 'column';
            ageEl.style.gap = '2px';

            const ageFormat = formatAgeWithWeekend(series.age_weekday_hours, series.age_weekend_hours);
            const mainAgeEl = document.createElement('div');
            mainAgeEl.textContent = ageFormat.main;
            ageEl.appendChild(mainAgeEl);

            if (ageFormat.weekend) {
                const weekendAgeEl = document.createElement('div');
                weekendAgeEl.textContent = ageFormat.weekend;
                weekendAgeEl.style.fontSize = '11px';
                weekendAgeEl.style.color = 'var(--text-secondary)';
                weekendAgeEl.style.opacity = '0.7';
                ageEl.appendChild(weekendAgeEl);
            }

            header.appendChild(ageEl);

            // Score
            const scoreEl = document.createElement('div');
            scoreEl.className = 'series-score';
            scoreEl.textContent = formatScoreAsTime(series.score);
            scoreEl.title = `Score: ${series.score.toFixed(2)} hours`;
            header.appendChild(scoreEl);

            // State + Delegates (combined column with state on top, delegates below)
            const stateDelegatesEl = document.createElement('div');
            stateDelegatesEl.style.display = 'flex';
            stateDelegatesEl.style.flexDirection = 'column';
            stateDelegatesEl.style.gap = '4px';

            // State
            const stateContainer = document.createElement('div');
            stateContainer.className = 'series-state';
            if (series.state) {
                const stateBadge = document.createElement('span');
                stateBadge.className = 'state-badge';

                // Add state-specific class
                const stateClass = 'state-' + series.state.toLowerCase().replace(/[^a-z0-9]+/g, '-');
                stateBadge.classList.add(stateClass);

                stateBadge.textContent = series.state;
                stateBadge.title = `State: ${series.state}`;
                stateContainer.appendChild(stateBadge);
            }
            stateDelegatesEl.appendChild(stateContainer);

            // Delegates
            const delegatesContainer = document.createElement('div');
            delegatesContainer.className = 'series-checks';
            if (series.delegates && series.delegates.length > 0) {
                series.delegates.forEach(delegate => {
                    const badge = document.createElement('span');
                    badge.className = 'delegate-badge';
                    badge.textContent = delegate;
                    badge.title = `Delegate: ${delegate}`;
                    delegatesContainer.appendChild(badge);
                });
            }
            stateDelegatesEl.appendChild(delegatesContainer);

            header.appendChild(stateDelegatesEl);

            // External Reviewers and Commenters
            const reviewersEl = document.createElement('div');
            reviewersEl.className = 'series-checks';
            // Show reviewers who reviewed ALL patches first
            if (series.reviewers_full && series.reviewers_full.length > 0) {
                series.reviewers_full.forEach(reviewer => {
                    const badge = document.createElement('span');
                    badge.className = 'reviewer-badge-full';
                    badge.textContent = reviewer;
                    badge.title = `Reviewed all patches: ${reviewer}`;
                    reviewersEl.appendChild(badge);
                });
            }
            // Then show reviewers who reviewed SOME patches
            if (series.reviewers_partial && series.reviewers_partial.length > 0) {
                series.reviewers_partial.forEach(reviewer => {
                    const badge = document.createElement('span');
                    badge.className = 'reviewer-badge-partial';
                    badge.textContent = reviewer;
                    badge.title = `Reviewed some patches: ${reviewer}`;
                    reviewersEl.appendChild(badge);
                });
            }
            // Finally show commenters (people who commented without review tags)
            if (series.commenters && series.commenters.length > 0) {
                series.commenters.forEach(commenter => {
                    const badge = document.createElement('span');
                    badge.className = 'commenter-badge';
                    badge.textContent = commenter;
                    badge.title = `${commenter} (commented without review tag on at least one patch)`;
                    reviewersEl.appendChild(badge);
                });
            }
            header.appendChild(reviewersEl);

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

                // Reviewers and Commenters
                const reviewersEl = document.createElement('div');
                reviewersEl.className = 'series-checks';

                // Show reviewers with tags first
                if (patch.reviewers && patch.reviewers.length > 0) {
                    patch.reviewers.forEach(reviewer => {
                        // Handle both old string format and new object format
                        const isObject = typeof reviewer === 'object';
                        const name = isObject ? reviewer.name : reviewer;
                        const source = isObject ? reviewer.source : 'original';

                        const badge = document.createElement('span');
                        // Apply different CSS class based on source
                        if (source === 'original') {
                            badge.className = 'reviewer-badge-original';
                            badge.title = `${name} (reviewed in original patch)`;
                        } else {
                            badge.className = 'reviewer-badge-comment';
                            badge.title = `${name} (reviewed in comments)`;
                        }
                        badge.textContent = name;
                        reviewersEl.appendChild(badge);
                    });
                }

                // Show commenters (people who commented without review tags)
                if (patch.commenters && patch.commenters.length > 0) {
                    patch.commenters.forEach(commenter => {
                        const badge = document.createElement('span');
                        badge.className = 'commenter-badge';
                        badge.textContent = commenter;
                        badge.title = `${commenter} (commented without review tag)`;
                        reviewersEl.appendChild(badge);
                    });
                }

                patchRow.appendChild(reviewersEl);

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
                // Show both days and hours, e.g., "2d 5h"
                const remainingHours = hours % 24;
                if (remainingHours > 0) {
                    return `${days}d ${remainingHours}h`;
                }
                return `${days}d`;
            } else if (hours > 0) {
                return `${hours}h`;
            } else if (minutes > 0) {
                return `${minutes}m`;
            } else {
                return 'now';
            }
        }

        function formatScoreAsTime(score) {
            // Treat score as hours
            // Positive score: e.g., 25 hours = "1d 1h"
            // Negative score: e.g., -7 hours = "-7h"

            const isNegative = score < 0;
            const absScore = Math.abs(score);
            const hours = Math.floor(absScore);
            const days = Math.floor(hours / 24);
            const remainingHours = hours % 24;

            let result = '';
            if (isNegative) {
                result = '-';
            }

            if (days > 0) {
                result += `${days}d`;
                if (remainingHours > 0) {
                    result += ` ${remainingHours}h`;
                }
            } else if (hours > 0) {
                result += `${hours}h`;
            } else {
                result += '0h';
            }

            return result;
        }

        function formatTimeAsHours(hours) {
            // Format hours as "Xd Yh" or "Xh" or "Xm"
            const h = Math.floor(hours);
            const days = Math.floor(h / 24);
            const remainingHours = h % 24;
            const minutes = Math.floor((hours - h) * 60);

            if (days > 0) {
                if (remainingHours > 0) {
                    return `${days}d ${remainingHours}h`;
                }
                return `${days}d`;
            } else if (h > 0) {
                return `${h}h`;
            } else if (minutes > 0) {
                return `${minutes}m`;
            } else {
                return 'now';
            }
        }

        function formatAgeWithWeekend(weekdayHours, weekendHours) {
            // Format age as "23h (+2d)" where first part is weekday time
            // and part in brackets is weekend time
            // Returns {main: "23h", weekend: "(+2d)"} or {main: "23h", weekend: ""}

            const mainTime = formatTimeAsHours(weekdayHours);

            if (weekendHours > 0.1) {  // Only show weekend if significant (> ~6 minutes)
                const weekendTime = formatTimeAsHours(weekendHours);
                return {
                    main: mainTime,
                    weekend: `(+${weekendTime})`
                };
            } else {
                return {
                    main: mainTime,
                    weekend: ''
                };
            }
        }

        function foldAllSeries() {
            // Collapse all expanded series
            const expandedRows = document.querySelectorAll('.series-row.expanded');
            expandedRows.forEach(row => {
                row.classList.remove('expanded');
            });
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
