"""Machine translation errors — one per thing the person has to do about it.

The split follows the action, not the HTTP code: a wrong key is fixed in
«Preferences», an exhausted quota is waited out, the network is checked, and an
unreadable answer is a reason to retry or to switch providers. A single `MtError`
with a string inside would force every caller to parse that text to know what to
do.

The message is translated **when the error is raised**, not when it is shown: the
core also runs without a window (`--scan-cli`), and there `translate` honestly
returns English.

**The key never reaches the message.** Not the text, not the `repr`, not the log:
exceptions are shown to the user, quoted in bug reports and pasted into chats.
"""
from __future__ import annotations


class MtError(Exception):
    """The common ancestor. Catch this one; tell the descendants apart."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class MtAuthError(MtError):
    """The key was refused: missing, mistyped, revoked, or for another service."""


class MtQuotaError(MtError):
    """The request or volume limit is used up.

    `retry_after` is how many seconds the service allowed before a retry, if it
    said so at all (the `Retry-After` header). Empty means the decision is ours.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class MtNetworkError(MtError):
    """The service was not reached: no network, no DNS answer, or a timeout."""


class MtResponseError(MtError):
    """An answer arrived but cannot be read: not JSON, a field missing, the wrong
    number of rows."""


class MtCancelled(Exception):
    """The user pressed «Interrupt».

    Deliberately not an `MtError`: this is not a failure, and it is handled apart
    — the same way `ScanCancelled` and `TmBuildCancelled` are next door.
    """
