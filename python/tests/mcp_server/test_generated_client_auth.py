"""Generated VPN clients must preserve the service-auth boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOKEN_PLACEHOLDER = "${CORTEX_MCP_AUTH_TOKEN}"


def test_claude_setup_scripts_register_secret_backed_header_after_positionals():
    for relative in (
        "cortexSetup.sh",
        "integrations/claude-code/setup/cortexSetup.sh",
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert TOKEN_PLACEHOLDER in content
        command = content.split("if claude mcp add", 1)[1].split("; then", 1)[0]
        assert command.index('cortex "$MCP_URL"') < command.index("--header")
        assert "X-Cortex-Service-Token" in command


def test_windows_setup_registers_secret_backed_header_after_positionals():
    content = (ROOT / "integrations/claude-code/setup/cortexSetup.bat").read_text(
        encoding="utf-8"
    )
    command = next(line for line in content.splitlines() if line.startswith("claude mcp add"))
    assert command.index('cortex "%CORTEX_MCP_URL%/mcp"') < command.index("--header")
    assert TOKEN_PLACEHOLDER in command
    assert "X-Cortex-Service-Token" in command


def test_every_setup_download_uses_runtime_service_token():
    for relative in (
        "cortexSetup.sh",
        "integrations/claude-code/setup/cortexSetup.sh",
        "integrations/claude-code/setup/cortexSetup.bat",
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "CORTEX_MCP_AUTH_TOKEN" in content
        assert "X-Cortex-Service-Token" in content


def test_active_ui_generators_use_vpn_endpoint_and_service_token():
    for relative in (
        "cortex-ui/src/features/mcp/components/McpConfigSection.tsx",
        "cortex-ui/src/features/mcp/components/CortexSetupDownload.tsx",
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "http://172.16.1.230:8051" in content
        assert "X-Cortex-Service-Token" in content
        assert "CORTEX_MCP_AUTH_TOKEN" in content
        assert "https://cortex.persalto.io" not in content


def test_cloudflare_provisioner_never_prints_or_writes_new_service_token():
    content = (ROOT / "integrations/cloudflare/provision-machine.sh").read_text(encoding="utf-8")
    assert "--print-only is retired" not in content  # generic retired-flag rejection is used
    assert "cf-access.env" not in content
    assert "CRED_CONTENT" not in content
    assert "item create --vault Atlas -" in content
