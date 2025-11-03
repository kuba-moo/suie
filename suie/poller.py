"""Event poller for tracking changes in Patchwork"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from .patchwork_client import PatchworkClient
from .state import StateManager


logger = logging.getLogger(__name__)


class PatchworkPoller:
    """Polls Patchwork for events and updates state"""

    def __init__(self, client: PatchworkClient, state: StateManager, project: str):
        """
        Initialize the poller

        Args:
            client: Patchwork API client
            state: State manager
            project: Project to monitor
        """
        self.client = client
        self.state = state
        self.project = project

    def initialize_state(self, lookback_days: int = 7):
        """
        Initialize state by fetching recent active series

        Args:
            lookback_days: Number of days to look back
        """
        logger.info("Initializing state for project %s (lookback: %d days)",
                   self.project, lookback_days)

        # First, get the latest event ID before loading state
        # This establishes our baseline - we'll only process events after this ID
        logger.info("Fetching latest event ID as baseline...")
        latest_events = self.client.get_events(self.project, per_page=1, single_page=True)

        if latest_events:
            baseline_event_id = latest_events[0].get('id', 0)
            logger.info("Baseline event ID: %d (will only process events after this)", baseline_event_id)
            self.state.last_event_id = baseline_event_id
        else:
            logger.warning("No events found, starting from event ID 0")
            self.state.last_event_id = 0

        # Calculate the cutoff date for series
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        since = cutoff.isoformat()

        # Fetch recent series
        logger.info("Fetching series...")
        series_list = self.client.get_series(self.project, since=since)
        logger.info("Found %d series", len(series_list))

        # Process each series
        for series_data in series_list:
            self._process_series(series_data)

        # Update last_update timestamp for informational purposes
        self.state.last_update = datetime.utcnow()

        logger.info("State initialized: %s", self.state.get_stats())

    def _process_series(self, series_data: dict):
        """
        Process a series and fetch all related data

        Args:
            series_data: Series data from API
        """
        series_id = series_data['id']
        self.state.add_series(series_data)

        # Fetch detailed series info if needed
        try:
            series_detail = self.client.get_series_detail(series_id)
            self.state.add_series(series_detail)
        except Exception as e:
            logger.warning("Failed to fetch series %d detail: %s", series_id, e)

        # Process patches in the series
        patch_refs = series_data.get('patches', [])
        for patch_ref in patch_refs:
            patch_id = patch_ref.get('id')
            if patch_id:
                self._process_patch(patch_id)

        # Process cover letter if present
        cover_ref = series_data.get('cover_letter')
        if cover_ref:
            cover_id = cover_ref.get('id')
            if cover_id:
                self._process_cover_letter(cover_id)

    def _process_patch(self, patch_id: int):
        """
        Process a patch and fetch all related data

        Args:
            patch_id: Patch ID
        """
        try:
            # Fetch patch detail
            patch_data = self.client.get_patch_detail(patch_id)
            self.state.add_patch(patch_data)

            # Fetch checks
            checks = self.client.get_patch_checks(patch_id)
            self.state.set_checks(patch_id, checks)

            # Fetch comments
            comments = self.client.get_patch_comments(patch_id)
            self.state.set_patch_comments(patch_id, comments)

        except Exception as e:
            logger.warning("Failed to process patch %d: %s", patch_id, e)

    def _process_cover_letter(self, cover_id: int):
        """
        Process a cover letter and fetch all related data

        Args:
            cover_id: Cover letter ID
        """
        try:
            # Fetch cover detail
            cover_data = self.client.get_cover_detail(cover_id)
            self.state.add_cover_letter(cover_data)

            # Fetch comments
            comments = self.client.get_cover_comments(cover_id)
            self.state.set_cover_comments(cover_id, comments)

        except Exception as e:
            logger.warning("Failed to process cover letter %d: %s", cover_id, e)

    def poll_events(self, since: Optional[str] = None) -> bool:
        """
        Poll for new events and update state

        Args:
            since: Unused (kept for compatibility)

        Returns:
            True if state was updated, False otherwise
        """
        # Use last_event_id for reliable event tracking
        since_id = self.state.last_event_id
        logger.debug("Fetching events since ID %s", since_id)

        try:
            events = self.client.get_events(self.project, since_id=since_id)

            if not events:
                logger.debug("No new events")
                return False

            logger.info("Processing %d events", len(events))
            state_changed = False

            # Process events from oldest to newest (reverse the list since API returns newest first)
            for event in reversed(events):
                if self._process_event(event):
                    state_changed = True

            return state_changed

        except Exception as e:
            logger.error("Failed to poll events: %s", e)
            return False

    def _process_event(self, event: dict) -> bool:
        """
        Process a single event

        Args:
            event: Event data

        Returns:
            True if state was changed, False otherwise
        """
        event_id = event.get('id')
        category = event.get('category')
        payload = event.get('payload', {})

        # Skip if we've already processed this event
        if self.state.last_event_id and event_id <= self.state.last_event_id:
            logger.debug("Skipping already processed event %d (last: %d)",
                        event_id, self.state.last_event_id)
            return False

        logger.debug("Processing event %d: %s", event_id, category)

        state_changed = False

        try:
            if category == 'series-created':
                series = payload.get('series', {})
                series_id = series.get('id')
                if series_id:
                    # Fetch and process the full series
                    series_data = self.client.get_series_detail(series_id)
                    self._process_series(series_data)
                    state_changed = True

            elif category == 'series-completed':
                series = payload.get('series', {})
                series_id = series.get('id')
                if series_id:
                    # Refresh the series
                    series_data = self.client.get_series_detail(series_id)
                    self._process_series(series_data)
                    state_changed = True

            elif category == 'patch-created':
                patch = payload.get('patch', {})
                patch_id = patch.get('id')
                if patch_id:
                    self._process_patch(patch_id)
                    state_changed = True

            elif category in ['patch-state-changed', 'patch-delegated', 'patch-completed']:
                patch = payload.get('patch', {})
                patch_id = patch.get('id')
                if patch_id:
                    # Refresh the patch
                    patch_data = self.client.get_patch_detail(patch_id)
                    self.state.add_patch(patch_data)
                    state_changed = True
                    logger.info("Updated patch %d due to %s event", patch_id, category)

            elif category == 'check-created':
                patch = payload.get('patch', {})
                patch_id = patch.get('id')
                if patch_id:
                    # Refresh checks for this patch
                    checks = self.client.get_patch_checks(patch_id)
                    self.state.set_checks(patch_id, checks)
                    state_changed = True

            elif category == 'patch-comment-created':
                patch = payload.get('patch', {})
                patch_id = patch.get('id')
                if patch_id:
                    # Refresh comments for this patch
                    comments = self.client.get_patch_comments(patch_id)
                    self.state.set_patch_comments(patch_id, comments)
                    state_changed = True

            elif category == 'cover-created':
                cover = payload.get('cover', {})
                cover_id = cover.get('id')
                if cover_id:
                    self._process_cover_letter(cover_id)
                    state_changed = True

            elif category == 'cover-comment-created':
                cover = payload.get('cover', {})
                cover_id = cover.get('id')
                if cover_id:
                    # Refresh comments for this cover
                    comments = self.client.get_cover_comments(cover_id)
                    self.state.set_cover_comments(cover_id, comments)
                    state_changed = True

            # Always update last event ID and date, even if we didn't process it
            # This ensures we advance past already-seen events
            event_date = event.get('date')
            self.state.update_last_event(event_id, event_date)

        except Exception as e:
            logger.error("Failed to process event %d: %s", event_id, e)
            # Still update last event ID to avoid getting stuck
            event_date = event.get('date')
            self.state.update_last_event(event_id, event_date)

        return state_changed
