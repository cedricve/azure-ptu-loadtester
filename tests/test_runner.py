import asyncio
import json

from aiohttp import web

from azure_ptu_loadtester.config import EndpointConfig
from azure_ptu_loadtester.reports import write_reports
from azure_ptu_loadtester.runner import RunOptions, run_comparison


async def test_comparison_sends_equal_paced_load_and_writes_redacted_reports(tmp_path):
    requests = []

    async def handle_request(request):
        requests.append(
            {
                "key": request.headers.get("api-key"),
                "version": request.query.get("api-version"),
                "body": await request.json(),
            }
        )
        await asyncio.sleep(0.005)
        return web.json_response(
            {"usage": {"prompt_tokens": 5, "completion_tokens": 1}}
        )

    application = web.Application()
    application.router.add_post("/chat/completions", handle_request)
    server = web.AppRunner(application)
    await server.setup()
    site = web.TCPSite(server, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    endpoints = (
        EndpointConfig("model-a", f"http://127.0.0.1:{port}/chat/completions", "key-a", "a", "v1"),
        EndpointConfig(
            "model-b",
            f"http://127.0.0.1:{port}/chat/completions",
            "key-b",
            "b",
            "v2",
            "max_completion_tokens",
        ),
    )
    options = RunOptions(
        rps=20,
        duration_seconds=0.11,
        prompt="test prompt",
        max_tokens=8,
        timeout_seconds=1,
        max_concurrency=2,
    )

    try:
        runs = await run_comparison(endpoints, options)
    finally:
        await server.cleanup()

    assert [len(run.results) for run in runs] == [3, 3]
    assert all(result.success for run in runs for result in run.results)
    assert {request["key"] for request in requests} == {"key-a", "key-b"}
    assert {request["version"] for request in requests} == {"v1", "v2"}
    assert {request["body"]["model"] for request in requests} == {"a", "b"}
    request_bodies = {request["body"]["model"]: request["body"] for request in requests}
    assert request_bodies["a"]["max_tokens"] == 8
    assert "max_completion_tokens" not in request_bodies["a"]
    assert request_bodies["b"]["max_completion_tokens"] == 8
    assert "max_tokens" not in request_bodies["b"]

    json_path, csv_path = write_reports(runs, options, tmp_path / "results")
    report_text = json_path.read_text()
    report = json.loads(report_text)
    assert "key-a" not in report_text
    assert "key-b" not in report_text
    assert "test prompt" not in report_text
    assert report["endpoints"][0]["summary"]["succeeded"] == 3
    assert len(csv_path.read_text().splitlines()) == 7