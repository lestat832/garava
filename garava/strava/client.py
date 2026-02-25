"""Strava API client wrapper using stravalib."""

from __future__ import annotations

import logging

from stravalib import Client

from garava.models import StravaToken

logger = logging.getLogger(__name__)


class StravaClient:
    """Client for Strava API using stravalib."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._client = Client()

    def set_access_token(self, token: StravaToken) -> None:
        """Set the access token for authenticated requests."""
        self._client.access_token = token.access_token

    @property
    def client(self) -> Client:
        """Get the underlying stravalib Client."""
        return self._client

    def get_authorization_url(self, redirect_uri: str, state: str | None = None) -> str:
        """Generate OAuth2 authorization URL.

        Args:
            redirect_uri: Callback URL for OAuth flow
            state: CSRF protection state parameter

        Returns:
            URL to redirect user to for authorization
        """
        return self._client.authorization_url(
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            scope=["activity:read_all", "activity:write"],
            state=state,
        )

    def exchange_code(self, code: str) -> StravaToken:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            StravaToken with access and refresh tokens
        """
        response = self._client.exchange_code_for_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            code=code,
        )

        token = StravaToken(
            access_token=response["access_token"],
            refresh_token=response["refresh_token"],
            expires_at=response["expires_at"],
            athlete_id=response.get("athlete", {}).get("id"),
        )

        self._client.access_token = token.access_token
        logger.info(f"Exchanged code for token, athlete_id: {token.athlete_id}")
        return token

    def refresh_token(self, refresh_token: str) -> StravaToken:
        """Refresh an expired access token.

        Args:
            refresh_token: The refresh token from previous auth

        Returns:
            New StravaToken with fresh access token
        """
        response = self._client.refresh_access_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=refresh_token,
        )

        token = StravaToken(
            access_token=response["access_token"],
            refresh_token=response["refresh_token"],
            expires_at=response["expires_at"],
        )

        self._client.access_token = token.access_token
        logger.info("Refreshed Strava access token")
        return token

    def get_athlete(self) -> dict:
        """Get the authenticated athlete's profile."""
        athlete = self._client.get_athlete()
        return {
            "id": athlete.id,
            "username": athlete.username,
            "firstname": athlete.firstname,
            "lastname": athlete.lastname,
        }
