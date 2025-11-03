"""Patchwork API client with retry logic and request logging"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


class PatchworkClient:
    """Client for interacting with the Patchwork API"""

    def __init__(self, base_url: str, user_agent: str, requests_log_path: Optional[str] = None):
        """
        Initialize the Patchwork client

        Args:
            base_url: Base URL for the Patchwork API
            user_agent: User agent string to use for requests
            requests_log_path: Path to JSON file for logging requests
        """
        self.base_url = base_url.rstrip('/')
        self.user_agent = user_agent
        self.requests_log_path = requests_log_path
        self.request_log = []

        # Configure session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({'User-Agent': self.user_agent})

    def _log_request(self, url: str, duration: float, count: int, error: Optional[str] = None):
        """Log a request for later analysis"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'url': url,
            'duration_ms': round(duration * 1000, 2),
            'object_count': count,
            'error': error
        }
        self.request_log.append(log_entry)
        logger.debug("Request to %s: %.2fms, %d objects", url, duration*1000, count)

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make a GET request to the API

        Args:
            endpoint: API endpoint (relative to base_url)
            params: Query parameters

        Returns:
            Response JSON data
        """
        url = urljoin(self.base_url + '/', endpoint)
        start_time = time.time()

        try:
            response = self.session.get(url, params=params, timeout=90)
            response.raise_for_status()
            data = response.json()
            duration = time.time() - start_time

            # Count objects in response
            count = len(data) if isinstance(data, list) else 1
            self._log_request(url, duration, count)

            return data
        except Exception as e:
            duration = time.time() - start_time
            self._log_request(url, duration, 0, str(e))
            logger.error("Request to %s failed: %s", url, e)
            raise

    def _get_paginated(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Fetch all pages of a paginated endpoint

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            List of all objects from all pages
        """
        if params is None:
            params = {}

        # Set a reasonable page size
        params.setdefault('per_page', 100)

        results = []
        page = 1

        while True:
            params['page'] = page
            data = self._make_request(endpoint, params)

            if not data:
                break

            results.extend(data)

            # Check if there are more pages
            # Patchwork API returns an empty list when no more results
            if len(data) < params['per_page']:
                break

            page += 1
            time.sleep(0.1)  # Small delay between pages

        return results

    def get_series(self, project: str, since: Optional[str] = None, **kwargs) -> List[Dict]:
        """
        Get series for a project

        Args:
            project: Project ID or linkname
            since: ISO8601 timestamp for filtering (earliest date-time)
            **kwargs: Additional query parameters

        Returns:
            List of series
        """
        params = {'project': project}
        if since:
            params['since'] = since
        params.update(kwargs)

        return self._get_paginated('series', params)

    def get_series_detail(self, series_id: int) -> Dict:
        """Get detailed information about a series"""
        return self._make_request(f'series/{series_id}')

    def get_patches(self, series_id: Optional[int] = None, project: Optional[str] = None,
                   since: Optional[str] = None, **kwargs) -> List[Dict]:
        """
        Get patches, optionally filtered by series or project

        Args:
            series_id: Filter by series ID
            project: Filter by project
            since: ISO8601 timestamp for filtering
            **kwargs: Additional query parameters

        Returns:
            List of patches
        """
        params = {}
        if series_id is not None:
            params['series'] = series_id
        if project is not None:
            params['project'] = project
        if since:
            params['since'] = since
        params.update(kwargs)

        return self._get_paginated('patches', params)

    def get_patch_detail(self, patch_id: int) -> Dict:
        """Get detailed information about a patch"""
        return self._make_request(f'patches/{patch_id}')

    def get_patch_comments(self, patch_id: int) -> List[Dict]:
        """Get comments for a patch"""
        return self._get_paginated(f'patches/{patch_id}/comments')

    def get_patch_checks(self, patch_id: int) -> List[Dict]:
        """Get checks for a patch"""
        return self._get_paginated(f'patches/{patch_id}/checks')

    def get_cover_detail(self, cover_id: int) -> Dict:
        """Get detailed information about a cover letter"""
        return self._make_request(f'covers/{cover_id}')

    def get_cover_comments(self, cover_id: int) -> List[Dict]:
        """Get comments for a cover letter"""
        return self._get_paginated(f'covers/{cover_id}/comments')

    def get_events(self, project: str, since: Optional[str] = None,
                   category: Optional[str] = None, **kwargs) -> List[Dict]:
        """
        Get events for a project

        Server-side filtering with 'since' is slow, so we filter locally instead:
        - Only send project filter to the API
        - Paginate through events until we reach events older than 'since'
        - Return only events that are newer than 'since'

        Args:
            project: Project ID or linkname
            since: ISO8601 timestamp for filtering (applied locally)
            category: Event category to filter by
            **kwargs: Additional query parameters

        Returns:
            List of events after the 'since' timestamp
        """
        params = {'project': project}
        if category:
            params['category'] = category
        params.update(kwargs)

        # Set page size
        params.setdefault('per_page', 100)

        results = []
        page = 1

        # Parse the since timestamp if provided
        since_dt = None
        if since:
            try:
                from datetime import datetime
                if since.endswith("Z"):
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                else:
                    since_dt = datetime.fromisoformat(since)
                logger.debug("Filtering events locally for events after %s", since)
            except (ValueError, AttributeError) as e:
                logger.warning("Failed to parse since timestamp '%s': %s", since, e)

        while True:
            params['page'] = page
            data = self._make_request('events', params)

            if not data:
                break

            # Filter events locally based on timestamp
            if since_dt:
                page_results = []
                stop_pagination = False

                for event in data:
                    event_date_str = event.get('date')
                    if event_date_str:
                        try:
                            if event_date_str.endswith("Z"):
                                event_dt = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
                            else:
                                event_dt = datetime.fromisoformat(event_date_str)

                            # Check if event is after the since timestamp
                            if event_dt > since_dt:
                                page_results.append(event)
                            else:
                                # Event is older than since, stop pagination
                                logger.debug("Reached event older than since date (event: %s, since: %s), stopping pagination",
                                           event_date_str, since)
                                stop_pagination = True
                                break
                        except (ValueError, AttributeError):
                            # If we can't parse the date, include the event
                            page_results.append(event)
                    else:
                        # No date field, include the event
                        page_results.append(event)

                results.extend(page_results)

                if stop_pagination:
                    logger.debug("Stopped pagination at page %d, found %d events total", page, len(results))
                    break
            else:
                # No since filter, include all events
                results.extend(data)

            # Check if there are more pages
            if len(data) < params['per_page']:
                break

            page += 1
            time.sleep(0.1)  # Small delay between pages

        logger.debug("Fetched %d events for project %s", len(results), project)
        return results

    def save_request_log(self):
        """
        Save the request log to disk (appending to existing entries).
        If the file reaches 10,000 entries, rotate it to a dated backup file.
        """
        if not self.requests_log_path or not self.request_log:
            return

        try:
            # Load existing entries if file exists
            existing_entries = []
            if os.path.exists(self.requests_log_path):
                try:
                    with open(self.requests_log_path, 'r', encoding='utf-8') as f:
                        existing_entries = json.load(f)
                    if not isinstance(existing_entries, list):
                        logger.warning("Request log file is not a list, resetting")
                        existing_entries = []
                except json.JSONDecodeError:
                    logger.warning("Request log file is corrupted, resetting")
                    existing_entries = []

            # Append new entries
            all_entries = existing_entries + self.request_log

            # Check if rotation is needed (10,000 entries threshold)
            if len(all_entries) >= 10000:
                # Rotate the log to a dated file
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                backup_path = self.requests_log_path.replace('.json', f'_{timestamp}.json')

                # Save all entries to the backup file
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump(all_entries, f, indent=2)
                logger.info("Rotated request log to %s (%d entries)", backup_path, len(all_entries))

                # Reset to empty for the main file
                all_entries = []

            # Save to main file
            with open(self.requests_log_path, 'w', encoding='utf-8') as f:
                json.dump(all_entries, f, indent=2)

            logger.debug("Saved %d new request log entries (total: %d)",
                        len(self.request_log), len(all_entries))

            # Clear the in-memory log after saving
            self.request_log = []

        except Exception as e:
            logger.error("Failed to save request log: %s", e)
