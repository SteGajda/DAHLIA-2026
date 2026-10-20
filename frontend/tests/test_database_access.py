"""SQL account requests use the current authenticated API session."""

import asyncio
import json

import httpx

from dahlia.core.api_client import ApiClient


def test_personal_access_requests_use_authentication_and_no_user_id():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"eligible": True})
    client = ApiClient(transport=httpx.MockTransport(handle))
    client.access_token = "session-token"
    assert asyncio.run(client.get_database_access()).success
    assert asyncio.run(client.issue_sql_credentials(" 8.8.8.8 ")).success
    assert requests[0].url.path == "/api/v1/database-access/me"
    assert requests[1].url.path == "/api/v1/database-access/credentials"
    assert json.loads(requests[1].content) == {"client_ipv4": "8.8.8.8"}
    assert all(r.headers["authorization"] == "Bearer session-token" for r in requests)
