"""State manager for tracking series, patches, checks, and comments"""

import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta, timezone
from collections import defaultdict


logger = logging.getLogger(__name__)


class StateManager:
    """Manages the in-memory state of patches, series, checks, and comments"""

    def __init__(self):
        """Initialize the state manager"""
        # Core objects
        self.series: Dict[int, Dict] = {}  # series_id -> series data
        self.patches: Dict[int, Dict] = {}  # patch_id -> patch data
        # patch_id -> list of checks
        self.checks: Dict[int, List[Dict]] = defaultdict(list)
        # patch_id -> list of comments
        self.patch_comments: Dict[int, List[Dict]] = defaultdict(list)
        self.cover_letters: Dict[int, Dict] = {}  # cover_id -> cover data
        # cover_id -> list of comments
        self.cover_comments: Dict[int, List[Dict]] = defaultdict(list)

        # Tracking
        self.last_event_id: Optional[int] = None
        self.last_update: Optional[datetime] = None
        self.active_series_ids: Set[int] = set()

    def add_series(self, series_data: Dict):
        """Add or update a series"""
        series_id = series_data['id']
        self.series[series_id] = series_data

        # Track as active if received_all is True and not too old
        if series_data.get('received_all', False):
            self.active_series_ids.add(series_id)

        logger.debug("Added/updated series %d: %s",
                    series_id, series_data.get('name', 'N/A'))

    def add_patch(self, patch_data: Dict):
        """Add or update a patch"""
        patch_id = patch_data['id']
        self.patches[patch_id] = patch_data
        logger.debug("Added/updated patch %d: %s",
                    patch_id, patch_data.get('name', 'N/A'))

    def add_check(self, patch_id: int, check_data: Dict):
        """Add a check for a patch"""
        self.checks[patch_id].append(check_data)
        logger.debug("Added check for patch %d: %s - %s", patch_id,
                    check_data.get('context', 'N/A'),
                    check_data.get('state', 'N/A'))

    def set_checks(self, patch_id: int, checks: List[Dict]):
        """Set all checks for a patch (replacing existing)"""
        self.checks[patch_id] = checks
        logger.debug("Set %d checks for patch %d", len(checks), patch_id)

    def add_patch_comment(self, patch_id: int, comment_data: Dict):
        """Add a comment for a patch"""
        self.patch_comments[patch_id].append(comment_data)
        logger.debug("Added comment for patch %d", patch_id)

    def set_patch_comments(self, patch_id: int, comments: List[Dict]):
        """Set all comments for a patch (replacing existing)"""
        self.patch_comments[patch_id] = comments
        logger.debug("Set %d comments for patch %d", len(comments), patch_id)

    def add_cover_letter(self, cover_data: Dict):
        """Add or update a cover letter"""
        cover_id = cover_data['id']
        self.cover_letters[cover_id] = cover_data
        logger.debug("Added/updated cover letter %d", cover_id)

    def add_cover_comment(self, cover_id: int, comment_data: Dict):
        """Add a comment for a cover letter"""
        self.cover_comments[cover_id].append(comment_data)
        logger.debug("Added comment for cover letter %d", cover_id)

    def set_cover_comments(self, cover_id: int, comments: List[Dict]):
        """Set all comments for a cover letter (replacing existing)"""
        self.cover_comments[cover_id] = comments
        logger.debug("Set %d comments for cover letter %d", len(comments), cover_id)

    def get_series_patches(self, series_id: int) -> List[Dict]:
        """Get all patches for a series"""
        patches = []
        series = self.series.get(series_id)
        if not series:
            return patches

        # Get patch IDs from the series
        patch_refs = series.get('patches', [])
        for patch_ref in patch_refs:
            patch_id = patch_ref.get('id')
            if patch_id and patch_id in self.patches:
                patches.append(self.patches[patch_id])

        return patches

    def get_patch_checks(self, patch_id: int) -> List[Dict]:
        """Get all checks for a patch"""
        return self.checks.get(patch_id, [])

    def get_patch_comments(self, patch_id: int) -> List[Dict]:
        """Get all comments for a patch"""
        return self.patch_comments.get(patch_id, [])

    def get_cover_letter(self, series_id: int) -> Optional[Dict]:
        """Get the cover letter for a series"""
        series = self.series.get(series_id)
        if not series:
            return None

        cover_ref = series.get('cover_letter')
        if not cover_ref:
            return None

        cover_id = cover_ref.get('id')
        return self.cover_letters.get(cover_id)

    def get_cover_comments(self, cover_id: int) -> List[Dict]:
        """Get all comments for a cover letter"""
        return self.cover_comments.get(cover_id, [])

    def get_active_series(self, lookback_days: int = 7) -> List[Dict]:
        """
        Get all active series within the lookback period

        Args:
            lookback_days: Number of days to look back

        Returns:
            List of active series, sorted by date (newest first)
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        active = []

        for series_id in self.active_series_ids:
            series = self.series.get(series_id)
            if not series:
                continue

            # Parse the date
            date_str = series.get('date')
            if not date_str:
                continue

            try:
                # Parse ISO8601 date
                series_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))

                # Check if within lookback period
                if series_date >= cutoff:
                    active.append(series)
            except (ValueError, AttributeError) as e:
                logger.warning("Failed to parse date for series %d: %s", series_id, e)

        # Sort by date, newest first
        active.sort(key=lambda s: s.get('date', ''), reverse=True)
        return active

    def is_series_inactive(self, series_id: int) -> bool:
        """
        Check if a series is inactive.
        A series is active only if at least one patch is in an active state.
        Active states are: new, under-review

        Args:
            series_id: Series ID to check

        Returns:
            True if series is inactive, False otherwise
        """
        patches = self.get_series_patches(series_id)
        if not patches:
            return False

        # Define active states - series is active only if at least one patch is in these states
        active_states = {'new', 'under-review'}

        for patch in patches:
            # Skip archived patches
            if patch.get('archived', False):
                continue

            # Check if patch is in an active state
            state = patch.get('state', '').lower()
            if state in active_states:
                return False  # Found an active patch, series is active

        # No active patches found, series is inactive
        return True

    def get_stats(self) -> Dict:
        """Get statistics about the current state"""
        return {
            'series_count': len(self.series),
            'active_series_count': len(self.active_series_ids),
            'patches_count': len(self.patches),
            'checks_count': sum(len(checks) for checks in self.checks.values()),
            'patch_comments_count': sum(len(comments) for comments in self.patch_comments.values()),
            'cover_letters_count': len(self.cover_letters),
            'cover_comments_count': sum(len(comments) for comments in self.cover_comments.values()),
            'last_event_id': self.last_event_id,
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

    def update_last_event(self, event_id: int, event_date: Optional[str] = None):
        """
        Update the last processed event ID and date

        Args:
            event_id: Event ID
            event_date: ISO 8601 date string from the event (optional)
        """
        self.last_event_id = event_id

        # If event_date is provided, use it; otherwise use current time
        if event_date:
            try:
                # Parse the event date
                if event_date.endswith("Z"):
                    self.last_update = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                else:
                    self.last_update = datetime.fromisoformat(event_date)
                # Convert to UTC if needed
                if self.last_update.tzinfo is None:
                    self.last_update = self.last_update.replace(tzinfo=None)
                    self.last_update = datetime.utcnow()  # Fallback to UTC now
                else:
                    # Convert to UTC for consistent comparisons
                    self.last_update = self.last_update.astimezone(timezone.utc).replace(tzinfo=None)
            except (ValueError, AttributeError):
                # If parsing fails, use current time
                self.last_update = datetime.utcnow()
        else:
            self.last_update = datetime.utcnow()
