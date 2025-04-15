The web UI is losing the port number when navigating between pages in the `python-mcp-server` application. This is because the application is not aware of the original host and port used by the client.

**Problem:**

The `src/web_routes.py` file uses `request.url_for()` to generate URLs for redirects and form actions. However, the application is not properly configured to use the `X-Forwarded-Host` header, which contains the original host and port requested by the client. As a result, `request.url_for()` is defaulting to the standard HTTPS port (443) when generating URLs.

The `src/config.py` file defines the application settings, but it does not include any logic to explicitly set the base URL based on the `X-Forwarded-Host` header.

**Solution:**

1.  **Modify `src/config.py` (in `python-mcp-server`):**

    *   Add a new setting to store the base URL. This setting should be initialized with a default value (e.g., `DOMAIN_NAME`).
    *   Update the setting based on the `X-Forwarded-Host` header. This can be done by creating a middleware that reads the `X-Forwarded-Host` header and updates the setting accordingly.

2.  **Modify `src/web_routes.py` (in `python-mcp-server`):**

    *   Update the `request.url_for()` calls to use the base URL from the settings. This will ensure that the generated URLs include the correct host and port.

**Example Code (Conceptual):**

**src/config.py (in `python-mcp-server`):**

```python
class Settings(BaseSettings):
    # ... other settings ...
    DOMAIN_NAME = os.environ.get("DOMAIN_NAME", "crawl4ai.my.domain")
    BASE_URL: str = DOMAIN_NAME # Default to domain name

settings = Settings()
```

**Middleware (Conceptual - Example for FastAPI in `python-mcp-server`):**

```python
from fastapi import Request

async def set_base_url(request: Request, call_next):
    x_forwarded_host = request.headers.get("x-forwarded-host")
    if x_forwarded_host:
        settings.BASE_URL = f"https://{x_forwarded_host}"  # Or http:// if X-Forwarded-Proto is http
    response = await call_next(request)
    return response
```

**src/web_routes.py (in `python-mcp-server`):**

```python
from src.config import settings

@router.get(...)
async def some_route(request: Request):
    # Use settings.BASE_URL when generating URLs
    redirect_url = f"{settings.BASE_URL}/some/path"
    return RedirectResponse(redirect_url)
```

**Important Considerations:**

*   Ensure that the middleware is properly registered in the FastAPI application.
*   Handle the case where the `X-Forwarded-Host` header is not present.
*   Consider the security implications of trusting the `X-Forwarded-Host` header. You may want to restrict the allowed proxy IPs.
