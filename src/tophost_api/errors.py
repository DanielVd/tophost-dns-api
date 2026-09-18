from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RECORD_TYPE = "INVALID_RECORD_TYPE"

    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    AMBIGUOUS_RECORD = "AMBIGUOUS_RECORD"
    RECORD_ALREADY_EXISTS = "RECORD_ALREADY_EXISTS"
    RECORD_CHANGED = "RECORD_CHANGED"

    DOMAIN_NOT_FOUND = "DOMAIN_NOT_FOUND"
    AMBIGUOUS_DOMAIN = "AMBIGUOUS_DOMAIN"

    AUTH_FAILED = "AUTH_FAILED"
    OTP_REQUIRED = "OTP_REQUIRED"
    OTP_CHALLENGE_NOT_FOUND = "OTP_CHALLENGE_NOT_FOUND"
    OTP_INVALID = "OTP_INVALID"
    TRUST_EXPIRED = "TRUST_EXPIRED"

    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_PROTOCOL_ERROR = "UPSTREAM_PROTOCOL_ERROR"
    UPSTREAM_RESPONSE_CHANGED = "UPSTREAM_RESPONSE_CHANGED"


class TophostAPIError(Exception):
    code = ErrorCode.UPSTREAM_PROTOCOL_ERROR
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        retryable: bool | None = None,
    ):
        super().__init__(message)

        if code is not None:
            self.code = code

        if retryable is not None:
            self.retryable = retryable

    def as_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": str(self),
            "retryable": self.retryable,
        }


class AuthenticationError(TophostAPIError):
    code = ErrorCode.AUTH_FAILED


class OTPRequiredError(TophostAPIError):
    code = ErrorCode.OTP_REQUIRED


class OTPChallengeNotFoundError(TophostAPIError):
    code = ErrorCode.OTP_CHALLENGE_NOT_FOUND


class OTPInvalidError(TophostAPIError):
    code = ErrorCode.OTP_INVALID


class RecordNotFoundError(TophostAPIError):
    code = ErrorCode.RECORD_NOT_FOUND


class AmbiguousRecordError(TophostAPIError):
    code = ErrorCode.AMBIGUOUS_RECORD


class RecordChangedError(TophostAPIError):
    code = ErrorCode.RECORD_CHANGED


class UpstreamUnavailableError(TophostAPIError):
    code = ErrorCode.UPSTREAM_UNAVAILABLE
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        reason: str = "upstream_unavailable",
    ):
        super().__init__(message)
        self.reason = reason


class UpstreamProtocolError(TophostAPIError):
    code = ErrorCode.UPSTREAM_PROTOCOL_ERROR


class DomainNotFoundError(TophostAPIError):
    code = ErrorCode.DOMAIN_NOT_FOUND


class AmbiguousDomainError(TophostAPIError):
    code = ErrorCode.AMBIGUOUS_DOMAIN
