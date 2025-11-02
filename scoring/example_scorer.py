"""
Example scoring function for Suie

This function demonstrates how to score patches based on various criteria.
Lower scores mean higher priority (patches are sorted ascending by score).

The scoring function receives:
- context: ScoringContext object with all patch/series information
- patch_score: PatchScore object to populate with diagnostic comments

You can return the score directly, or set patch_score.score and return None.
"""


def score_patch(context, patch_score):
    """
    Score a patch based on readiness to be applied

    Args:
        context: ScoringContext with patch, series, checks, comments, etc.
                 context.check_outcomes: Dict mapping expected check names to outcomes
                                        (pass/warning/fail/missing)
                 context.additional_checks: List of checks not in expected_checks config

        patch_score: PatchScore object where you can add diagnostic comments

    Returns:
        float: Score value (lower = higher priority)
    """
    score = 0.0

    # Check 1: Process expected checks from configuration
    # context.check_outcomes contains the outcome for each expected check
    missing_checks = []
    failed_checks = []
    warning_checks = []

    for check_name, outcome in context.check_outcomes.items():
        if outcome == 'missing':
            missing_checks.append(check_name)
            score += 100
        elif outcome == 'fail':
            failed_checks.append(check_name)
            score += 200
        elif outcome == 'warning':
            warning_checks.append(check_name)
            score += 50

    if missing_checks:
        patch_score.add_comment(f"Missing checks: {', '.join(missing_checks)}")

    if failed_checks:
        patch_score.add_comment(f"Failed checks: {', '.join(failed_checks)}")

    if warning_checks:
        patch_score.add_comment(f"Warning checks: {', '.join(warning_checks)}")

    # Check additional checks (not in expected_checks config)
    # These are provided as a list of check dictionaries
    if context.additional_checks:
        additional_failed = [c['context'] for c in context.additional_checks
                           if c.get('state') in ['fail', 'warning']]
        if additional_failed:
            score += 50  # Penalty for unexpected check failures
            patch_score.add_comment(f"Additional checks failed: {', '.join(additional_failed)}")

    # Check 2: Patches with external reviews have lower score (higher priority)
    external_reviews = context.get_external_review_tags()

    if len(external_reviews) >= 2:
        # Has multiple reviews from different people/companies
        score -= 300
        patch_score.add_comment(f"Has {len(external_reviews)} external reviews - ready")
    elif len(external_reviews) == 1:
        # Has one review
        score -= 150
        patch_score.add_comment("Has 1 external review")
    elif context.review_comments_present:
        # Has review comments but no tags yet
        score -= 50
        patch_score.add_comment("Has review feedback")
    else:
        # No reviews yet
        score += 100
        patch_score.add_comment("No reviews yet")

    # Check 3: Author reputation affects score
    author_score = context.get_author_reviewer_score()

    if author_score > 3000:
        # Very experienced author
        score -= 100
        patch_score.add_comment("Experienced author")
    elif author_score > 1000:
        # Experienced author
        score -= 50
        patch_score.add_comment("Regular author")
    elif author_score < 0:
        # New or less experienced author - may need more review
        score += 50
        patch_score.add_comment("New author - needs attention")

    # Check 4: Company backing
    company_score = context.get_author_company_reviewer_score()

    if company_score > 5000:
        # Strong company backing
        score -= 50
        patch_score.add_comment("Strong company backing")

    # Check 5: Patch state
    state = context.patch.get('state', '').lower()

    if state in ['accepted', 'rejected']:
        # Terminal states - push to bottom
        score += 10000
        patch_score.add_comment(f"Terminal state: {state}")
    elif state == 'superseded':
        score += 5000
        patch_score.add_comment("Superseded by newer version")
    elif state == 'new':
        # New patches might need attention
        pass
    elif state == 'under-review':
        # Being actively reviewed
        score -= 25
        patch_score.add_comment("Under active review")

    # Check 6: Archived patches
    if context.patch.get('archived', False):
        score += 10000
        patch_score.add_comment("Archived")

    return score
