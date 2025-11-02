"""Main application entry point for Suie"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List

import yaml

from .patchwork_client import PatchworkClient
from .state import StateManager
from .poller import PatchworkPoller
from .scoring import DeveloperDatabase, ScoringEngine, SeriesScore
from .ui_generator import UIGenerator


logger = logging.getLogger(__name__)


class SuieApp:
    """Main Suie application"""

    def __init__(self, config_path: str):
        """
        Initialize the application

        Args:
            config_path: Path to the configuration file
        """
        self.config = self._load_config(config_path)
        self._setup_logging()

        # Initialize components
        logger.info("Initializing Suie...")

        self.client = PatchworkClient(
            base_url=self.config['patchwork']['url'],
            user_agent=self.config['patchwork']['user_agent'],
            requests_log_path=self.config['logging'].get('requests_log')
        )

        self.state = StateManager()

        self.poller = PatchworkPoller(
            client=self.client,
            state=self.state,
            project=self.config['patchwork']['project']
        )

        self.dev_db = DeveloperDatabase(
            db_path=self.config['database'].get('mailmap_path'),
            stats_path=self.config['database'].get('stats_path')
        )

        self.scoring_engine = ScoringEngine(
            module_path=self.config['sorting']['module_path'],
            function_name=self.config['sorting']['function_name'],
            dev_db=self.dev_db
        )

        self.ui_generator = UIGenerator(
            output_path=self.config['ui']['output_path'],
            hide_inactive_default=self.config['ui'].get('hide_inactive_default', True),
            expected_checks=self.config['ui'].get('expected_checks', [])
        )

        logger.info("Suie initialized successfully")

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info("Loaded configuration from %s", config_path)
            return config
        except Exception as e:
            logger.error("Failed to load configuration: %s", e)
            sys.exit(1)

    def _setup_logging(self):
        """Setup logging based on configuration"""
        log_level = self.config['logging'].get('level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def initialize(self):
        """Initialize state by fetching recent series"""
        lookback_days = self.config['state'].get('lookback_days', 7)
        logger.info("Initializing state (lookback: %d days)", lookback_days)

        self.poller.initialize_state(lookback_days=lookback_days)

        logger.info("State initialization complete")
        logger.info("Stats: %s", self.state.get_stats())

        # Generate initial UI
        self.regenerate_ui()

        # Save request log
        self.client.save_request_log()

    def poll_and_update(self):
        """Poll for events and regenerate UI if state changed"""
        logger.info("Polling for events...")

        state_changed = self.poller.poll_events()

        if state_changed:
            logger.info("State changed, regenerating UI")
            self.regenerate_ui()
        else:
            logger.debug("No state changes")

        # Save request log
        self.client.save_request_log()

        return state_changed

    def regenerate_ui(self):
        """Regenerate the UI with current state"""
        logger.info("Regenerating UI...")

        lookback_days = self.config['state'].get('lookback_days', 7)
        active_series = self.state.get_active_series(lookback_days)

        logger.info("Processing %d active series", len(active_series))

        # Score all series
        scored_series = []
        delegates = set()

        for series in active_series:
            series_score = self._score_series(series)
            series_data = self._prepare_series_data(series, series_score)
            scored_series.append(series_data)

            # Collect delegates
            for patch_data in series_data['patches']:
                if patch_data['delegate']:
                    delegates.add(patch_data['delegate'])

        # Sort by score (lowest first = highest priority)
        scored_series.sort(key=lambda s: s['score'])

        # Generate UI
        self.ui_generator.generate(scored_series, sorted(delegates))

        logger.info("UI regenerated with %d series", len(scored_series))

    def _score_series(self, series: Dict) -> SeriesScore:
        """Score a series"""
        series_id = series['id']
        patches = self.state.get_series_patches(series_id)

        # Build checks and comments maps
        checks_map = {}
        comments_map = {}

        for patch in patches:
            patch_id = patch['id']
            checks_map[patch_id] = self.state.get_patch_checks(patch_id)
            comments_map[patch_id] = self.state.get_patch_comments(patch_id)

        # Get cover letter and comments
        cover_letter = self.state.get_cover_letter(series_id)
        cover_comments = []
        if cover_letter:
            cover_comments = self.state.get_cover_comments(cover_letter['id'])

        # Score the series
        expected_checks = self.config['ui'].get('expected_checks', [])
        return self.scoring_engine.score_series(
            series, patches, checks_map, comments_map,
            cover_letter, cover_comments, expected_checks
        )

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """
        Normalize a date string to ISO 8601 format with UTC timezone.
        Patchwork dates are in UTC, so we ensure they're properly marked as such.

        Args:
            date_str: Date string from Patchwork (assumed to be UTC)

        Returns:
            ISO 8601 formatted date string with timezone
        """
        if not date_str:
            return ''

        try:
            # Parse the date string - handles various ISO 8601 formats
            # If no timezone info, assume UTC (Patchwork returns UTC times)
            if date_str.endswith('Z') or '+' in date_str or date_str.endswith('-00:00'):
                # Already has timezone info
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            else:
                # No timezone info - assume UTC (Patchwork always returns UTC)
                dt = datetime.fromisoformat(date_str).replace(tzinfo=None)
                # Convert to UTC-aware datetime
                dt = dt.replace(tzinfo=timezone.utc)

            # Return in ISO 8601 format with timezone
            return dt.isoformat()
        except (ValueError, AttributeError) as e:
            logger.warning("Failed to parse date '%s': %s", date_str, e)
            return date_str  # Return as-is if we can't parse it

    @staticmethod
    def _deduplicate_checks(checks: List[Dict]) -> Dict[str, Dict]:
        """
        Deduplicate checks by context, keeping only the latest (highest ID).

        Args:
            checks: List of check dictionaries

        Returns:
            Dictionary mapping context -> latest check data
        """
        checks_by_context = {}
        for check in checks:
            context = check.get('context')
            if not context:
                continue

            # Keep the check with the highest ID (most recent)
            if context not in checks_by_context:
                checks_by_context[context] = check
            else:
                existing_id = checks_by_context[context].get('id', 0)
                new_id = check.get('id', 0)
                if new_id > existing_id:
                    checks_by_context[context] = check

        return checks_by_context

    def _prepare_series_data(self, series: Dict, series_score: SeriesScore) -> Dict:
        """Prepare series data for UI"""
        expected_checks = self.config['ui'].get('expected_checks', [])

        # Aggregate check status across all patches
        # For each check context, track the worst state across all patches
        # Priority: missing > fail > warning > success

        # First pass: collect all check contexts and build per-patch check maps
        all_check_contexts = set(expected_checks)
        patch_checks_map = {}  # patch_id -> {context -> check_data}

        for patch_score in series_score.patch_scores:
            patch_id = patch_score.patch_id
            patch = self.state.patches.get(patch_id)
            if not patch:
                continue

            checks = self.state.get_patch_checks(patch_id)
            # Deduplicate checks by context, keeping only the latest
            checks_dict = self._deduplicate_checks(checks)
            patch_checks_map[patch_id] = checks_dict
            all_check_contexts.update(checks_dict.keys())

        # Second pass: determine worst state for each check context across all patches
        check_states = {}  # check_context -> worst_state

        for context in all_check_contexts:
            worst_state = 'success'  # Start optimistic

            for patch_score in series_score.patch_scores:
                patch_id = patch_score.patch_id
                if patch_id not in patch_checks_map:
                    continue

                checks_dict = patch_checks_map[patch_id]

                if context not in checks_dict:
                    # Check is missing for this patch - highest priority
                    worst_state = 'missing'
                    break  # Can't get worse than missing
                else:
                    # Check exists, get its state
                    check = checks_dict[context]
                    state = check.get('state', 'unknown')

                    # Update to worst state (priority: missing > fail > warning > success)
                    if state == 'fail':
                        worst_state = 'fail'
                    elif state == 'warning' and worst_state not in ['fail']:
                        worst_state = 'warning'
                    # success doesn't change worst_state unless it's still 'success'

            check_states[context] = worst_state

        # Categorize checks by their series-level status
        series_failed_checks = []
        series_warning_checks = []
        series_missing_checks = []
        series_passing_checks = []

        for context, state in check_states.items():
            if state == 'missing':
                series_missing_checks.append(context)
            elif state == 'fail':
                series_failed_checks.append(context)
            elif state == 'warning':
                series_warning_checks.append(context)
            elif state == 'success':
                series_passing_checks.append(context)

        # Prepare patch data
        patches_data = []
        for patch_score in series_score.patch_scores:
            patch_id = patch_score.patch_id
            patch = self.state.patches.get(patch_id)
            if not patch:
                continue

            checks = self.state.get_patch_checks(patch_id)
            # Deduplicate checks by context, keeping only the latest
            checks_dict = self._deduplicate_checks(checks)

            # Get failed, missing, and passing checks for this patch
            failed_checks = []
            passing_checks = 0
            for check in checks_dict.values():
                state = check.get('state')
                if state in ['fail', 'warning']:
                    # Store full check data for failed checks (need URL and description)
                    failed_checks.append({
                        'context': check.get('context'),
                        'state': state,
                        'description': check.get('description', ''),
                        'target_url': check.get('target_url', '')
                    })
                elif state == 'success':
                    passing_checks += 1

            present_checks = set(checks_dict.keys())
            missing_checks = [c for c in expected_checks if c not in present_checks]

            # Get delegate
            delegate = None
            delegate_data = patch.get('delegate')
            if delegate_data:
                delegate = delegate_data.get('username')

            patches_data.append({
                'id': patch_id,
                'name': patch.get('name', 'Unknown'),
                'score': patch_score.score,
                'score_comments': patch_score.comments,
                'checks_failed': failed_checks,
                'checks_missing': missing_checks,
                'checks_passing': passing_checks,
                'delegate': delegate
            })

        # Get author name
        submitter = series.get('submitter', {})
        author_name = submitter.get('name', submitter.get('email', 'Unknown'))

        # Check if series is inactive
        is_inactive = self.state.is_series_inactive(series['id'])

        # Collect unique delegates
        delegates_in_series = sorted(set(
            p['delegate'] for p in patches_data
            if p['delegate']
        ))

        return {
            'id': series['id'],
            'title': series.get('name') or 'No title',
            'author': author_name,
            'date': self._normalize_date(series.get('date', '')),
            'score': series_score.score,
            'is_inactive': is_inactive,
            'patches': patches_data,
            'delegates': delegates_in_series,
            'checks_summary': {
                'failed': sorted(series_failed_checks),
                'warning': sorted(series_warning_checks),
                'missing': sorted(series_missing_checks),
                'passing': len(series_passing_checks)
            }
        }

    def run_continuous(self, poll_interval: int = 300):
        """
        Run in continuous mode, polling for events periodically

        Args:
            poll_interval: Seconds between polls
        """
        logger.info("Running in continuous mode (poll interval: %ds)", poll_interval)

        while True:
            try:
                self.poll_and_update()
            except KeyboardInterrupt:
                logger.info("Received interrupt, shutting down...")
                break
            except Exception as e:
                logger.error("Error in main loop: %s", e, exc_info=True)

            # Always save request log before sleeping (catches any missed saves)
            self.client.save_request_log()
            logger.info("Sleeping for %d seconds...", poll_interval)
            time.sleep(poll_interval)

        # Final save of request log
        self.client.save_request_log()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Suie - Patchwork patch ranking application')
    parser.add_argument('--config', '-c', default='config.yaml',
                       help='Path to configuration file (default: config.yaml)')
    parser.add_argument('--init-only', action='store_true',
                       help='Initialize state and exit (do not poll for updates)')
    parser.add_argument('--poll-interval', type=int, default=300,
                       help='Polling interval in seconds (default: 300)')

    args = parser.parse_args()

    # Create application
    app = SuieApp(args.config)

    # Initialize state
    app.initialize()

    if args.init_only:
        logger.info("Initialization complete, exiting")
        return

    # Run continuous polling
    app.run_continuous(poll_interval=args.poll_interval)


if __name__ == '__main__':
    main()
