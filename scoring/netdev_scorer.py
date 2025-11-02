"""
Netdev scoring function for Suie

The scoring function receives:
- context: ScoringContext object with all patch/series information
- patch_score: PatchScore object to populate with diagnostic comments
"""

maintainer_group = {
    "Andrew Lunn <andrew@lunn.ch>",
    # DT maintainers, they should really be scoped
    "Rob Herring <robh@kernel.org>",
    "Krzysztof Kozlowski <krzk@kernel.org>",
    "Conor Dooley <conor@kernel.org>",
}

trusted_reviewer_group = {
    "Florian Fainelli <florian.fainelli@broadcom.com>",
    "Russell King <kernel@armlinux.org.uk>",
}

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

    # Application target for perfection is 1 day.
    score = 24

    # Check 1: Process expected checks from configuration
    # context.check_outcomes contains the outcome for each expected check
    missing_checks = []
    failed_checks = []
    warning_checks = []

    for check_name, outcome in context.check_outcomes.items():
        if outcome == 'missing':
            missing_checks.append(check_name)
            score += 24
        elif outcome == 'fail':
            failed_checks.append(check_name)
            score += 12
        elif outcome == 'warning':
            warning_checks.append(check_name)
            score += 3

    if missing_checks:
        patch_score.add_comment(f"Missing checks: {', '.join(missing_checks)}")
    if failed_checks:
        patch_score.add_comment(f"Failed checks: {', '.join(failed_checks)}")
    if warning_checks:
        patch_score.add_comment(f"Warning checks: {', '.join(warning_checks)}")

    # Check additional checks (not in expected_checks config)
    if context.additional_checks:
        additional_failed = [c['context'] for c in context.additional_checks
                           if c.get('state') in ['fail', 'warning']]
        if additional_failed:
            score += 1
            patch_score.add_comment(f"Additional checks failed: {', '.join(additional_failed)}")

    # Check 2: Author reputation affects score
    author_score = context.get_author_reviewer_score()

    if author_score < 0:
        score += 12
        patch_score.add_comment(f"Author score negative ({author_score})")

    # Check 3: Company score
    company_score = context.get_author_company_reviewer_score()

    if company_score < 0:
        score += 24
        patch_score.add_comment(f"Company score negative ({company_score})")

    # Check 4: Reviews
    external_reviews = context.get_external_review_tags()

    approved = False
    for _, email in external_reviews:
        for maint in maintainer_group | trusted_reviewer_group:
            approved |= email in maint

    if approved:
        # No extra wait, ready to go!
        patch_score.add_comment("Approved")
    else:
        # "Normal" reviewers
        score += 24 - 12 * min(len(external_reviews), 2)
        patch_score.add_comment(f"{len(external_reviews)} reviews")

    # Check 6: Comment threads
    if context.review_comments_present:
        score += 48

    return score
