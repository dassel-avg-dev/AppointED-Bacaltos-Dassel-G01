def theme(request):
    """Expose the user's chosen theme (cookie) to templates. Defaults to light."""
    return {"theme": "dark" if request.COOKIES.get("theme") == "dark" else "light"}
