from sanic.exceptions import SanicException
from sanic.exceptions import Unauthorized as SanicUnauthorized

from web_foundation.errors.app.application import ApplicationError


class BaseAuthException(SanicException, ApplicationError):
    error_type: str = "L"
    default_class: int = 1
    default_subclass: int = 999


class InvalidToken(BaseAuthException):
    pass


class AuthenticationFailed(BaseAuthException):
    status_code = 401

    def __init__(self, message="Authentication failed.", **kwargs):
        super().__init__(message, **kwargs)


class ScopesFailed(BaseAuthException):
    status_code = 401

    def __init__(self, message="Authentication failed.", **kwargs):
        super().__init__(message, **kwargs)


class MissingAuthorizationHeader(BaseAuthException):
    status_code = 400

    def __init__(self, message="Authorization header not present.", **kwargs):
        super().__init__(message, **kwargs)


class MissingAuthorizationCookie(BaseAuthException):
    status_code = 400

    def __init__(self, message="Authorization cookie not present.", **kwargs):
        super().__init__(message, **kwargs)


class MissingAuthorizationQueryArg(BaseAuthException):
    status_code = 400

    def __init__(
            self, message="Authorization query argument not present.", **kwargs
    ):
        super().__init__(message, **kwargs)


class InvalidAuthorizationHeader(BaseAuthException):
    status_code = 400

    def __init__(self, message="Authorization header is invalid.", **kwargs):
        super().__init__(message, **kwargs)


class InvalidCustomClaim(BaseAuthException):
    status_code = 500

    def __init__(self, message="Custom claim is invalid.", **kwargs):
        super().__init__(message, **kwargs)


class InvalidCustomClaimError(BaseAuthException):
    status_code = 401

    def __init__(self, message="Custom claim value was not met.", **kwargs):
        super().__init__(message, **kwargs)


class InvalidVerification(BaseAuthException):
    status_code = 500

    def __init__(
            self,
            message="Verifications must be a callable object "
                    "returning a boolean value.",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class InvalidVerificationError(BaseAuthException):
    status_code = 401

    def __init__(self, message="Verifications were not met.", **kwargs):
        super().__init__(message, **kwargs)


class AuthenticateNotImplemented(BaseAuthException):
    status_code = 500

    def __init__(
            self,
            message="Sanic JWT initialized without providing an authenticate "
                    "method.",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class RefreshTokenNotImplemented(BaseAuthException):
    status_code = 500

    def __init__(
            self, message="Refresh tokens have not been enabled.", **kwargs
    ):
        super().__init__(message, **kwargs)


class ScopesNotImplemented(BaseAuthException):
    status_code = 500

    def __init__(
            self,
            message="Scopes have not been enabled. Initialize with "
                    "add_scopes_to_payload to provide scoping.",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class UserSecretNotImplemented(BaseAuthException):
    status_code = 500

    def __init__(
            self, message="User secrets have not been enabled.", **kwargs
    ):
        super().__init__(message, **kwargs)


class MissingRegisteredClaim(BaseAuthException):
    status_code = 500

    def __init__(
            self,
            message="One or more claims have been registered, but your "
                    "extend_payload() method does not supply them. ",
            missing=None,
            **kwargs
    ):
        if missing:  # noqa
            message += str(missing)
        super().__init__(message, **kwargs)


class MeEndpointNotSetup(BaseAuthException):
    status_code = 500

    def __init__(
            self,
            message="/me endpoint has not been setup. Pass retrieve_user if "
                    "you with to proceeed.",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class InvalidRetrieveUserObject(BaseAuthException):
    status_code = 500

    def __init__(
            self,
            message="The retrieve_user method should return either a dict or "
                    "an object with a to_dict or __json__ method.",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class InitializationFailure(BaseAuthException):
    status_code = 500

    def __init__(
            self,
            message="Sanic JWT was not initialized properly. It must be "
                    "instantiated on a sanic.Sanic or sanic.Blueprint "
                    "instance.",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class Unauthorized(BaseAuthException, SanicUnauthorized):
    def __init__(self, message="Auth required.", **kwargs):
        super().__init__(message, scheme="Bearer", **kwargs)


class InvalidClassViewsFormat(BaseAuthException):
    def __init__(
            self,
            message="class_views should follow this format ('<SOME ROUTE>', "
                    "ClassInheritedFromBaseEndpoint)",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class InvalidConfiguration(BaseAuthException):
    def __init__(self, message="", **kwargs):
        message = (
                "An invalid setting was passed to the Sanic JWT "
                "configuration: " + str(message)
        )
        super().__init__(message, **kwargs)


class InvalidPayload(BaseAuthException):
    status_code = 500

    def __init__(self, message="", **kwargs):
        message = (
            "Payload must be a dictionary with a key mapped to "
            "SANIC_JWT_USER_ID"
        )
        super().__init__(message, **kwargs)


class RequiredKeysNotFound(BaseAuthException):
    def __init__(
            self,
            message="You must provide both (valid) SANIC_JWT_PUBLIC_KEY and "
                    "SANIC_JWT_PRIVATE_KEY when using asymmetric "
                    "cryptographic algorithms like RS*, EC* or PS*",
            **kwargs
    ):
        super().__init__(message, **kwargs)


class ProvidedPathNotFound(BaseAuthException):
    def __init__(
            self, message="The Path object given is not a valid file", **kwargs
    ):
        super().__init__(message, **kwargs)


class LoopNotRunning(BaseAuthException):
    def __init__(
            self, message="The asyncio loop is not currently running", **kwargs
    ):
        super().__init__(message, **kwargs)
