import sys
from traceback import extract_tb

from sanic.errorpages import exception_response, JSONRenderer
from sanic.handlers import ErrorHandler
from sanic.exceptions import SanicException

from web_foundation.errors.app.application import ApplicationError
from web_foundation import settings


class StatusCodes:
    APPLICATION_CODE = 409
    REPORT_CODE = 501


class ExtJSONRenderer(JSONRenderer):
    def _generate_output(self, *, full):
        output = {
            "description": self.title,
            "status": self.status,
            # "message": self.text,
            "error": getattr(self.exception, "context", {})
        }
        if not output['error'].get('type'):
            output['error']['type'] = getattr(self.exception, "error_type", "C")

        if not output['error'].get('class'):
            output['error']['class'] = getattr(self.exception, "default_class", 999)

        if not output['error'].get('subclass'):
            output['error']['subclass'] = getattr(self.exception, "default_subclass", 999)

        if not output['error'].get('code'):
            output['error'][
                'code'] = f"{output['error']['type']}-{output['error']['class']}-{output['error']['subclass']}"

        if self.text:
            if output.get('error'):
                if not output['error'].get('comment'):
                    output['error'].update({"comment": self.text})
            else:
                output['error'] = {"comment": self.text}

        if full:
            _, exc_value, __ = sys.exc_info()
            exceptions = []

            while exc_value:
                exceptions.append(
                    {
                        "type": exc_value.__class__.__name__,
                        "exception": str(exc_value),
                        "frames": [
                            {
                                "file": frame.filename,
                                "line": frame.lineno,
                                "name": frame.name,
                                "src": frame.line,
                            }
                            for frame in extract_tb(exc_value.__traceback__)
                        ],
                    }
                )
                exc_value = exc_value.__cause__

            output["path"] = self.request.path
            output["args"] = self.request.args
            output["exceptions"] = exceptions[::-1]

        return output


class ExtendedErrorHandler(ErrorHandler):
    def default(self, request, exception):
        """Convert ApplicationError to SanicException"""
        renderer = None
        if isinstance(exception, ApplicationError):
            if not isinstance(exception, SanicException):
                exception = type(exception.__class__.__name__,
                                 (SanicException,),
                                 {"message": exception.message if exception.message else "",
                                  "status_code": StatusCodes.APPLICATION_CODE,
                                  "error_type": exception.error_type,
                                  "default_class": exception.default_class,
                                  "default_subclass": exception.default_subclass, })(context=exception.context)
            renderer = ExtJSONRenderer
        else:
            self.log(request, exception)
        fallback = request.app.config.FALLBACK_ERROR_FORMAT
        return exception_response(
            request,
            exception,
            debug=settings.DEBUG,
            base=self.base,
            fallback=fallback,
            renderer=renderer
        )
