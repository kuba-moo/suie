"""Main application entry point for Suie"""

import argparse
import fnmatch
import logging
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import requests
import yaml

from .patchwork_client import PatchworkClient
from .poller import PatchworkPoller
from .scoring import DeveloperDatabase, ScoringEngine, SeriesScore
from .state import StateManager
from .ui_generator import UIGenerator


logger = logging.getLogger(__name__)


class Person:
    """Person representation for maintainer matching"""
    def __init__(self, name_email):
        self.name_email = name_email
        self.name, self.email = self.name_email_split(name_email)

    @staticmethod
    def name_email_split(name_email):
        idx = name_email.rfind('<')
        if idx > 1:
            idx = name_email.rfind('<')
            name = name_email[:idx].strip()
            email = name_email[idx + 1:-1].strip()
        else:
            if idx > -1:
                name_email = name_email[idx + 1:-1]
            name = ''
            email = name_email
        if '+' in email and email.find('+') < email.find('@'):
            pidx = email.find('+')
            didx = email.find('@')
            email = email[:pidx] + email[didx:]

        return name, email

    def __eq__(self, other):
        # Handle comparison with another Person object
        if isinstance(other, Person):
            return self.email == other.email
        # Handle comparison with string (name_email format)
        if self.name_email == other:
            return True
        _, email = self.name_email_split(other)
        return self.email == email


class MaintainersEntry:
    """Entry in MAINTAINERS file"""
    def __init__(self, lines):
        self._raw = lines

        self.title = lines[0]
        self.maintainers = []
        self.reviewers = []
        self.files = []

        for line in lines[1:]:
            if line[:3] == 'M:\t':
                self.maintainers.append(Person(line[3:]))
            elif line[:3] == 'R:\t':
                self.reviewers.append(Person(line[3:]))
            elif line[:3] == 'F:\t':
                self.files.append(line[3:])

        self._owners = self.maintainers + self.reviewers

        self._file_match = []
        self._file_pfx = []
        for F in self.files:
            # Strip trailing wildcard, it's implicit and slows down the match
            if F.endswith('*'):
                F = F[:-1]
            if '?' in F or '*' in F or '[' in F:
                self._file_match.append(F)
            else:
                self._file_pfx.append(F)

    def match_owner(self, person):
        for M in self._owners:
            if person == M:
                return True
        return False

    def match_path(self, path):
        for F in self._file_pfx:
            if path.startswith(F):
                return True
        for F in self._file_match:
            if fnmatch.fnmatch(path, F):
                return True
        return False


class MaintainersList:
    """List of maintainer entries"""
    def __init__(self):
        self._list = []

    def __len__(self):
        return len(self._list)

    def add(self, other):
        self._list.append(other)

    def find_by_paths(self, paths):
        ret = MaintainersList()
        for entry in self._list:
            for path in paths:
                if entry.match_path(path):
                    ret.add(entry)
                    break
        return ret

    def find_by_owner(self, person):
        ret = MaintainersList()
        for entry in self._list:
            if entry.match_owner(person):
                ret.add(entry)
        return ret


