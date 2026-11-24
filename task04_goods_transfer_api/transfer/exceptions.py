"""HTTP exception missing from DRF's built-in set."""

from rest_framework.exceptions import APIException


class Conflict(APIException):
    """A second decision or another invalid lifecycle change (409)."""

    status_code = 409
    default_detail = "The request is in a conflicting state."
    default_code = "conflict"
