"""Custom error handlers for the panelsh application."""

import logging
from typing import Optional

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


def permission_denied_view(
    request: HttpRequest, exception: Optional[Exception] = None
) -> HttpResponse:
    """Return a friendly 403 page for permission errors."""
    logger.warning(
        "Permission denied", extra={"path": request.path, "method": request.method}
    )
    return render(
        request,
        "403.html",
        {
            "path": request.path,
        },
        status=403,
    )


def page_not_found_view(
    request: HttpRequest, exception: Optional[Exception] = None
) -> HttpResponse:
    """Return a friendly 404 page and log the missing path."""
    logger.warning(
        "Page not found",
        extra={
            "path": request.path,
            "method": request.method,
            "referer": request.META.get("HTTP_REFERER"),
        },
    )
    return render(
        request,
        "404.html",
        {
            "path": request.path,
        },
        status=404,
    )
