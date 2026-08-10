from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp import server_runtime
from diptrace_mcp.config import Settings


class _FindingsStore:
    def read(self, report_id: str) -> Any:
        return SimpleNamespace(document_id="doc", report_id=report_id)


class _TransactionsStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "diff.txt").write_text("diff-body", encoding="utf-8")
        (root / "preview.svg").write_text("<svg/>", encoding="utf-8")
        (root / "preview.json").write_text('{"preview": true}', encoding="utf-8")

    def read(self, txid: str) -> Any:
        return SimpleNamespace(operations=[{"kind": "synthetic", "txid": txid}])

    def diff_path(self, txid: str) -> Path:
        return self.root / "diff.txt"

    def preview_svg_path(self, txid: str) -> Path:
        return self.root / "preview.svg"

    def preview_json_path(self, txid: str) -> Path:
        return self.root / "preview.json"


class _ResourceService:
    instance: _ResourceService | None = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.findings = _FindingsStore()
        self.transactions = _TransactionsStore(settings.state_dir)
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        type(self).instance = self

    def status(self) -> dict[str, Any]:
        return {"ok": True, "status": "synthetic"}

    def get_capabilities(self) -> dict[str, Any]:
        return {"ok": True, "capabilities": "synthetic"}

    def trusted_provenance_registry_report(self) -> dict[str, Any]:
        return {"trusted_entry_count": 0}

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> str:
            self.calls.append((name, args, kwargs))
            return json.dumps({"method": name, "args": [str(item) for item in args]})

        return call


def _render_uri(template: str) -> str:
    replacements = {
        "{document_id}": "doc",
        "{report_id}": "report",
        "{txid}": "tx",
        "{preview_id}": "preview",
        "{plan_id}": "plan",
        "{jobid}": "job",
        "{export_id}": "export",
        "{artifact}": "artifact.txt",
    }
    value = template
    for token, replacement in replacements.items():
        value = value.replace(token, replacement)
    assert "{" not in value
    return value


def test_every_resource_and_prompt_callback_executes_through_fastmcp(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    async def verify() -> None:
        monkeypatch.setattr(server_runtime, "DipTraceService", _ResourceService)
        settings = Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        server = server_runtime.create_server(settings)

        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=10),
        ) as session:
            resources = await session.list_resources()
            assert len(resources.resources) >= 4
            for resource in resources.resources:
                result = await session.read_resource(str(resource.uri))
                assert result.contents

            templates = await session.list_resource_templates()
            assert len(templates.resourceTemplates) >= 20
            for template in templates.resourceTemplates:
                result = await session.read_resource(_render_uri(str(template.uriTemplate)))
                assert result.contents

            prompts = await session.list_prompts()
            assert len(prompts.prompts) >= 10
            for prompt in prompts.prompts:
                arguments = {
                    argument.name: "coverage-probe"
                    for argument in (prompt.arguments or [])
                    if argument.required
                }
                result = await session.get_prompt(prompt.name, arguments)
                assert result.messages
                assert result.messages[0].content.text

        service = _ResourceService.instance
        assert service is not None
        called_names = {name for name, _args, _kwargs in service.calls}
        assert {
            "document_resource",
            "review_resource",
            "findings_resource",
            "transaction_summary_resource",
            "raw_preview_diff_resource",
            "plan_resource",
            "job_resource",
            "export_resource",
        } <= called_names

    asyncio.run(verify())
