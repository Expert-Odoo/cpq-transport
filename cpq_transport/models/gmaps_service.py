# -*- coding: utf-8 -*-
"""Google Routes API — Compute Route Matrix service.

Utility class (not an Odoo model). Isolated so it can be mocked in tests.

Uses the modern Routes API (`routes.googleapis.com`) — the legacy Distance
Matrix API (`maps.googleapis.com/maps/api/distancematrix`) is deprecated by
Google.
"""
import json
import logging
import urllib.request

_logger = logging.getLogger(__name__)

ENDPOINT = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
FIELD_MASK = "originIndex,destinationIndex,duration,distanceMeters,status,condition"
TIMEOUT = 10


class GoogleMapsService:
    """Wrapper around Google Routes API — Compute Route Matrix."""

    @classmethod
    def get_distance_km(cls, origin, destination, api_key):
        """Compute driving distance between two free-form addresses.

        Args:
            origin (str): free-form origin address.
            destination (str): free-form destination address.
            api_key (str): Google Cloud API key with Routes API enabled.

        Returns:
            tuple: (distance_km: float|None, status: str, error_msg: str|None)
                status is 'OK' or one of:
                'ZERO_RESULTS', 'OVER_QUERY_LIMIT', 'REQUEST_DENIED',
                'INVALID_REQUEST', 'NETWORK_ERROR', 'MISSING_KEY'.
        """
        if not api_key:
            return (None, "MISSING_KEY", "Google Routes API key is not configured.")
        if not origin or not destination:
            return (None, "INVALID_REQUEST", "Origin and destination are required.")

        body = {
            "origins": [{"waypoint": {"address": origin}}],
            "destinations": [{"waypoint": {"address": destination}}],
            "travelMode": "DRIVE",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
            "User-Agent": "Odoo-cpq_transport/1.0",
        }
        _logger.info(
            "GoogleRoutes distance query: %s -> %s", origin, destination
        )
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return cls._map_http_error(e)
        except Exception as e:  # pylint: disable=broad-except
            _logger.warning("GoogleRoutes network error: %s", e)
            return (None, "NETWORK_ERROR", str(e))

        # Global error object (rare — most errors come as HTTPError)
        if isinstance(payload, dict) and payload.get("error"):
            err = payload["error"]
            return (None, err.get("status") or "UNKNOWN", err.get("message"))

        # Successful responses are a JSON array of matrix elements
        if not isinstance(payload, list) or not payload:
            return (None, "ZERO_RESULTS", "Empty response from Routes API.")

        element = payload[0]
        # Element-level status (google.rpc.Status: code 0 = OK)
        elem_status = element.get("status") or {}
        code = elem_status.get("code")
        if code and code != 0:
            return (
                None,
                "INVALID_REQUEST",
                elem_status.get("message") or "Route element error.",
            )

        condition = element.get("condition")
        if condition != "ROUTE_EXISTS":
            return (None, "ZERO_RESULTS", condition or "No route found.")

        meters = element.get("distanceMeters")
        if meters is None:
            return (None, "ZERO_RESULTS", "No distance value in response.")
        return (round(meters / 1000.0, 2), "OK", None)

    @staticmethod
    def _map_http_error(http_error):
        """Map an HTTPError from Routes API to our internal status codes."""
        code = http_error.code
        try:
            body = http_error.read().decode("utf-8")
            payload = json.loads(body)
            msg = payload.get("error", {}).get("message") or body
        except Exception:  # pylint: disable=broad-except
            msg = str(http_error)
        _logger.warning("GoogleRoutes HTTP %s: %s", code, msg)
        if code in (401, 403):
            return (None, "REQUEST_DENIED", msg)
        if code == 429:
            return (None, "OVER_QUERY_LIMIT", msg)
        if code == 400:
            return (None, "INVALID_REQUEST", msg)
        return (None, "NETWORK_ERROR", "HTTP %s: %s" % (code, msg))


AUTOCOMPLETE_ENDPOINT = "https://places.googleapis.com/v1/places:autocomplete"
AUTOCOMPLETE_FIELD_MASK = "suggestions.placePrediction.text,suggestions.placePrediction.placeId"


class GooglePlacesService:
    """Wrapper around Google Places API (New) — autocomplete."""

    @classmethod
    def autocomplete(cls, query, api_key, language="fr"):
        """Suggest addresses matching the query.

        Args:
            query (str): partial address the user is typing.
            api_key (str): Google Cloud API key with Places API (New) enabled.
            language (str): BCP-47 language code (default: "fr").

        Returns:
            tuple: (suggestions: list[dict], status: str, error_msg: str|None)
                suggestions is a list of {"text": str, "place_id": str}.
        """
        if not api_key:
            return ([], "MISSING_KEY", "Google Places API key is not configured.")
        if not query or len(query.strip()) < 3:
            return ([], "OK", None)

        body = {
            "input": query,
            "languageCode": language,
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": AUTOCOMPLETE_FIELD_MASK,
            "User-Agent": "Odoo-cpq_transport/1.0",
        }
        req = urllib.request.Request(
            AUTOCOMPLETE_ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                msg = err_body.get("error", {}).get("message") or str(e)
            except Exception:  # pylint: disable=broad-except
                msg = str(e)
            _logger.warning("GooglePlaces HTTP %s: %s", e.code, msg)
            if e.code in (401, 403):
                return ([], "REQUEST_DENIED", msg)
            if e.code == 429:
                return ([], "OVER_QUERY_LIMIT", msg)
            return ([], "NETWORK_ERROR", msg)
        except Exception as e:  # pylint: disable=broad-except
            _logger.warning("GooglePlaces network error: %s", e)
            return ([], "NETWORK_ERROR", str(e))

        suggestions = []
        for item in payload.get("suggestions") or []:
            pred = item.get("placePrediction") or {}
            text = (pred.get("text") or {}).get("text")
            place_id = pred.get("placeId")
            if text:
                suggestions.append({"text": text, "place_id": place_id})
        return (suggestions, "OK", None)
