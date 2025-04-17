# Implementation Plan: Remove ProxyHeadersMiddleware

This document outlines the steps to safely remove `ProxyHeadersMiddleware` from the project, ensuring continued security and functionality.

---

## 1. Remove the Import Statement

- Delete or comment out the line in `src/main.py` that imports `ProxyHeadersMiddleware`.

## 2. Remove Middleware Registration

- Delete or comment out the line that adds `ProxyHeadersMiddleware` to your FastAPI app:
  ```python
  app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
  ```
- Also remove or update any related log messages.

## 3. Review and Update Documentation

- Update your README or any project documentation to remove references to `ProxyHeadersMiddleware` or proxy header handling at the application level.

## 4. Check for Related Code

- Search for any other code that references proxy headers, `X-Forwarded-For`, or similar logic. Remove or refactor as needed.

## 5. Update Reverse Proxy Configuration (if needed)

- If your application is deployed behind a reverse proxy (e.g., Nginx, Traefik, Caddy), ensure that the proxy is configured to set and trust the appropriate headers (`X-Forwarded-For`, etc.).
- Document this requirement for deployment.

## 6. Test Application Functionality

- Run your application locally and in your deployment environment to ensure that removing the middleware does not affect core functionality.
- Specifically test scenarios where client IP or protocol information is important.

## 7. Code Cleanup

- Remove any now-unused imports or variables.
- Run linting and formatting tools to ensure code quality.

## 8. Commit and Document the Change

- Make a clear commit message, e.g., "Remove ProxyHeadersMiddleware (no longer supported in Starlette 0.46+)".
- Note the change in your project’s changelog or release notes.

---

### Optional: Add TrustedHostMiddleware

If you still want to restrict allowed hosts, consider adding `TrustedHostMiddleware` instead, which is supported in your Starlette version.

---

**This plan is saved for future reference. Resume from here if the session is interrupted.**
