"""Standalone page with outstanding patch counts per tree and company"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
from jinja2 import Template

from .ui_generator import THEME_CSS


logger = logging.getLogger(__name__)


class StatsGenerator:
    """Generates a static page breaking the queue down by tree and company"""

    def __init__(self, output_path: str,
                 tracking_scripts: Optional[List[str]] = None,
                 lookback_days: Optional[int] = None):
        """
        Initialize the stats generator

        Args:
            output_path: Path where the HTML file should be written
            tracking_scripts: List of tracking script HTML strings to insert in <head>
            lookback_days: How far back the mirror reaches, shown on the page so
                the counts are not read as an all time backlog
        """
        self.output_path = output_path
        self.tracking_scripts = tracking_scripts or []
        self.lookback_days = lookback_days

    def generate(self, series_scores: List[Dict]):
        """
        Generate the stats page

        Args:
            series_scores: List of series with scores and metadata, the same
                list the review queue is built from
        """
        tree_designations = sorted({series["tree_designation"]
                                    for series in series_scores
                                    if series.get("tree_designation")})

        template_data = {
            "series_list": series_scores,
            "tree_designations": tree_designations,
            "lookback_days": self.lookback_days,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tracking_scripts": self.tracking_scripts,
            "theme_css": THEME_CSS,
        }

        html = Template(STATS_TEMPLATE).render(**template_data)

        directory = os.path.dirname(self.output_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("Generated stats at %s", self.output_path)


# Nothing links here from the review queue, the page is opened directly when
# the shape of the backlog is the question rather than what to review next
STATS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Suie - Outstanding Patches</title>
    <link rel="icon" type="image/png" href="suie.png">
    {% for script in tracking_scripts %}
    {{ script | safe }}
    {% endfor %}
    <style>
{{ theme_css | safe }}

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
            max-width: 1100px;
            margin: 0 auto;
        }

        header {
            background: var(--bg-primary);
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 6px;
            box-shadow: 0 1px 3px var(--shadow);
        }

        .header-top {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
        }

        h1 {
            font-size: 24px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        h1 img {
            height: 1.2em;
            width: auto;
            vertical-align: middle;
        }

        .stats {
            padding: 6px 12px;
            background: var(--bg-hover);
            border-radius: 6px;
            font-size: 13px;
            color: var(--text-secondary);
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

        .chart {
            background: var(--bg-primary);
            padding: 20px;
            border-radius: 6px;
            box-shadow: 0 1px 3px var(--shadow);
        }

        /* Name, bar, count. Every bar is drawn against the same scale, the
         * busiest submitter, so the rows can be read against each other */
        .bar-row {
            display: grid;
            grid-template-columns: 200px 1fr 50px;
            gap: 12px;
            align-items: center;
            padding: 3px 0;
        }

        .bar-name {
            font-size: 13px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* Submitters with no corpmap entry are people rather than companies,
         * so they get their name in italics and a hollow bar */
        .bar-row.individual .bar-name {
            font-style: italic;
            color: var(--text-secondary);
        }

        .bar-track {
            min-width: 0;
        }

        .bar {
            height: 16px;
            border-radius: 3px;
            min-width: 2px;
            background-color: var(--text-link);
        }

        .bar-row.individual .bar {
            background-color: transparent;
            box-shadow: inset 0 0 0 1px var(--text-link);
        }

        .bar-count {
            font-size: 13px;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }

        .chart-total {
            margin-top: 14px;
            padding-top: 10px;
            border-top: 1px solid var(--border-color);
            font-size: 13px;
            color: var(--text-secondary);
            text-align: right;
        }

        .chart-empty {
            font-size: 13px;
            color: var(--text-secondary);
        }

        @media (max-width: 700px) {
            .bar-row {
                grid-template-columns: 120px 1fr 40px;
                gap: 8px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-top">
                <h1><img src="suie.png" alt="Suie">Suie - Outstanding Patches</h1>
                <div class="stats">
                    Generated: <span id="generated-time"></span> ago{% if lookback_days %} |
                    Last <span id="lookback">{{ lookback_days }}</span> days{% endif %}
                </div>
            </div>
            <div class="controls">
                <div class="control-group">
                    <label for="tree-filter">Tree:</label>
                    <select id="tree-filter"></select>
                </div>
                <div class="control-group">
                    <input type="checkbox" id="include-no-tree">
                    <label for="include-no-tree">Include no tree</label>
                </div>
                <div class="control-group">
                    <input type="checkbox" id="split-unknown" checked>
                    <label for="split-unknown">Split unknown</label>
                </div>
                <div class="control-group">
                    <input type="checkbox" id="include-inactive">
                    <label for="include-inactive">Inactive</label>
                </div>
                <div class="control-group">
                    <button id="theme-toggle" title="Toggle dark mode">🌓</button>
                </div>
            </div>
        </header>

        <div class="chart">
            <div id="chart-body"></div>
            <div class="chart-total" id="chart-total"></div>
        </div>
    </div>

    <script>
        // Data embedded from Python, the same series the review queue lists
        const seriesData = {{ series_list | tojson }};
        const treeDesignations = {{ tree_designations | tojson }};
        const generatedAt = "{{ generated_at }}";

        // Which tree, and which of the three switches, is a mode people stay
        // in rather than a per visit choice, so keep it across reloads
        const STORAGE_TREE = 'suie.stats.tree';
        const STORAGE_NO_TREE = 'suie.stats.noTree';
        const STORAGE_SPLIT = 'suie.stats.splitUnknown';
        const STORAGE_INACTIVE = 'suie.stats.inactive';

        const UNKNOWN = 'Unknown';

        document.addEventListener('DOMContentLoaded', () => {
            initializeTheme();
            initializeUI();
            loadSettings();
            render();
            updateStats();

            document.getElementById('tree-filter').addEventListener('change', onTreeChange);
            document.getElementById('include-no-tree').addEventListener('change', onSettingChange);
            document.getElementById('split-unknown').addEventListener('change', onSettingChange);
            document.getElementById('include-inactive').addEventListener('change', onSettingChange);
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
            const genTime = new Date(generatedAt);

            document.getElementById('generated-time').textContent = formatRelativeTime(genTime);
            buildTreeOptions();
        }

        function loadSettings() {
            // The tree in the URL wins over the stored one, so a view can be
            // linked without the reader's own choice overriding it
            const urlTree = new URLSearchParams(window.location.search).get('tree');

            try {
                document.getElementById('include-no-tree').checked =
                    localStorage.getItem(STORAGE_NO_TREE) === 'true';
                document.getElementById('include-inactive').checked =
                    localStorage.getItem(STORAGE_INACTIVE) === 'true';
                // Splitting is the default, so only an explicit 'false' turns it off
                document.getElementById('split-unknown').checked =
                    localStorage.getItem(STORAGE_SPLIT) !== 'false';

                const tree = urlTree !== null ? urlTree : localStorage.getItem(STORAGE_TREE);
                const select = document.getElementById('tree-filter');

                if (tree !== null &&
                    Array.from(select.options).some(opt => opt.value === tree)) {
                    select.value = tree;
                }
            } catch (err) {
                console.error('Failed to load the stats settings:', err);
            }

            // The counts in the option labels depend on the switches above
            buildTreeOptions();
        }

        function saveSettings() {
            try {
                localStorage.setItem(STORAGE_TREE,
                    document.getElementById('tree-filter').value);
                localStorage.setItem(STORAGE_NO_TREE,
                    String(document.getElementById('include-no-tree').checked));
                localStorage.setItem(STORAGE_SPLIT,
                    String(document.getElementById('split-unknown').checked));
                localStorage.setItem(STORAGE_INACTIVE,
                    String(document.getElementById('include-inactive').checked));
            } catch (err) {
                console.error('Failed to save the stats settings:', err);
            }
        }

        function onTreeChange() {
            const tree = document.getElementById('tree-filter').value;
            const url = new URL(window.location);

            if (tree) {
                url.searchParams.set('tree', tree);
            } else {
                url.searchParams.delete('tree');
            }
            window.history.replaceState({}, '', url);

            saveSettings();
            render();
        }

        function onSettingChange() {
            saveSettings();
            // The switches move the counts, and the counts are in the labels
            buildTreeOptions();
            render();
        }

        function buildTreeOptions() {
            // Carrying the count in each label turns the dropdown itself into
            // a summary, so the shape of the queue is visible without clicking
            // through every tree
            const select = document.getElementById('tree-filter');
            const selected = select.value;
            const counts = countByTree();

            select.innerHTML = '';
            select.appendChild(makeTreeOption('', 'All trees', counts.all));

            treeDesignations.forEach(tree => {
                select.appendChild(makeTreeOption(tree, tree, counts.byTree[tree] || 0));
            });

            // Rebuilding drops the selection, put it back
            if (Array.from(select.options).some(opt => opt.value === selected)) {
                select.value = selected;
            }
        }

        function makeTreeOption(value, label, count) {
            const option = document.createElement('option');

            option.value = value;
            option.textContent = label + ' (' + count + ')';
            return option;
        }

        function countByTree() {
            // What each tree would show if it were selected, the no tree
            // series included in every one of them when asked for
            const includeNoTree = document.getElementById('include-no-tree').checked;
            const byTree = {};
            let tagged = 0;
            let noTree = 0;

            treeDesignations.forEach(tree => {
                byTree[tree] = 0;
            });

            selectedSeries().forEach(series => {
                if (series.tree_designation) {
                    byTree[series.tree_designation] =
                        (byTree[series.tree_designation] || 0) + series.patches.length;
                    tagged += series.patches.length;
                } else {
                    noTree += series.patches.length;
                }
            });

            if (includeNoTree) {
                treeDesignations.forEach(tree => {
                    byTree[tree] += noTree;
                });
            }

            // The no tree series land in every tree above, so summing those
            // would count them once per tree rather than once
            return {byTree: byTree, all: tagged + (includeNoTree ? noTree : 0)};
        }

        function selectedSeries() {
            // Everything the switches let through, before the tree is applied
            const includeInactive = document.getElementById('include-inactive').checked;

            return seriesData.filter(series => includeInactive || !series.is_inactive);
        }

        // Companies get a bar each. Authors with no corpmap entry get one too,
        // when splitting is on, because a single Unknown bar hides the fact
        // that one person can out submit a whole company.
        function aggregate() {
            const tree = document.getElementById('tree-filter').value;
            const includeNoTree = document.getElementById('include-no-tree').checked;
            const splitUnknown = document.getElementById('split-unknown').checked;
            const rows = new Map();
            let patches = 0;
            let seriesCount = 0;

            selectedSeries().forEach(series => {
                if (!series.tree_designation) {
                    // No tree at all, counted against whatever is selected,
                    // but only when asked for
                    if (!includeNoTree) {
                        return;
                    }
                } else if (tree && series.tree_designation !== tree) {
                    return;
                }

                const company = series.author_company;
                const key = company || (splitUnknown ? authorName(series) : UNKNOWN);
                let row = rows.get(key);

                if (!row) {
                    row = {key: key, count: 0, series: 0, individual: !company};
                    rows.set(key, row);
                }
                row.count += series.patches.length;
                row.series += 1;
                patches += series.patches.length;
                seriesCount += 1;
            });

            return {
                rows: [...rows.values()].sort(
                    (a, b) => b.count - a.count || a.key.localeCompare(b.key)),
                patches: patches,
                seriesCount: seriesCount
            };
        }

        function authorName(series) {
            // The maintainer and reviewer markers are per series, they depend
            // on which paths the series touches, so the same person shows up
            // both with and without one. Strip them or they end up as two bars.
            return series.author.replace(' Ⓜ', '').replace(' Ⓡ', '').trim();
        }

        function render() {
            const body = document.getElementById('chart-body');
            const totals = document.getElementById('chart-total');
            const data = aggregate();

            body.innerHTML = '';

            if (!data.rows.length) {
                const empty = document.createElement('div');

                empty.className = 'chart-empty';
                empty.textContent = 'No outstanding patches here.';
                body.appendChild(empty);
                totals.textContent = '';
                return;
            }

            const max = data.rows[0].count;

            data.rows.forEach(entry => {
                const row = document.createElement('div');
                const name = document.createElement('div');
                const track = document.createElement('div');
                const bar = document.createElement('div');
                const count = document.createElement('div');

                row.className = 'bar-row' + (entry.individual ? ' individual' : '');
                row.title = entry.key + ' - ' + plural(entry.count, 'patch', 'patches') +
                            ' in ' + plural(entry.series, 'series', 'series');

                name.className = 'bar-name';
                name.textContent = entry.key;
                row.appendChild(name);

                track.className = 'bar-track';
                bar.className = 'bar';
                bar.style.width = (100 * entry.count / max) + '%';
                track.appendChild(bar);
                row.appendChild(track);

                count.className = 'bar-count';
                count.textContent = entry.count;
                row.appendChild(count);

                body.appendChild(row);
            });

            totals.textContent = plural(data.patches, 'patch', 'patches') + ' in ' +
                                 plural(data.seriesCount, 'series', 'series') + ', ' +
                                 plural(data.rows.length, 'submitter', 'submitters');
        }

        function plural(count, one, many) {
            return count + ' ' + (count === 1 ? one : many);
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
