"""Main application entry point for Suie"""

import argparse
import logging
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List

import yaml

from .patchwork_client import PatchworkClient
from .poller import PatchworkPoller
from .scoring import DeveloperDatabase, ScoringEngine, SeriesScore
from .state import StateManager
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
            base_url=self.config["patchwork"]["url"],
            user_agent=self.config["patchwork"]["user_agent"],
            requests_log_path=self.config["logging"].get("requests_log"),
        )

        self.state = StateManager()

        self.poller = PatchworkPoller(
            client=self.client,
            state=self.state,
            project=self.config["patchwork"]["project"],
        )

        self.dev_db = DeveloperDatabase(
            db_path=self.config["database"].get("mailmap_path"),
            stats_path=self.config["database"].get("stats_path"),
        )

        self.scoring_engine = ScoringEngine(
            module_path=self.config["sorting"]["module_path"],
            function_name=self.config["sorting"]["function_name"],
            dev_db=self.dev_db,
        )

        self.ui_generator = UIGenerator(
            output_path=self.config["ui"]["output_path"],
            hide_inactive_default=self.config["ui"].get("hide_inactive_default", True),
            expected_checks=self.config["ui"].get("expected_checks", []),
        )

        logger.info("Suie initialized successfully")

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info("Loaded configuration from %s", config_path)
            return config
        except Exception as e:
            logger.error("Failed to load configuration: %s", e)
            sys.exit(1)

    def _setup_logging(self):
        """Setup logging based on configuration"""
        log_level = self.config["logging"].get("level", "INFO")
        logging.basicConfig(
            level=getattr(logging, log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def initialize(self):
        """Initialize state by fetching recent series"""
        lookback_days = self.config["state"].get("lookback_days", 7)
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

        lookback_days = self.config["state"].get("lookback_days", 7)
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
            for patch_data in series_data["patches"]:
                if patch_data["delegate"]:
                    delegates.add(patch_data["delegate"])

        # Sort by score (lowest first = highest priority)
        scored_series.sort(key=lambda s: s["score"])

        # Generate UI
        self.ui_generator.generate(scored_series, sorted(delegates))

        logger.info("UI regenerated with %d series", len(scored_series))

    def _score_series(self, series: Dict) -> SeriesScore:
        """Score a series"""
        series_id = series["id"]
        patches = self.state.get_series_patches(series_id)

        # Build checks and comments maps
        checks_map = {}
        comments_map = {}

        for patch in patches:
            patch_id = patch["id"]
            checks_map[patch_id] = self.state.get_patch_checks(patch_id)
            comments_map[patch_id] = self.state.get_patch_comments(patch_id)

        # Get cover letter and comments
        cover_letter = self.state.get_cover_letter(series_id)
        cover_comments = []
        if cover_letter:
            cover_comments = self.state.get_cover_comments(cover_letter["id"])

        # Calculate age excluding weekends
        date_normalized = self._normalize_date(series.get("date", ""))
        age_breakdown = self._calculate_age_excluding_weekends(date_normalized)

        # Score the series
        expected_checks = self.config["ui"].get("expected_checks", [])
        return self.scoring_engine.score_series(
            series,
            patches,
            checks_map,
            comments_map,
            cover_letter,
            cover_comments,
            expected_checks,
            age_breakdown["weekday_hours"],
            age_breakdown["weekend_hours"],
        )

    @staticmethod
    def _extract_reviewer_names_with_source(patch: Dict, comments: List[Dict]) -> Dict[str, str]:
        """
        Extract reviewer names with their source (original or comment).
        Looks for Reviewed-by, Acked-by, and Tested-by tags.

        Args:
            patch: Patch data
            comments: List of comments for the patch

        Returns:
            Dictionary mapping reviewer name -> source ('original' or 'comment')
        """
        reviewers = {}  # reviewer_name -> source

        # Extract from patch headers and content (original)
        headers = patch.get("headers", {})
        tag_headers = ["Reviewed-by", "Acked-by", "Tested-by"]

        for tag_type in tag_headers:
            values = headers.get(tag_type, [])
            if not isinstance(values, list):
                values = [values]

            for value in values:
                # Extract name from "Name <email>" format
                match = re.match(r"^([^<]+)<", value)
                if match:
                    name = match.group(1).strip()
                    if name:
                        # Mark as original if not already seen, or if already seen as comment
                        reviewers[name] = 'original'
                else:
                    # Try to extract just email and use local part
                    email_match = re.search(r"([a-zA-Z0-9._%+-]+)@", value)
                    if email_match:
                        name = email_match.group(1)
                        if name:
                            reviewers[name] = 'original'

        # Check patch content for trailers (original)
        content = patch.get("content", "")
        tag_pattern = r"(?:Reviewed-by|Acked-by|Tested-by):\s*([^<\n]+)(?:<|$)"
        matches = re.findall(tag_pattern, content, re.IGNORECASE | re.MULTILINE)

        for name in matches:
            name = name.strip()
            if name:
                reviewers[name] = 'original'

        # Check comments for review tags (added later)
        for comment in comments:
            comment_content = comment.get('content', '')
            matches = re.findall(tag_pattern, comment_content, re.IGNORECASE | re.MULTILINE)

            for name in matches:
                name = name.strip()
                if name and name not in reviewers:  # Only add if not already marked as original
                    reviewers[name] = 'comment'

        return reviewers

    @staticmethod
    def _extract_reviewer_names(patch: Dict) -> List[str]:
        """
        Extract reviewer names from a patch.
        Looks for Reviewed-by, Acked-by, and Tested-by tags.

        Args:
            patch: Patch data

        Returns:
            List of reviewer names (not emails)
        """
        reviewers = []
        seen = set()  # Deduplicate reviewers

        # Check headers
        headers = patch.get("headers", {})
        tag_headers = ["Reviewed-by", "Acked-by", "Tested-by"]

        for tag_type in tag_headers:
            values = headers.get(tag_type, [])
            if not isinstance(values, list):
                values = [values]

            for value in values:
                # Extract name from "Name <email>" format
                # Try to get name before <email>
                match = re.match(r"^([^<]+)<", value)
                if match:
                    name = match.group(1).strip()
                    if name and name not in seen:
                        reviewers.append(name)
                        seen.add(name)
                else:
                    # Try to extract just email and use local part
                    email_match = re.search(r"([a-zA-Z0-9._%+-]+)@", value)
                    if email_match:
                        name = email_match.group(1)
                        if name and name not in seen:
                            reviewers.append(name)
                            seen.add(name)

        # Also check patch content for trailers
        content = patch.get("content", "")
        tag_pattern = r"(?:Reviewed-by|Acked-by|Tested-by):\s*([^<\n]+)(?:<|$)"
        matches = re.findall(tag_pattern, content, re.IGNORECASE | re.MULTILINE)

        for name in matches:
            name = name.strip()
            if name and name not in seen:
                reviewers.append(name)
                seen.add(name)

        return reviewers

    @staticmethod
    def _extract_name_from_identity(identity: str) -> str:
        """
        Extract a human-readable name from an identity string.

        Handles formats like:
        - "John Doe <john@example.com>" -> "John Doe"
        - "john@example.com" -> "John Doe" (from email local part, capitalized)
        - "john.doe@example.com" -> "John Doe" (from email, capitalized and dots to spaces)

        Args:
            identity: Identity string (canonical or email)

        Returns:
            Human-readable name
        """
        # Clean up the identity first
        identity = identity.strip()

        # Try to extract name from "Name <email>" format
        match = re.match(r"^(.+?)\s*<", identity)
        if match:
            name = match.group(1).strip()
            # Make sure we got a name, not an email
            if name and "@" not in name and name:
                return name

        # If identity is just an email or we couldn't extract a name,
        # try to make a readable name from the email local part
        email_match = re.search(r"([a-zA-Z0-9._%+-]+)@", identity)
        if email_match:
            local_part = email_match.group(1)
            # Replace dots and underscores with spaces
            name = local_part.replace(".", " ").replace("_", " ")
            # Capitalize each word
            name = " ".join(word.capitalize() for word in name.split())
            return name

        # Last resort: return identity as-is
        return identity

    @staticmethod
    def _extract_reviewer_emails(patch: Dict) -> List[str]:
        """
        Extract reviewer email addresses from a patch.
        Looks for Reviewed-by and Acked-by tags (treating them the same).

        Args:
            patch: Patch data

        Returns:
            List of reviewer email addresses
        """
        reviewers = []
        seen = set()  # Deduplicate reviewers

        # Check headers - only Reviewed-by and Acked-by (per requirements)
        headers = patch.get("headers", {})
        tag_headers = ["Reviewed-by", "Acked-by"]

        for tag_type in tag_headers:
            values = headers.get(tag_type, [])
            if not isinstance(values, list):
                values = [values]

            for value in values:
                # Extract email from "Name <email>" format
                match = re.search(r"<([^>]+)>", value)
                if match:
                    email = match.group(1).strip()
                    if email and email not in seen:
                        reviewers.append(email)
                        seen.add(email)
                else:
                    # Try to extract just email
                    email_match = re.search(
                        r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", value
                    )
                    if email_match:
                        email = email_match.group(1)
                        if email and email not in seen:
                            reviewers.append(email)
                            seen.add(email)

        # Also check patch content for trailers - only Reviewed-by and Acked-by
        content = patch.get("content", "")
        tag_pattern = (r"(?:Reviewed-by|Acked-by):\s*(?:[^<\n]+<)?"
                      r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")
        matches = re.findall(tag_pattern, content, re.IGNORECASE | re.MULTILINE)

        for email in matches:
            email = email.strip()
            if email and email not in seen:
                reviewers.append(email)
                seen.add(email)

        return reviewers

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
            return ""

        try:
            # Parse the date string - handles various ISO 8601 formats
            # If no timezone info, assume UTC (Patchwork returns UTC times)
            if date_str.endswith("Z") or "+" in date_str or date_str.endswith("-00:00"):
                # Already has timezone info
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
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
    def _calculate_age_excluding_weekends(date_str: str) -> Dict[str, float]:
        """
        Calculate the age of a series excluding weekend time.

        For simplicity, assumes only a single weekend overlap.
        Saturday (5) and Sunday (6) are considered weekend days.

        Args:
            date_str: ISO 8601 date string with timezone

        Returns:
            Dictionary with:
                - weekday_hours: Hours elapsed during weekdays
                - weekend_hours: Hours elapsed during weekend
                - total_hours: Total hours elapsed
        """
        if not date_str:
            return {"weekday_hours": 0, "weekend_hours": 0, "total_hours": 0}

        try:
            # Parse the date
            if date_str.endswith("Z"):
                posted_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                posted_dt = datetime.fromisoformat(date_str)

            # Get current time in UTC
            now_dt = datetime.now(timezone.utc)

            # Calculate total elapsed time
            total_elapsed = now_dt - posted_dt
            total_hours = total_elapsed.total_seconds() / 3600

            # Find weekend hours
            # For simplicity, assume only one weekend overlap
            weekend_hours = 0
            weekday_hours = total_hours

            # Iterate through each hour to determine if it falls on weekend
            # This is simple but not the most efficient - good enough for one weekend
            current = posted_dt
            while current < now_dt:
                # Check if current time is on weekend (Saturday=5, Sunday=6)
                weekday = current.weekday()
                if weekday >= 5:  # Saturday or Sunday
                    # Calculate how much of the next hour is in our range
                    next_hour = current + timedelta(hours=1)
                    if next_hour > now_dt:
                        # Partial hour at the end
                        fraction = (now_dt - current).total_seconds() / 3600
                        weekend_hours += fraction
                    else:
                        weekend_hours += 1

                current += timedelta(hours=1)
                if current > now_dt:
                    break

            # Calculate weekday hours
            weekday_hours = total_hours - weekend_hours

            return {
                "weekday_hours": max(0, weekday_hours),
                "weekend_hours": max(0, weekend_hours),
                "total_hours": total_hours
            }

        except (ValueError, AttributeError) as e:
            logger.warning("Failed to calculate age for date '%s': %s", date_str, e)
            return {"weekday_hours": 0, "weekend_hours": 0, "total_hours": 0}

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
            context = check.get("context")
            if not context:
                continue

            # Keep the check with the highest ID (most recent)
            if context not in checks_by_context:
                checks_by_context[context] = check
            else:
                existing_id = checks_by_context[context].get("id", 0)
                new_id = check.get("id", 0)
                if new_id > existing_id:
                    checks_by_context[context] = check

        return checks_by_context

    def _prepare_series_data(self, series: Dict, series_score: SeriesScore) -> Dict:
        """Prepare series data for UI"""
        expected_checks = self.config["ui"].get("expected_checks", [])

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
            worst_state = "success"  # Start optimistic

            for patch_score in series_score.patch_scores:
                patch_id = patch_score.patch_id
                if patch_id not in patch_checks_map:
                    continue

                checks_dict = patch_checks_map[patch_id]

                if context not in checks_dict:
                    # Check is missing for this patch - highest priority
                    worst_state = "missing"
                    break  # Can't get worse than missing

                # Check exists, get its state
                check = checks_dict[context]
                state = check.get("state", "unknown")

                # Update to worst state (priority: missing > fail > warning > success)
                if state == "fail":
                    worst_state = "fail"
                elif state == "warning" and worst_state not in ["fail"]:
                    worst_state = "warning"
                # success doesn't change worst_state unless it's still 'success'

            check_states[context] = worst_state

        # Categorize checks by their series-level status
        series_failed_checks = []
        series_warning_checks = []
        series_missing_checks = []
        series_passing_checks = []

        for context, state in check_states.items():
            if state == "missing":
                series_missing_checks.append(context)
            elif state == "fail":
                series_failed_checks.append(context)
            elif state == "warning":
                series_warning_checks.append(context)
            elif state == "success":
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
                state = check.get("state")
                if state in ["fail", "warning"]:
                    # Store full check data for failed checks (need URL and description)
                    failed_checks.append(
                        {
                            "context": check.get("context"),
                            "state": state,
                            "description": check.get("description", ""),
                            "target_url": check.get("target_url", ""),
                        }
                    )
                elif state == "success":
                    passing_checks += 1

            present_checks = set(checks_dict.keys())
            missing_checks = [c for c in expected_checks if c not in present_checks]

            # Get delegate
            delegate = None
            delegate_data = patch.get("delegate")
            if delegate_data:
                delegate = delegate_data.get("username")

            # Get reviewers with source information
            comments = self.state.get_patch_comments(patch_id)
            reviewers_with_source = self._extract_reviewer_names_with_source(patch, comments)

            # Convert to list of dicts for UI
            reviewers = [
                {"name": name, "source": source}
                for name, source in reviewers_with_source.items()
            ]

            patches_data.append(
                {
                    "id": patch_id,
                    "name": patch.get("name", "Unknown"),
                    "score": patch_score.score,
                    "score_comments": patch_score.comments,
                    "checks_failed": failed_checks,
                    "checks_missing": missing_checks,
                    "checks_passing": passing_checks,
                    "delegate": delegate,
                    "reviewers": reviewers,
                }
            )

        # Get author name
        submitter = series.get("submitter", {})
        author_name = submitter.get("name", submitter.get("email", "Unknown"))

        # Check if series is inactive
        is_inactive = self.state.is_series_inactive(series["id"])

        # Determine series state from patches
        # Collect all unique patch states
        patch_states = set()
        all_archived = True
        for patch_score in series_score.patch_scores:
            patch_id = patch_score.patch_id
            patch = self.state.patches.get(patch_id)
            if patch:
                state = patch.get("state", "").lower()
                if state:
                    patch_states.add(state)
                if not patch.get("archived", False):
                    all_archived = False

        # Determine overall series state
        series_state = None
        if all_archived:
            series_state = "archived"
        elif "rejected" in patch_states:
            series_state = "rejected"
        elif "accepted" in patch_states:
            if len(patch_states) == 1:
                series_state = "accepted"
            else:
                series_state = "accepted (partial)"
        elif "superseded" in patch_states:
            series_state = "superseded"
        elif "deferred" in patch_states:
            series_state = "deferred"
        elif "not-applicable" in patch_states:
            series_state = "not-applicable"
        elif "under-review" in patch_states or "rfc" in patch_states:
            series_state = "under-review"
        elif "new" in patch_states or "changes-requested" in patch_states:
            series_state = "new"

        # Collect unique delegates
        delegates_in_series = sorted(
            set(p["delegate"] for p in patches_data if p["delegate"])
        )

        # Aggregate external reviewers at series level
        # Get author's company
        author_email = submitter.get("email", "")
        author_company = self.dev_db.get_company(author_email)

        # Track which reviewers reviewed which patches
        # Use email as key to properly deduplicate, store name separately
        reviewer_data = {}  # canonical_email -> {'name': str, 'patches': set}
        total_patches = len(series_score.patch_scores)

        for patch_score in series_score.patch_scores:
            patch_id = patch_score.patch_id
            patch = self.state.patches.get(patch_id)
            if not patch:
                continue

            # Extract review tags with email addresses from the patch
            # This preserves the full names as they appear in the patch

            # Helper function to process review tags
            def process_review_tag(value):
                """Extract name and email from a review tag, process it"""
                # Extract both name and email from "Name <email>" format
                match = re.match(r"^(.+?)\s*<([^>]+)>", value)
                if match:
                    name = match.group(1).strip()
                    email = match.group(2).strip()
                else:
                    # Try to extract just email
                    email_match = re.search(
                        r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", value
                    )
                    if email_match:
                        email = email_match.group(1)
                        name = self._extract_name_from_identity(email)
                    else:
                        return None, None

                return name, email

            def add_reviewer(name, email):
                """Add or update reviewer in reviewer_data"""
                # Check if this is an external reviewer
                reviewer_company = self.dev_db.get_company(email)
                if reviewer_company != author_company or author_company is None:
                    # Get canonical email for deduplication
                    canonical_id = self.dev_db.get_canonical_identity(email)
                    canonical_email_match = re.search(r"<([^>]+)>", canonical_id)
                    if canonical_email_match:
                        canonical_email = canonical_email_match.group(1)
                    else:
                        canonical_email = email

                    # Add or update reviewer data
                    if canonical_email not in reviewer_data:
                        reviewer_data[canonical_email] = {
                            'name': name,
                            'patches': set()
                        }
                    # If we see a longer/better name, use it
                    elif len(name) > len(reviewer_data[canonical_email]['name']):
                        reviewer_data[canonical_email]['name'] = name

                    reviewer_data[canonical_email]['patches'].add(patch_id)

            # Check patch headers
            headers = patch.get("headers", {})
            tag_headers = ["Reviewed-by", "Acked-by"]

            for tag_type in tag_headers:
                values = headers.get(tag_type, [])
                if not isinstance(values, list):
                    values = [values]

                for value in values:
                    name, email = process_review_tag(value)
                    if name and email:
                        add_reviewer(name, email)

            # Check patch content for trailers
            content = patch.get("content", "")
            tag_pattern = r"(?:Reviewed-by|Acked-by):\s*(.+?)(?:\n|$)"
            matches = re.findall(tag_pattern, content, re.IGNORECASE | re.MULTILINE)

            for value in matches:
                name, email = process_review_tag(value)
                if name and email:
                    add_reviewer(name, email)

            # IMPORTANT: Also check comments for review tags
            comments = self.state.get_patch_comments(patch_id)
            for comment in comments:
                comment_content = comment.get('content', '')
                matches = re.findall(tag_pattern, comment_content, re.IGNORECASE | re.MULTILINE)

                for value in matches:
                    name, email = process_review_tag(value)
                    if name and email:
                        add_reviewer(name, email)

        # Categorize reviewers: full (reviewed all patches) vs partial (reviewed some)
        reviewers_full = []
        reviewers_partial = []

        for _canonical_email, data in reviewer_data.items():
            reviewer_name = data['name']
            patch_ids = data['patches']
            if len(patch_ids) == total_patches:
                reviewers_full.append(reviewer_name)
            else:
                reviewers_partial.append(reviewer_name)

        # Sort reviewer lists
        reviewers_full.sort()
        reviewers_partial.sort()

        # Get Lore URL - try cover letter first, then first patch
        lore_url = series.get("list_archive_url")
        if not lore_url:
            # Try cover letter
            cover_letter = self.state.get_cover_letter(series["id"])
            if cover_letter:
                lore_url = cover_letter.get("list_archive_url")

            # If still no URL, try first patch
            if not lore_url and series_score.patch_scores:
                first_patch_id = series_score.patch_scores[0].patch_id
                first_patch = self.state.patches.get(first_patch_id)
                if first_patch:
                    lore_url = first_patch.get("list_archive_url")

        # Calculate age excluding weekends
        date_normalized = self._normalize_date(series.get("date", ""))
        age_breakdown = self._calculate_age_excluding_weekends(date_normalized)

        return {
            "id": series["id"],
            "title": series.get("name") or "No title",
            "author": author_name,
            "date": date_normalized,
            "age_weekday_hours": age_breakdown["weekday_hours"],
            "age_weekend_hours": age_breakdown["weekend_hours"],
            "age_total_hours": age_breakdown["total_hours"],
            "score": series_score.score,
            "is_inactive": is_inactive,
            "state": series_state,
            "patches": patches_data,
            "delegates": delegates_in_series,
            "reviewers_full": reviewers_full,
            "reviewers_partial": reviewers_partial,
            "lore_url": lore_url,
            "patchwork_url": series.get("web_url"),
            "checks_summary": {
                "failed": sorted(series_failed_checks),
                "warning": sorted(series_warning_checks),
                "missing": sorted(series_missing_checks),
                "passing": len(series_passing_checks),
            },
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
    parser = argparse.ArgumentParser(
        description="Suie - Patchwork patch ranking application"
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Initialize state and exit (do not poll for updates)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=300,
        help="Polling interval in seconds (default: 300)",
    )

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


if __name__ == "__main__":
    main()
