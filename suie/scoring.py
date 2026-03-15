"""Scoring system for ranking patches and series"""

import importlib.util
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple


logger = logging.getLogger(__name__)


@dataclass
class PatchScore:
    """Represents the score and diagnostic information for a patch"""
    patch_id: int
    score: float
    comments: List[str] = field(default_factory=list)
    emojis: str = ""

    def add_comment(self, comment: str):
        """Add a diagnostic comment"""
        self.comments.append(comment)


@dataclass
class SeriesScore:
    """Represents the score for a series"""
    series_id: int
    score: float
    patch_scores: List[PatchScore] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    emojis: str = ""


class DeveloperDatabase:
    """Manages developer information, mailmap, and company mappings"""

    def __init__(self, db_path: Optional[str] = None, stats_path: Optional[str] = None):
        """
        Initialize the developer database

        Args:
            db_path: Path to the JSON file with mailmap and corpmap
            stats_path: Path to JSON file or directory containing developer statistics
                       If directory, will load the newest file
        """
        self.mailmap_list: List[List[str]] = []  # list of [pattern, canonical]
        self.corpmap_list: List[List[str]] = []  # list of [pattern, company]
        self.bots: List[str] = []  # list of bot email addresses
        self.stats: Dict = {}  # developer statistics
        self.stats_base_path: Optional[str] = None  # directory or file path for stats
        self.stats_loaded_file: Optional[str] = None  # actual file loaded

        if db_path:
            self._load_database(db_path)
        if stats_path:
            self.stats_base_path = stats_path
            self._load_stats(stats_path)

    def _load_database(self, db_path: str):
        """Load mailmap and corpmap from JSON file"""
        try:
            with open(db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load mailmap: list of [pattern, canonical]
            self.mailmap_list = data.get('mailmap', [])

            # Load corpmap: list of [email_pattern, company]
            # And extend it with mailmap mappings (like ml-stat.py does)
            self.corpmap_list = data.get('corpmap', []).copy()

            # For each mailmap entry, add corpmap entries for the source too
            # This mirrors lines 742-744 in ml-stat.py
            for mailmap_entry in self.mailmap_list:
                mailmap_pattern = mailmap_entry[0]
                mailmap_target = mailmap_entry[1]

                # Check if any corpmap pattern matches the mailmap TARGET
                for corpmap_entry in data.get('corpmap', []):
                    corp_pattern = corpmap_entry[0]
                    company = corpmap_entry[1]

                    if corp_pattern in mailmap_target:
                        # Add mapping for the mailmap SOURCE too
                        self.corpmap_list.append([mailmap_pattern, company])

            # Load bots list
            self.bots = data.get('bots', [])

            logger.info("Loaded %d mailmap entries and %d corpmap entries (expanded to %d), %d bots",
                       len(self.mailmap_list), len(data.get('corpmap', [])),
                       len(self.corpmap_list), len(self.bots))
        except Exception as e:
            logger.error("Failed to load database from %s: %s", db_path, e)

    def _get_newest_file_in_directory(self, directory: str) -> Optional[str]:
        """
        Get the newest file in a directory based on modification time

        Args:
            directory: Directory path

        Returns:
            Path to newest file, or None if directory is empty
        """
        try:
            files = []
            for entry in os.listdir(directory):
                full_path = os.path.join(directory, entry)
                if not os.path.isfile(full_path):
                    continue

                # Try to load as JSON to verify it's a valid JSON file
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        json.load(f)
                    # If load succeeds, add to list
                    files.append(full_path)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Skip files that aren't valid JSON
                    continue

            if not files:
                logger.warning("No valid JSON files found in directory %s", directory)
                return None

            # Sort by modification time, newest first
            files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
            return files[0]

        except Exception as e:
            logger.error("Failed to find newest file in %s: %s", directory, e)
            return None

    def _load_stats(self, stats_path: str):
        """
        Load developer statistics from JSON file or directory

        Args:
            stats_path: Path to JSON file or directory containing JSON files
        """
        try:
            # Check if path is a directory
            if os.path.isdir(stats_path):
                actual_file = self._get_newest_file_in_directory(stats_path)
                if not actual_file:
                    logger.error("No stats files found in directory %s", stats_path)
                    return
                logger.info("Loading stats from newest file in directory: %s",
                           os.path.basename(actual_file))
                stats_file = actual_file
            else:
                stats_file = stats_path

            # Load the stats file
            with open(stats_file, 'r', encoding='utf-8') as f:
                self.stats = json.load(f)

            self.stats_loaded_file = stats_file
            logger.info("Loaded statistics from %s for %d individuals",
                       os.path.basename(stats_file),
                       len(self.stats.get('individual', {})))
        except Exception as e:
            logger.error("Failed to load stats from %s: %s", stats_path, e)

    def check_and_reload_stats(self) -> bool:
        """
        Check if a newer stats file is available and reload if so

        Returns:
            True if stats were reloaded, False otherwise
        """
        if not self.stats_base_path:
            return False

        try:
            # Only check if base path is a directory
            if not os.path.isdir(self.stats_base_path):
                return False

            # Find newest file in directory
            newest_file = self._get_newest_file_in_directory(self.stats_base_path)
            if not newest_file:
                return False

            # Check if it's different from currently loaded file
            if newest_file == self.stats_loaded_file:
                return False

            # New file found - reload stats
            logger.info("New stats file detected: %s (was: %s)",
                       os.path.basename(newest_file),
                       os.path.basename(self.stats_loaded_file) if self.stats_loaded_file else "none")
            self._load_stats(self.stats_base_path)
            return True

        except Exception as e:
            logger.error("Failed to check for new stats file: %s", e)
            return False

    def _apply_mapping(self, identity: str, mapping_list: List[List[str]]) -> str:
        """
        Apply a mapping list to an identity, similar to get_from_mapped() in ml-stat.py

        Args:
            identity: Identity string (e.g., email or "Name <email>")
            mapping_list: List of [pattern, target] pairs

        Returns:
            Mapped identity or original if no match
        """
        # Ensure identity has angle brackets for consistent matching
        if '<' not in identity:
            identity = '<' + identity + '>'

        # Remove quotes for matching
        identity = identity.replace('"', "")

        # Apply all mappings in sequence
        for mapping_entry in mapping_list:
            pattern = mapping_entry[0]
            target = mapping_entry[1]

            if pattern in identity:
                return target

        return identity

    def get_canonical_identity(self, email: str) -> str:
        """
        Get the canonical identity for an email.
        Follows the same logic as get_from_mapped() in ml-stat.py

        Args:
            email: Email address

        Returns:
            Canonical identity or original email if not in mailmap
        """
        return self._apply_mapping(email, self.mailmap_list)

    def get_company(self, email: str) -> Optional[str]:
        """
        Get the company for an email address.
        First applies mailmap, then applies corpmap to the result.

        Args:
            email: Email address

        Returns:
            Company name or None if not found
        """
        # First get canonical identity
        canonical = self.get_canonical_identity(email)

        # Then apply corpmap
        for pattern, company in self.corpmap_list:
            if pattern in canonical or pattern in email:
                return company

        return None

    def _find_in_stats(self, email: str) -> Optional[str]:
        """
        Find an individual in stats by email.
        Stats keys are in "Name <email>" format, but we might only have the email.

        Args:
            email: Email address to search for

        Returns:
            The stats key if found, None otherwise
        """
        individual_stats = self.stats.get('individual', {})

        # First try canonical identity (might be "Name <email>" if in mailmap)
        canonical = self.get_canonical_identity(email)
        if canonical in individual_stats:
            return canonical

        # If not found, try matching by email within the keys
        # Stats keys are in "Name <email>" format
        for key in individual_stats:
            # Extract email from "Name <email>" format
            email_match = re.search(r'<([^>]+)>', key)
            if email_match and email_match.group(1) == email:
                return key
            # Also try direct match if key is just an email
            if key == email:
                return key

        return None

    def get_reviewer_score(self, email: str) -> float:
        """
        Get the reviewer score for an individual

        Args:
            email: Email address

        Returns:
            Reviewer score (higher is better, negative values indicate less experienced reviewers)
        """
        individual_stats = self.stats.get('individual', {})
        stats_key = self._find_in_stats(email)

        if stats_key:
            score_data = individual_stats[stats_key].get('score', {})
            return score_data.get('positive', 0)

        return 0

    def get_posting_count(self, email: str) -> int:
        """
        Get the number of change-sets authored by an individual

        Args:
            email: Email address

        Returns:
            Number of change-sets posted (0 if not found)
        """
        individual_stats = self.stats.get('individual', {})
        stats_key = self._find_in_stats(email)

        if stats_key:
            author_data = individual_stats[stats_key].get('author', {})
            return author_data.get('cs', 0)

        return 0

    def is_bot(self, email: str) -> bool:
        """
        Check if an email address belongs to a bot

        Args:
            email: Email address to check

        Returns:
            True if the email is in the bots list, False otherwise
        """
        # Ensure email has angle brackets for consistent matching
        if '<' not in email:
            email = '<' + email + '>'

        # Check if email matches any bot
        for bot_email in self.bots:
            if bot_email in email or email in bot_email:
                return True

        return False

    def get_company_reviewer_score(self, email: str) -> float:
        """
        Get the reviewer score for a company

        Args:
            email: Email address

        Returns:
            Company reviewer score
        """
        company = self.get_company(email)
        if not company:
            return 0

        corporate_stats = self.stats.get('corporate', {})
        if company in corporate_stats:
            score_data = corporate_stats[company].get('score', {})
            return score_data.get('positive', 0)

        return 0


class ScoringContext:
    """Context object passed to scoring functions"""

    def __init__(self, patch: Dict, series: Dict, all_patches: List[Dict],
                 checks: List[Dict], comments: List[Dict], cover_letter: Optional[Dict],
                 cover_comments: List[Dict], dev_db: DeveloperDatabase,
                 expected_checks: Optional[List[str]] = None,
                 series_age_weekday_hours: float = 0,
                 series_age_weekend_hours: float = 0,
                 time_since_last_comment_hours: Optional[float] = None):
        """
        Initialize the scoring context

        Args:
            patch: Patch data
            series: Series data
            all_patches: All patches in the series
            checks: Checks for this patch
            comments: Comments for this patch
            cover_letter: Cover letter for the series (if any)
            cover_comments: Comments on the cover letter
            dev_db: Developer database
            expected_checks: List of expected check names from configuration
            series_age_weekday_hours: Age of series in weekday hours (excluding weekends)
            series_age_weekend_hours: Age of series in weekend hours
            time_since_last_comment_hours: Hours since most recent comment (None if no comments)
        """
        self.patch = patch
        self.series = series
        self.all_patches = all_patches
        self.checks = checks
        self.comments = comments
        self.cover_letter = cover_letter
        self.cover_comments = cover_comments
        self.dev_db = dev_db

        # Age information for the series
        self.series_age_weekday_hours = series_age_weekday_hours
        self.series_age_weekend_hours = series_age_weekend_hours
        self.series_age_total_hours = series_age_weekday_hours + series_age_weekend_hours

        # Time since last comment
        self.time_since_last_comment_hours = time_since_last_comment_hours

        # Initialize attributes
        self.review_tags = []  # List of (tag_type, email) tuples
        self.review_comments_present = False

        # Process checks: separate expected vs additional, and determine outcomes
        self.expected_checks = expected_checks or []
        # check_name -> outcome (pass/warning/fail/missing)
        self.check_outcomes: Dict[str, str] = {}
        self.additional_checks: List[Dict] = []  # checks not in expected_checks

        # Parse useful information
        self._parse_review_tags()
        self._process_checks()

    def _process_checks(self):
        """Process checks to separate expected from additional and determine outcomes"""
        # Build a map of check context to check data (deduplicated by keeping latest)
        checks_by_context = {}
        for check in self.checks:
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

        # Process expected checks - determine their outcomes
        for check_name in self.expected_checks:
            if check_name in checks_by_context:
                check = checks_by_context[check_name]
                state = check.get('state', 'unknown')
                # Map state to outcome (success -> pass)
                outcome = 'pass' if state == 'success' else state
                self.check_outcomes[check_name] = outcome
            else:
                # Expected check is missing
                self.check_outcomes[check_name] = 'missing'

        # Collect additional checks (not in expected list)
        for context, check in checks_by_context.items():
            if context not in self.expected_checks:
                self.additional_checks.append(check)

    def _parse_review_tags(self):
        """Parse review tags from patch content and comments"""

        # Extract tags from patch headers
        headers = self.patch.get('headers', {})
        self._extract_tags_from_headers(headers)

        # Extract tags from patch content (trailers in commit message)
        content = self.patch.get('content', '')
        self._extract_tags_from_content(content)

        # Track identities of people who left discussion comments (no tags)
        # Use both names and canonical emails for matching
        discussion_commenter_names = set()
        discussion_commenter_emails = set()

        # Check comments for tags
        all_comments = list(self.comments)
        if self.cover_comments:
            all_comments.extend(self.cover_comments)

        for comment in all_comments:
            content = comment.get('content', '')
            self._extract_tags_from_content(content)

            # If this comment has no tags and substantial content,
            # track the submitter as a discussion commenter
            tag_pattern = r'^(?:Reviewed-by|Acked-by|Tested-by):\s*'
            if not re.search(tag_pattern, content, re.IGNORECASE | re.MULTILINE):
                if len(content.strip()) > 50:
                    submitter = comment.get('submitter', {})
                    name = (submitter.get('name') or '').strip().lower()
                    email = (submitter.get('email') or '').strip()
                    if name:
                        discussion_commenter_names.add(name)
                    if email:
                        canonical = self.dev_db.get_canonical_identity(email).lower()
                        discussion_commenter_emails.add(canonical)

        # Check if any discussion commenters are unresolved (didn't provide tags)
        # Match by either name or canonical email
        tag_provider_names = set()
        tag_provider_emails = set()
        tag_name_pattern = r'^(?:Reviewed-by|Acked-by|Tested-by):\s*([^<\n]+)'
        tag_email_pattern = r'^(?:Reviewed-by|Acked-by|Tested-by):\s*[^<\n]*<([^>]+)>'
        for comment in all_comments:
            content = comment.get('content', '')
            name_matches = re.findall(tag_name_pattern, content, re.IGNORECASE | re.MULTILINE)
            if name_matches:
                # Add the comment submitter's identity
                submitter = comment.get('submitter', {})
                name = (submitter.get('name') or '').strip().lower()
                email = (submitter.get('email') or '').strip()
                if name:
                    tag_provider_names.add(name)
                if email:
                    canonical = self.dev_db.get_canonical_identity(email).lower()
                    tag_provider_emails.add(canonical)
                # Add names and emails from the tags themselves
                for tag_name in name_matches:
                    tag_provider_names.add(tag_name.strip().lower())
                email_matches = re.findall(tag_email_pattern, content, re.IGNORECASE | re.MULTILINE)
                for tag_email in email_matches:
                    canonical = self.dev_db.get_canonical_identity(tag_email.strip()).lower()
                    tag_provider_emails.add(canonical)

        # A commenter is resolved if their name OR email matches a tag provider
        unresolved_names = discussion_commenter_names - tag_provider_names
        unresolved_emails = discussion_commenter_emails - tag_provider_emails
        if unresolved_names and unresolved_emails:
            self.review_comments_present = True

    def _extract_tags_from_headers(self, headers: Dict):
        """Extract review tags from email headers"""
        # Common tag headers
        tag_headers = ['Reviewed-by', 'Acked-by', 'Tested-by']

        for tag_type in tag_headers:
            values = headers.get(tag_type, [])
            if not isinstance(values, list):
                values = [values]

            for value in values:
                email = self._extract_email(value)
                if email:
                    self.review_tags.append((tag_type.lower(), email))

    def _extract_tags_from_content(self, content: str):
        """Extract review tags from content"""
        # Pattern to match review tags
        tag_pattern = r'^(Reviewed-by|Acked-by|Tested-by):\s*(.+?)(?:\n|$)'

        matches = re.findall(tag_pattern, content, re.IGNORECASE | re.MULTILINE)

        for tag_type, value in matches:
            email = self._extract_email(value)
            if email:
                self.review_tags.append((tag_type.lower(), email))

    def _extract_email(self, text: str) -> Optional[str]:
        """Extract email address from text"""
        email_pattern = (r'<([^>]+)>|'
                        r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')
        match = re.search(email_pattern, text)
        if match:
            return match.group(1) or match.group(2)
        return None

    def get_author_email(self) -> str:
        """Get the author's email address"""
        submitter = self.patch.get('submitter', {})
        return submitter.get('email', '')

    def get_author_company(self) -> Optional[str]:
        """Get the author's company"""
        return self.dev_db.get_company(self.get_author_email())

    def get_author_reviewer_score(self) -> float:
        """Get the reviewer score for the author"""
        return self.dev_db.get_reviewer_score(self.get_author_email())

    def get_author_company_reviewer_score(self) -> float:
        """Get the company reviewer score for the author"""
        return self.dev_db.get_company_reviewer_score(self.get_author_email())

    def get_author_postings(self) -> int:
        """Get the number of change-sets the author has posted"""
        return self.dev_db.get_posting_count(self.get_author_email())

    def get_external_review_tags(self) -> List[Tuple[str, str]]:
        """
        Get review tags from people not in the same company as the author

        Returns:
            List of (tag_type, email) tuples
        """
        author_company = self.get_author_company()
        external_tags = []

        for tag_type, email in self.review_tags:
            reviewer_company = self.dev_db.get_company(email)
            if reviewer_company != author_company or author_company is None:
                external_tags.append((tag_type, email))

        return external_tags

    def has_external_reviews(self) -> bool:
        """Check if patch has external reviews (tags or comments)"""
        return len(self.get_external_review_tags()) > 0 or self.review_comments_present

    def get_check_status(self, context: str) -> Optional[str]:
        """
        Get the status of a specific check

        Args:
            context: Check context name

        Returns:
            Check state (pending, success, warning, fail) or None if not found
        """
        for check in self.checks:
            if check.get('context') == context:
                return check.get('state')
        return None

    def get_failed_checks(self) -> List[Dict]:
        """Get all failed checks"""
        return [c for c in self.checks if c.get('state') in ['fail', 'warning']]

    def get_missing_checks(self, expected_checks: List[str]) -> List[str]:
        """
        Get list of expected checks that are missing

        Args:
            expected_checks: List of expected check context names

        Returns:
            List of missing check names
        """
        present_checks = {c.get('context') for c in self.checks}
        return [c for c in expected_checks if c not in present_checks]


class ScoringEngine:
    """Engine for scoring patches and series"""

    def __init__(self, module_path: str, function_name: str, dev_db: DeveloperDatabase):
        """
        Initialize the scoring engine

        Args:
            module_path: Path to the Python module containing the scoring function
            function_name: Name of the scoring function
            dev_db: Developer database
        """
        self.dev_db = dev_db
        self.scoring_function = self._load_scoring_function(module_path, function_name)

    def _load_scoring_function(self, module_path: str, function_name: str) -> Callable:
        """Load the scoring function from a Python module"""
        try:
            spec = importlib.util.spec_from_file_location("scoring_module", module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load module from {module_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, function_name):
                raise AttributeError(f"Module does not have function '{function_name}'")

            scoring_func = getattr(module, function_name)
            logger.info("Loaded scoring function '%s' from %s",
                       function_name, module_path)
            return scoring_func

        except Exception as e:
            logger.error("Failed to load scoring function: %s", e)
            raise

    def score_patch(self, patch: Dict, series: Dict, all_patches: List[Dict],
                   checks: List[Dict], comments: List[Dict], cover_letter: Optional[Dict],
                   cover_comments: List[Dict], expected_checks: Optional[List[str]] = None,
                   series_age_weekday_hours: float = 0,
                   series_age_weekend_hours: float = 0,
                   time_since_last_comment_hours: Optional[float] = None) -> PatchScore:
        """
        Score a single patch

        Args:
            patch: Patch data
            series: Series data
            all_patches: All patches in the series
            checks: Checks for this patch
            comments: Comments for this patch
            cover_letter: Cover letter (if any)
            cover_comments: Comments on cover letter
            expected_checks: List of expected check names from configuration
            series_age_weekday_hours: Age of series in weekday hours (excluding weekends)
            series_age_weekend_hours: Age of series in weekend hours

        Returns:
            PatchScore object
        """
        context = ScoringContext(patch, series, all_patches, checks, comments,
                               cover_letter, cover_comments, self.dev_db, expected_checks,
                               series_age_weekday_hours, series_age_weekend_hours,
                               time_since_last_comment_hours)

        # Create a score object that the scoring function can populate
        patch_score = PatchScore(patch_id=patch['id'], score=0.0)

        try:
            # Call the scoring function
            score_value = self.scoring_function(context, patch_score)

            # Use returned score if provided, otherwise use patch_score.score
            if score_value is not None:
                patch_score.score = float(score_value)

        except Exception as e:
            logger.error("Error scoring patch %d: %s", patch['id'], e)
            patch_score.score = float('inf')  # Push to bottom
            patch_score.add_comment(f"Scoring error: {e}")

        return patch_score

    def score_series(self, series: Dict, patches: List[Dict], checks_map: Dict[int, List[Dict]],
                    comments_map: Dict[int, List[Dict]], cover_letter: Optional[Dict],
                    cover_comments: List[Dict], expected_checks: Optional[List[str]] = None,
                    series_age_weekday_hours: float = 0,
                    series_age_weekend_hours: float = 0,
                    time_since_last_comment_hours: Optional[float] = None) -> SeriesScore:
        """
        Score a series (score is the maximum of all patch scores)

        Args:
            series: Series data
            patches: List of patches in the series
            checks_map: Map of patch_id -> checks
            comments_map: Map of patch_id -> comments
            cover_letter: Cover letter (if any)
            cover_comments: Comments on cover letter
            expected_checks: List of expected check names from configuration
            series_age_weekday_hours: Age of series in weekday hours (excluding weekends)
            series_age_weekend_hours: Age of series in weekend hours
            time_since_last_comment_hours: Hours since most recent comment (None if no comments)

        Returns:
            SeriesScore object
        """
        series_score = SeriesScore(series_id=series['id'], score=0.0)

        # Score each patch
        for patch in patches:
            patch_id = patch['id']
            checks = checks_map.get(patch_id, [])
            comments = comments_map.get(patch_id, [])

            patch_score = self.score_patch(patch, series, patches, checks, comments,
                                          cover_letter, cover_comments, expected_checks,
                                          series_age_weekday_hours, series_age_weekend_hours,
                                          time_since_last_comment_hours)
            series_score.patch_scores.append(patch_score)

        # Series score is the maximum (worst) patch score
        if series_score.patch_scores:
            series_score.score = max(ps.score for ps in series_score.patch_scores)
        else:
            series_score.score = float('inf')  # No patches, push to bottom

        # Aggregate unique emojis from all patch scores (preserving order)
        seen = set()
        all_emojis = []
        for ps in series_score.patch_scores:
            for ch in ps.emojis:
                if ch not in seen:
                    seen.add(ch)
                    all_emojis.append(ch)
        series_score.emojis = ''.join(all_emojis)

        return series_score
