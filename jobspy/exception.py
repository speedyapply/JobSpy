"""Scraper exceptions. All are deprecated: boards log failures instead of raising."""


class LinkedInException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with LinkedIn")


class IndeedException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Indeed")


class ZipRecruiterException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with ZipRecruiter")


class GlassdoorException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Glassdoor")


class GoogleJobsException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Google Jobs")


class BaytException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Bayt")


class NaukriException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Naukri")


class BDJobsException(Exception):
    """Deprecated since 1.2.0: never raised; will be removed in 2.0."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with BDJobs")