class Maintainers:
    """Parser for kernel MAINTAINERS file"""
    def __init__(self, *, file=None, url=None, config=None):
        self.entries = MaintainersList()

        self.http_headers = None
        if config:
            ua = config.get('patchwork', {}).get('user_agent', '')
            if ua:
                self.http_headers = {"user-agent": ua}

        if file:
            self._load_from_file(file)
        elif url:
            self._load_from_url(url)

    def _load_from_lines(self, lines):
        group = []
        started = False
        for line in lines:
            # Skip the "intro" section of MAINTAINERS
            started |= line.isupper()
            if not started:
                continue

            # Fix up tabs vs spaces
            if len(line) > 5 and line[0].isupper() and line[1:4] == ':  ':
                logger.debug("Bad attr line: %s %s", group, line.strip())
                line = line[:2] + '\t' + line[2:].strip()

            if line == '':
                if len(group) > 1:
                    self.entries.add(MaintainersEntry(group))
                    group = []
                else:
                    if group:
                        logger.debug('Empty group: %s', group)
            elif (len(line) > 3 and line[1:3] == ':\t') or len(group) == 0:
                group.append(line.strip())
            else:
                logger.debug("Bad group: %s %s", group, line.strip())
                group = [line.strip()]

    def _load_from_file(self, file):
        with open(file, 'r') as f:
            self._load_from_lines(f.read().split('\n'))

    def _load_from_url(self, url):
        r = requests.get(url, headers=self.http_headers)
        data = r.content.decode('utf-8')
        self._load_from_lines(data.split('\n'))

    def find_by_path(self, path):
        return self.entries.find_by_paths([path])

    def find_by_paths(self, paths):
        return self.entries.find_by_paths(paths)

    def find_by_owner(self, person):
        return self.entries.find_by_owner(person)


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
            tracking_scripts=self.config["ui"].get("tracking_scripts", []),
        )

        # Load MAINTAINERS file if configured
        self.maintainers = None
        self.maintainers_config = self.config.get("maintainers", {})
        self.maintainers_last_loaded = None

        if self.maintainers_config.get("enabled", False):
            self._load_maintainers()

        logger.info("Suie initialized successfully")

    def _load_maintainers(self):
        """Load or reload MAINTAINERS file"""
        maintainers_file = self.maintainers_config.get("file")
        maintainers_url = self.maintainers_config.get("url")

        try:
            if maintainers_file:
                logger.info("Loading MAINTAINERS from file: %s", maintainers_file)
                self.maintainers = Maintainers(file=maintainers_file, config=self.config)
            elif maintainers_url:
                logger.info("Loading MAINTAINERS from URL: %s", maintainers_url)
                self.maintainers = Maintainers(url=maintainers_url, config=self.config)

            if self.maintainers:
                logger.info("Loaded %d MAINTAINERS entries", len(self.maintainers.entries))
                self.maintainers_last_loaded = datetime.now(timezone.utc)
        except Exception as e:
            logger.warning("Failed to load MAINTAINERS: %s", e)
            self.maintainers = None

    def _check_and_reload_maintainers(self):
        """Check if MAINTAINERS needs reloading (once per day) and reload if needed"""
        if not self.maintainers_config.get("enabled", False):
            return

        # If never loaded, load it now
        if self.maintainers_last_loaded is None:
            self._load_maintainers()
            return

        # Check if 24 hours have passed since last load
        now = datetime.now(timezone.utc)
        time_since_load = now - self.maintainers_last_loaded
        hours_since_load = time_since_load.total_seconds() / 3600

        if hours_since_load >= 24:
            logger.info(
                "MAINTAINERS file is %.1f hours old, reloading...",
                hours_since_load
            )
            self._load_maintainers()

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

        # Check and reload MAINTAINERS if needed (once per day)
        self._check_and_reload_maintainers()

        state_changed = self.poller.poll_events()

        # Check if new stats file is available
        stats_reloaded = self.dev_db.check_and_reload_stats()

        if stats_reloaded:
            logger.info("New stats file loaded, forcing UI regeneration")
            state_changed = True  # Force regeneration even if no patch changes

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

        # Calculate time since most recent comment
        time_since_last_comment_hours = self._calculate_time_since_last_comment(
            comments_map, cover_comments
        )

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
            time_since_last_comment_hours,
        )

    def _extract_commenters_without_tags(self, comments: List[Dict], series_id: int, author_email: str) -> List[str]:
        """
        Extract names of people who commented without providing review tags.
        Excludes the author from the list.

        Args:
            comments: List of comments
            series_id: Series ID (for logging)
            author_email: Author's email to exclude

        Returns:
            List of commenter names (deduplicated, excluding author)
        """
        commenters = set()

        # Get author's canonical email for comparison
        author_canonical = self.dev_db.get_canonical_identity(author_email).lower()

        for comment in comments:
            # Skip empty comments
            content = comment.get('content', '').strip()
            if not content or len(content) < 20:  # Skip very short comments
                continue

            # Check if comment contains review tags - if so, skip (already tracked)
            tag_pattern = r"(?:Reviewed-by|Acked-by|Tested-by):\s*"
            if re.search(tag_pattern, content, re.IGNORECASE):
                continue

            # Extract submitter information
            submitter = comment.get('submitter', {})
            name = (submitter.get('name') or '').strip()
            email = submitter.get('email') or ''

            # Skip if this is the author
            if email:
                commenter_canonical = self.dev_db.get_canonical_identity(email).lower()
                if commenter_canonical == author_canonical:
                    continue

            # If no name, try to extract from email
            if not name:
                if email:
                    # Extract name from email local part
                    local_match = re.match(r"([^@]+)@", email)
                    if local_match:
                        local_part = local_match.group(1)
                        name = local_part.replace('.', ' ').replace('_', ' ')
                        name = ' '.join(word.capitalize() for word in name.split())

            if name:
                commenters.add(name)

                # Log if commenter is not in ml-stats (unless it's a bot)
                if email and not self.dev_db.is_bot(email):
                    stats_key = self.dev_db._find_in_stats(email)
                    if not stats_key:
                        logger.info(
                            "Commenter %s (%s) not found in ml-stats for series #%d",
                            name, email, series_id
                        )

        return sorted(list(commenters))

    def _extract_reviewer_names_with_source(self, patch: Dict, comments: List[Dict], author_email: str) -> Dict[str, str]:
        """
        Extract reviewer names with their source (original or comment).
        Looks for Reviewed-by, Acked-by, and Tested-by tags.
        Excludes the author from the list.

        Priority rules:
        - If review tag in comments → 'comment' (engaged via comment)
        - If review tag in original AND person commented (without tag) → 'comment' (engaged)
        - If review tag in original only → 'original' (passive review)

        Match reviewers to commenters by name only (not email), as people may use
        different email addresses for comments vs review tags.

        Args:
            patch: Patch data
            comments: List of comments for the patch
            author_email: Author's email to exclude

        Returns:
            Dictionary mapping reviewer name -> source ('original' or 'comment')
        """
        reviewers_original = {}  # name -> True
        reviewers_comment = {}   # name -> True
        commenters = set()       # Set of commenter names (commented without review tag)

        # Get author's canonical email for comparison
        author_canonical = self.dev_db.get_canonical_identity(author_email).lower()

        # Helper to normalize name for matching
        def normalize_name(name):
            """Normalize name for case-insensitive matching"""
            return name.strip().lower()

        # Extract from patch headers and content (original reviews)
        headers = patch.get("headers", {})
        tag_headers = ["Reviewed-by", "Acked-by", "Tested-by"]

        for tag_type in tag_headers:
            values = headers.get(tag_type, [])
            if not isinstance(values, list):
                values = [values]

            for value in values:
                # Extract email to check if it's the author
                email_match = re.search(r"<([^>]+)>", value)
                if email_match:
                    reviewer_email = email_match.group(1).strip()
                    reviewer_canonical = self.dev_db.get_canonical_identity(reviewer_email).lower()
                    if reviewer_canonical == author_canonical:
                        continue  # Skip author

                # Extract name from "Name <email>" format
                match = re.match(r"^([^<]+)<", value)
                if match:
                    name = match.group(1).strip()
                    if name:
                        reviewers_original[normalize_name(name)] = name
                else:
                    # Try to extract just email and use local part
                    email_match = re.search(r"([a-zA-Z0-9._%+-]+)@", value)
                    if email_match:
                        name = email_match.group(1)
                        if name:
                            reviewers_original[normalize_name(name)] = name

        # Check patch content for trailers (original reviews)
        content = patch.get("content", "")
        tag_pattern = r"(?:Reviewed-by|Acked-by|Tested-by):\s*([^<\n]+)(?:<([^>]+)>|$)"
        matches = re.findall(tag_pattern, content, re.IGNORECASE | re.MULTILINE)

        for name, email in matches:
            name = name.strip()
            email = email.strip()

            # Skip if this is the author
            if email:
                reviewer_canonical = self.dev_db.get_canonical_identity(email).lower()
                if reviewer_canonical == author_canonical:
                    continue

            if name:
                reviewers_original[normalize_name(name)] = name

        # Check comments for review tags (comment reviews)
        for comment in comments:
            comment_content = comment.get('content', '')
            matches = re.findall(tag_pattern, comment_content, re.IGNORECASE | re.MULTILINE)

            for name, email in matches:
                name = name.strip()
                email = email.strip()

                # Skip if this is the author
                if email:
                    reviewer_canonical = self.dev_db.get_canonical_identity(email).lower()
                    if reviewer_canonical == author_canonical:
                        continue

                if name:
                    reviewers_comment[normalize_name(name)] = name

        # Extract commenters (people who commented without review tags)
        for comment in comments:
            content = comment.get('content', '').strip()
            if not content or len(content) < 20:  # Skip very short comments
                continue

            # Check if comment contains review tags - if so, skip (already tracked)
            tag_pattern_check = r"(?:Reviewed-by|Acked-by|Tested-by):\s*"
            if re.search(tag_pattern_check, content, re.IGNORECASE):
                continue

            # Extract submitter information
            submitter = comment.get('submitter', {})
            name = (submitter.get('name') or '').strip()
            email = submitter.get('email') or ''

            # Skip if this is the author
            if email:
                commenter_canonical = self.dev_db.get_canonical_identity(email).lower()
                if commenter_canonical == author_canonical:
                    continue

            # If no name, try to extract from email
            if not name:
                if email:
                    # Extract name from email local part
                    local_match = re.match(r"([^@]+)@", email)
                    if local_match:
                        local_part = local_match.group(1)
                        name = local_part.replace('.', ' ').replace('_', ' ')
                        name = ' '.join(word.capitalize() for word in name.split())

            if name:
                commenters.add(normalize_name(name))

        # Build final result with priority rules
        result = {}  # name -> source

        # Priority 1: Review tag in comments → 'comment'
        for normalized_name, display_name in reviewers_comment.items():
            result[display_name] = 'comment'

        # Priority 2: Review tag in original
        for normalized_name, display_name in reviewers_original.items():
            # Skip if already in comments (priority 1)
            if normalized_name in reviewers_comment:
                continue

            # If they also commented (without adding a tag) → 'comment' (engaged)
            if normalized_name in commenters:
                result[display_name] = 'comment'
            else:
                # Pure original review, no engagement → 'original'
                result[display_name] = 'original'

        return result

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
        Looks for Reviewed-by, Acked-by, and Tested-by tags (treating them the same).

        Args:
            patch: Patch data

        Returns:
            List of reviewer email addresses
        """
        reviewers = []
        seen = set()  # Deduplicate reviewers

        # Check headers - Reviewed-by, Acked-by, and Tested-by
        headers = patch.get("headers", {})
        tag_headers = ["Reviewed-by", "Acked-by", "Tested-by"]

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

        # Also check patch content for trailers - Reviewed-by, Acked-by, and Tested-by
        content = patch.get("content", "")
        tag_pattern = (r"(?:Reviewed-by|Acked-by|Tested-by):\s*(?:[^<\n]+<)?"
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
    def _calculate_time_since_last_comment(comments_map: Dict[int, List[Dict]],
                                           cover_comments: List[Dict]) -> Optional[float]:
        """
        Calculate the time in hours since the most recent comment.

        Args:
            comments_map: Map of patch_id -> comments
            cover_comments: Comments on the cover letter

        Returns:
            Hours since most recent comment, or None if no comments
        """
        most_recent_date = None

        # Check all patch comments
        for comments in comments_map.values():
            for comment in comments:
                date_str = comment.get('date')
                if not date_str:
                    continue

                try:
                    # Parse the date - ensure it's timezone-aware
                    if date_str.endswith("Z"):
                        comment_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    elif "+" in date_str or date_str.endswith("-00:00"):
                        # Already has timezone info
                        comment_dt = datetime.fromisoformat(date_str)
                    else:
                        # No timezone info - assume UTC (Patchwork always returns UTC)
                        comment_dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

                    # Track most recent
                    if most_recent_date is None or comment_dt > most_recent_date:
                        most_recent_date = comment_dt

                except (ValueError, AttributeError):
                    continue

        # Check cover letter comments
        for comment in cover_comments:
            date_str = comment.get('date')
            if not date_str:
                continue

            try:
                # Parse the date - ensure it's timezone-aware
                if date_str.endswith("Z"):
                    comment_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                elif "+" in date_str or date_str.endswith("-00:00"):
                    # Already has timezone info
                    comment_dt = datetime.fromisoformat(date_str)
                else:
                    # No timezone info - assume UTC (Patchwork always returns UTC)
                    comment_dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

                # Track most recent
                if most_recent_date is None or comment_dt > most_recent_date:
                    most_recent_date = comment_dt

            except (ValueError, AttributeError):
                continue

        # If no comments found, return None
        if most_recent_date is None:
            return None

        # Calculate time since most recent comment
        now_dt = datetime.now(timezone.utc)
        time_since = now_dt - most_recent_date
        hours_since = time_since.total_seconds() / 3600

        return hours_since

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

    def _find_previous_versions(self, series: Dict) -> List[Dict]:
        """
        Find all previous versions of a series by matching title.

        Looks for series with:
        - Same title (ignoring version numbers in square brackets)
        - Lower version number
        - Different series ID

        Args:
            series: Current series data

        Returns:
            List of previous version series data, sorted by version (ascending)
        """
        current_id = series["id"]
        current_version = series.get("version", 1)
        current_title = series.get("name") or ""

        # Normalize title by removing version prefix like "v2" or "[PATCH v3]"
        # and tree designation like "[net-next]"
        def normalize_title(title):
            # Handle None or empty title
            if not title:
                return ""

            # Remove [PATCH vX] or [PATCH vX NN/MM] patterns
            title = re.sub(r'\[PATCH\s+v\d+(?:\s+\d+/\d+)?\]', '', title, flags=re.IGNORECASE)
            # Remove [vX] patterns
            title = re.sub(r'\[v\d+\]', '', title, flags=re.IGNORECASE)
            # Remove tree designation like [net-next], [net], etc.
            title = re.sub(r'\[[a-z0-9_-]+\]', '', title, flags=re.IGNORECASE)
            # Clean up extra whitespace
            title = re.sub(r'\s+', ' ', title).strip()
            return title.lower()

        current_title_normalized = normalize_title(current_title)

        if not current_title_normalized:
            return []

        # Search through all known series (including inactive ones)
        # Keep track of all matching versions
        matches_by_version = {}  # version -> series_data

        for candidate_id, candidate in self.state.series.items():
            # Skip the current series
            if candidate_id == current_id:
                continue

            candidate_title = candidate.get("name") or ""
            candidate_version = candidate.get("version", 1)
            candidate_date_str = candidate.get("date", "")

            # Normalize and compare titles
            candidate_title_normalized = normalize_title(candidate_title)

            if candidate_title_normalized != current_title_normalized:
                continue

            # Titles match - check if this is a previous version
            # Previous version must have lower version number
            if candidate_version >= current_version:
                continue

            # Parse dates for comparison (for deduplication)
            try:
                if candidate_date_str.endswith("Z"):
                    candidate_date = datetime.fromisoformat(candidate_date_str.replace("Z", "+00:00"))
                elif "+" in candidate_date_str:
                    candidate_date = datetime.fromisoformat(candidate_date_str)
                else:
                    candidate_date = datetime.fromisoformat(candidate_date_str).replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                candidate_date = None

            # If we already have this version, keep the newer one
            if candidate_version in matches_by_version:
                existing = matches_by_version[candidate_version]
                existing_date_str = existing.get("date", "")
                try:
                    if existing_date_str.endswith("Z"):
                        existing_date = datetime.fromisoformat(existing_date_str.replace("Z", "+00:00"))
                    elif "+" in existing_date_str:
                        existing_date = datetime.fromisoformat(existing_date_str)
                    else:
                        existing_date = datetime.fromisoformat(existing_date_str).replace(tzinfo=timezone.utc)
                except (ValueError, AttributeError):
                    existing_date = None

                # Keep the newer one
                if candidate_date and existing_date and candidate_date > existing_date:
                    matches_by_version[candidate_version] = candidate
            else:
                matches_by_version[candidate_version] = candidate

        # Sort by version number (ascending)
        sorted_versions = sorted(matches_by_version.items(), key=lambda x: x[0])
        return [series_data for _version, series_data in sorted_versions]

    @staticmethod
    def _parse_diff_for_paths(diff_content: str) -> List[str]:
        """
        Parse a git diff to extract modified file paths.

        Args:
            diff_content: Git diff content

        Returns:
            List of modified file paths
        """
        paths = []

        # Look for diff --git a/path b/path lines
        # or +++ b/path lines
        for line in diff_content.split('\n'):
            # Match diff --git a/path b/path
            git_match = re.match(r'^diff --git a/(.+) b/.+$', line)
            if git_match:
                path = git_match.group(1)
                if path != '/dev/null':  # Skip deletions
                    paths.append(path)
                continue

            # Match +++ b/path (fallback)
            plus_match = re.match(r'^\+\+\+ b/(.+)$', line)
            if plus_match:
                path = plus_match.group(1)
                if path != '/dev/null':  # Skip deletions
                    paths.append(path)

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for path in paths:
            if path not in seen:
                seen.add(path)
                deduped.append(path)

        return deduped

    def _check_maintainer(self, email: str, paths: List[str]) -> bool:
        """
        Check if a person is a maintainer of any of the modified paths.

        Args:
            email: Email address to check
            paths: List of file paths

        Returns:
            True if person is a maintainer of at least one path
        """
        if not self.maintainers or not email or not paths:
            return False

        # Create a Person object for matching
        person_str = f"<{email}>"
        person = Person(person_str)

        # Find all maintainer entries for these paths
        matching_entries = self.maintainers.find_by_paths(paths)

        # Check if this person is listed in any of the matching entries
        for entry in matching_entries._list:
            if entry.match_owner(person):
                return True

        return False

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
            reviewers_with_source = self._extract_reviewer_names_with_source(
                patch, comments, author_email
            )

            # Convert to list of dicts for UI
            reviewers = [
                {"name": name, "source": source}
                for name, source in reviewers_with_source.items()
            ]

            # Get commenters (people who commented without providing review tags)
            commenters = self._extract_commenters_without_tags(
                comments, series["id"], author_email
            )

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
                    "commenters": commenters,
                }
            )

        # Get author name and company
        submitter = series.get("submitter", {})
        author_email = submitter.get("email", "")
        author_name = submitter.get("name", "")

        # If name is missing or empty, use email address
        if not author_name or not author_name.strip():
            author_name = author_email if author_email else "Unknown"

        author_company = None

        if author_email:
            author_company = self.dev_db.get_company(author_email)

            # Warn if author is not found in ml-stats (unless it's a bot)
            if not self.dev_db.is_bot(author_email):
                stats_key = self.dev_db._find_in_stats(author_email)
                if not stats_key:
                    logger.warning(
                        "Author %s (%s) not found in ml-stats for series #%d: %s",
                        author_name, author_email, series["id"], series.get("name", "")
                    )

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
        elif "changes-requested" in patch_states:
            series_state = "changes-requested"
        elif "rfc" in patch_states:
            series_state = "rfc"
        elif "awaiting-upstream" in patch_states:
            series_state = "awaiting-upstream"
        elif "deferred" in patch_states:
            series_state = "deferred"
        elif "not-applicable" in patch_states:
            series_state = "not-applicable"
        elif "under-review" in patch_states:
            series_state = "under-review"
        elif "new" in patch_states:
            series_state = "new"

        # Collect unique delegates
        delegates_in_series = sorted(
            set(p["delegate"] for p in patches_data if p["delegate"])
        )

        # Aggregate external reviewers at series level
        # Get author's company
        author_email = submitter.get("email", "")
        author_company = self.dev_db.get_company(author_email)

        # Parse patch diffs to extract modified paths (for maintainer checking)
        modified_paths = []
        for patch_score in series_score.patch_scores:
            patch_id = patch_score.patch_id
            patch = self.state.patches.get(patch_id)
            if patch:
                diff_content = patch.get("diff", "")
                if diff_content:
                    patch_paths = self._parse_diff_for_paths(diff_content)
                    modified_paths.extend(patch_paths)

        # Deduplicate paths
        modified_paths = list(set(modified_paths))

        # Track which reviewers reviewed which patches and the source
        # Use name (normalized) as key to properly deduplicate across patches
        # canonical_email -> {'name': str, 'patches': set, 'sources': set of ('original' or 'comment')}
        reviewer_data = {}  # canonical_email -> data
        total_patches = len(series_score.patch_scores)

        for patch_score in series_score.patch_scores:
            patch_id = patch_score.patch_id
            patch = self.state.patches.get(patch_id)
            if not patch:
                continue

            # Get reviewers with source information for this patch
            comments = self.state.get_patch_comments(patch_id)
            reviewers_with_source = self._extract_reviewer_names_with_source(patch, comments)

            # For each reviewer in this patch, track them at series level
            for reviewer_name, source in reviewers_with_source.items():
                # Try to find email from patch headers/content/comments
                # This is needed to check if they're external and for deduplication

                # Search in patch headers
                headers = patch.get("headers", {})
                tag_headers = ["Reviewed-by", "Acked-by", "Tested-by"]

                reviewer_email = None
                for tag_type in tag_headers:
                    values = headers.get(tag_type, [])
                    if not isinstance(values, list):
                        values = [values]

                    for value in values:
                        # Check if this value contains our reviewer's name
                        if reviewer_name.lower() in value.lower():
                            # Extract email
                            email_match = re.search(r"<([^>]+)>", value)
                            if email_match:
                                reviewer_email = email_match.group(1).strip()
                                break
                            # Try bare email
                            email_match = re.search(
                                r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", value
                            )
                            if email_match:
                                reviewer_email = email_match.group(1)
                                break
                    if reviewer_email:
                        break

                # Search in patch content if not found in headers
                if not reviewer_email:
                    content = patch.get("content", "")
                    tag_pattern = r"(?:Reviewed-by|Acked-by|Tested-by):\s*(.+?)(?:\n|$)"
                    matches = re.findall(tag_pattern, content, re.IGNORECASE | re.MULTILINE)

                    for value in matches:
                        if reviewer_name.lower() in value.lower():
                            email_match = re.search(r"<([^>]+)>", value)
                            if email_match:
                                reviewer_email = email_match.group(1).strip()
                                break
                            email_match = re.search(
                                r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", value
                            )
                            if email_match:
                                reviewer_email = email_match.group(1)
                                break

                # Search in comments if still not found
                if not reviewer_email:
                    for comment in comments:
                        comment_content = comment.get('content', '')
                        matches = re.findall(tag_pattern, comment_content, re.IGNORECASE | re.MULTILINE)

                        for value in matches:
                            if reviewer_name.lower() in value.lower():
                                email_match = re.search(r"<([^>]+)>", value)
                                if email_match:
                                    reviewer_email = email_match.group(1).strip()
                                    break
                                email_match = re.search(
                                    r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", value
                                )
                                if email_match:
                                    reviewer_email = email_match.group(1)
                                    break
                        if reviewer_email:
                            break

                # Skip if we couldn't find an email
                if not reviewer_email:
                    continue

                # Check if this is an external reviewer
                reviewer_company = self.dev_db.get_company(reviewer_email)
                if reviewer_company == author_company and author_company is not None:
                    continue  # Skip internal reviewers

                # Get canonical email for deduplication
                canonical_id = self.dev_db.get_canonical_identity(reviewer_email)
                canonical_email_match = re.search(r"<([^>]+)>", canonical_id)
                if canonical_email_match:
                    canonical_email = canonical_email_match.group(1)
                else:
                    canonical_email = reviewer_email

                # Check if reviewer is in ml-stats (unless it's a bot)
                if not self.dev_db.is_bot(reviewer_email):
                    stats_key = self.dev_db._find_in_stats(reviewer_email)
                    if not stats_key:
                        logger.info(
                            "Reviewer %s (%s) not found in ml-stats for series #%d",
                            reviewer_name, reviewer_email, series["id"]
                        )

                # Add or update reviewer data
                if canonical_email not in reviewer_data:
                    reviewer_data[canonical_email] = {
                        'name': reviewer_name,
                        'patches': set(),
                        'sources': set()
                    }
                # If we see a longer/better name, use it
                elif len(reviewer_name) > len(reviewer_data[canonical_email]['name']):
                    reviewer_data[canonical_email]['name'] = reviewer_name

                reviewer_data[canonical_email]['patches'].add(patch_id)
                reviewer_data[canonical_email]['sources'].add(source)

        # Categorize reviewers with priority rules:
        # Priority 1: If ANY patch has "comment" source -> reviewer is "comment" at series level
        # Priority 2: Full review (all patches) with "original" only -> "original-full"
        # Priority 3: Partial review -> "partial"

        reviewers_full_comment = []    # Reviewed all patches, at least one via comment
        reviewers_full_original = []   # Reviewed all patches, all in original posts
        reviewers_partial = []         # Reviewed some patches

        for canonical_email, data in reviewer_data.items():
            reviewer_name = data['name']
            patch_ids = data['patches']
            sources = data['sources']

            is_full = len(patch_ids) == total_patches
            has_comment = 'comment' in sources

            # Check if this reviewer is a maintainer of modified paths
            reviewer_is_maintainer = self._check_maintainer(canonical_email, modified_paths)
            if reviewer_is_maintainer:
                reviewer_name = f"{reviewer_name} ●"

            if is_full:
                if has_comment:
                    reviewers_full_comment.append(reviewer_name)
                else:
                    reviewers_full_original.append(reviewer_name)
            else:
                reviewers_partial.append(reviewer_name)

        # Sort reviewer lists
        reviewers_full_comment.sort()
        reviewers_full_original.sort()
        reviewers_partial.sort()

        # Aggregate commenters (people who commented without review tags) at series level
        # Track commenters who commented on at least one patch without providing tags
        # IMPORTANT: Exclude anyone who has review tags anywhere (reviewers have priority)
        all_commenters = set()
        for patch_data in patches_data:
            all_commenters.update(patch_data["commenters"])

        # Build set of all reviewer names (normalized for comparison)
        all_reviewer_names = set()
        for reviewer_name in (reviewers_full_comment + reviewers_full_original + reviewers_partial):
            # Remove the maintainer marker (●) if present for comparison
            clean_name = reviewer_name.replace(" ●", "").strip().lower()
            all_reviewer_names.add(clean_name)

        # Filter out commenters who are also reviewers (reviewers have priority)
        series_commenters = []
        for commenter in all_commenters:
            clean_commenter = commenter.strip().lower()
            if clean_commenter not in all_reviewer_names:
                series_commenters.append(commenter)

        series_commenters.sort()

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

        # Check if author is a maintainer
        author_is_maintainer = False
        if author_email:
            author_is_maintainer = self._check_maintainer(author_email, modified_paths)

        # Mark author name with large dot if maintainer
        if author_is_maintainer:
            author_name = f"{author_name} ●"

        # Find all previous versions of this series
        prev_versions = self._find_previous_versions(series)
        prev_versions_data = []

        for prev_series in prev_versions:
            # Get lore URL for this previous version
            prev_lore_url = prev_series.get("list_archive_url")
            if not prev_lore_url:
                # Try cover letter
                prev_cover = self.state.get_cover_letter(prev_series["id"])
                if prev_cover:
                    prev_lore_url = prev_cover.get("list_archive_url")
                # If still no URL, try first patch
                if not prev_lore_url:
                    prev_patches = self.state.get_series_patches(prev_series["id"])
                    if prev_patches:
                        prev_lore_url = prev_patches[0].get("list_archive_url")

            if prev_lore_url:
                prev_versions_data.append({
                    "version": prev_series.get("version", 1),
                    "lore_url": prev_lore_url
                })

        return {
            "id": series["id"],
            "title": series.get("name") or "No title",
            "version": series.get("version", 1),
            "prev_versions": prev_versions_data,  # List of {version, lore_url}
            "author": author_name,
            "author_company": author_company,
            "date": date_normalized,
            "age_weekday_hours": age_breakdown["weekday_hours"],
            "age_weekend_hours": age_breakdown["weekend_hours"],
            "age_total_hours": age_breakdown["total_hours"],
            "score": series_score.score,
            "is_inactive": is_inactive,
            "state": series_state,
            "patches": patches_data,
            "delegates": delegates_in_series,
            "reviewers_full_comment": reviewers_full_comment,     # All patches, at least one via comment
            "reviewers_full_original": reviewers_full_original,   # All patches, all in original posts
            "reviewers_partial": reviewers_partial,               # Reviewed some patches
            "commenters": series_commenters,
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
        default=None,
        help="Polling interval in seconds (overrides config file)",
    )

    args = parser.parse_args()

    # Create application
    app = SuieApp(args.config)

    # Initialize state
    app.initialize()

    if args.init_only:
        logger.info("Initialization complete, exiting")
        return

    # Determine poll interval: CLI arg > config file > default (300)
    poll_interval = args.poll_interval
    if poll_interval is None:
        poll_interval = app.config.get("polling", {}).get("interval", 300)

    # Run continuous polling
    app.run_continuous(poll_interval=poll_interval)


if __name__ == "__main__":
    main()
