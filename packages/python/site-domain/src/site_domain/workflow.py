"""Editorial workflow state machine (docs/10_EDITORIAL_WORKFLOW.md §1).

`ARTICLE_STATUSES` is the full set of valid `site_article.status` values.
`ALLOWED_TRANSITIONS` enumerates every allowed `(from, to)` pair; any pair
not listed is forbidden (e.g. `published -> draft` without a new version).
"""

from __future__ import annotations

RECEIVED = "received"
PROCESSING = "processing"
DRAFT = "draft"
DUPLICATE_CANDIDATE = "duplicate_candidate"
REJECTED_AS_IRRELEVANT = "rejected_as_irrelevant"
NEEDS_REVIEW = "needs_review"
APPROVED = "approved"
SCHEDULED = "scheduled"
PUBLISHING = "publishing"
PUBLISHED = "published"
CORRECTED = "corrected"
UNPUBLISHED = "unpublished"
ARCHIVED = "archived"

ARTICLE_STATUSES: frozenset[str] = frozenset(
    {
        RECEIVED,
        PROCESSING,
        DRAFT,
        DUPLICATE_CANDIDATE,
        REJECTED_AS_IRRELEVANT,
        NEEDS_REVIEW,
        APPROVED,
        SCHEDULED,
        PUBLISHING,
        PUBLISHED,
        CORRECTED,
        UNPUBLISHED,
        ARCHIVED,
    }
)

#: Every allowed (from, to) transition. Anything absent here is forbidden,
#: including `published -> draft` (a correction must go through `corrected`).
ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (RECEIVED, PROCESSING),
        (PROCESSING, DRAFT),
        (PROCESSING, DUPLICATE_CANDIDATE),
        (PROCESSING, REJECTED_AS_IRRELEVANT),
        (DRAFT, NEEDS_REVIEW),
        (DUPLICATE_CANDIDATE, NEEDS_REVIEW),
        (DUPLICATE_CANDIDATE, REJECTED_AS_IRRELEVANT),
        (NEEDS_REVIEW, APPROVED),
        (NEEDS_REVIEW, DRAFT),
        (APPROVED, SCHEDULED),
        (APPROVED, PUBLISHING),
        (SCHEDULED, PUBLISHING),
        (SCHEDULED, APPROVED),
        (PUBLISHING, PUBLISHED),
        (PUBLISHED, CORRECTED),
        (PUBLISHED, UNPUBLISHED),
        (CORRECTED, NEEDS_REVIEW),
        (CORRECTED, PUBLISHED),
        (UNPUBLISHED, ARCHIVED),
        (UNPUBLISHED, NEEDS_REVIEW),
        (REJECTED_AS_IRRELEVANT, ARCHIVED),
        (REJECTED_AS_IRRELEVANT, NEEDS_REVIEW),
    }
)


class InvalidTransitionError(Exception):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(f"transition {current_status!r} -> {target_status!r} is not allowed")
        self.current_status = current_status
        self.target_status = target_status


def ensure_transition_allowed(current_status: str, target_status: str) -> None:
    if (current_status, target_status) not in ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(current_status, target_status)
