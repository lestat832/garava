"""Strava OAuth2 authentication flow."""

from __future__ import annotations

import http.server
import logging
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass

from garava.database import Database
from garava.models import StravaToken
from garava.strava.client import StravaClient

logger = logging.getLogger(__name__)

DEFAULT_REDIRECT_URI = "http://localhost:8000/callback"


@dataclass
class AuthResult:
    """Result of OAuth authorization."""

    success: bool
    token: StravaToken | None = None
    error: str | None = None


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    authorization_code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        """Handle GET request (OAuth callback)."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.authorization_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this window.</p></body></html>"
            )
        elif "error" in params:
            OAuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h1>Authorization failed</h1>"
                f"<p>{OAuthCallbackHandler.error}</p></body></html>".encode()
            )
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging."""
        pass


def run_oauth_flow(
    strava_client: StravaClient,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    timeout: int = 120,
) -> AuthResult:
    """Run interactive OAuth2 authorization flow.

    Opens a browser for user to authorize, starts local server to receive callback.

    Args:
        strava_client: StravaClient instance with client_id/secret
        redirect_uri: Callback URL (must match Strava app settings)
        timeout: Seconds to wait for user authorization

    Returns:
        AuthResult with token or error
    """
    # Reset handler state
    OAuthCallbackHandler.authorization_code = None
    OAuthCallbackHandler.error = None

    # Parse redirect URI to get port
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or 8000

    # Start callback server
    server = http.server.HTTPServer(("localhost", port), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.daemon = True
    server_thread.start()

    # Open browser for authorization
    auth_url = strava_client.get_authorization_url(redirect_uri)
    logger.info(f"Opening browser for Strava authorization...")
    print(f"\nIf browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    start_time = time.time()
    while server_thread.is_alive() and (time.time() - start_time) < timeout:
        time.sleep(0.5)

    server.server_close()

    # Check result
    if OAuthCallbackHandler.error:
        return AuthResult(success=False, error=OAuthCallbackHandler.error)

    if not OAuthCallbackHandler.authorization_code:
        return AuthResult(success=False, error="Authorization timed out")

    # Exchange code for token
    try:
        token = strava_client.exchange_code(OAuthCallbackHandler.authorization_code)
        return AuthResult(success=True, token=token)
    except Exception as e:
        return AuthResult(success=False, error=str(e))


def ensure_valid_token(
    db: Database,
    strava_client: StravaClient,
) -> StravaToken | None:
    """Ensure we have a valid (non-expired) Strava token.

    Refreshes the token if it's expired.

    Args:
        db: Database for token storage
        strava_client: StravaClient for token refresh

    Returns:
        Valid StravaToken or None if no token exists
    """
    token = db.get_strava_token()

    if token is None:
        logger.warning("No Strava token found. Run 'garava setup' to authorize.")
        return None

    # Check if token is expired or expiring soon
    if token.is_expired():
        logger.info("Strava token expired, refreshing...")
        try:
            token = strava_client.refresh_token(token.refresh_token)
            db.save_strava_token(token)
            logger.info("Token refreshed successfully")
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return None

    strava_client.set_access_token(token)
    return token
