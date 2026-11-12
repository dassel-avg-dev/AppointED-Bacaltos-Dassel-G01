from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def _role_required(check):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


student_required = _role_required(lambda u: u.is_student)  # BR-06
faculty_required = _role_required(lambda u: u.is_faculty)  # BR-05, BR-10
