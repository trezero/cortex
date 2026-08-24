"""Generated client configuration must preserve every authentication layer."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REQUIRED_PLACEHOLDERS = (
    "${CF_ACCESS_CLIENT_ID}",
    "${CF_ACCESS_CLIENT_SECRET}",
    "${CORTEX_MCP_AUTH_TOKEN}",
)


def test_claude_setup_scripts_register_all_secret_backed_headers():
    for relative in (
        "cortexSetup.sh",
        "integrations/claude-code/setup/cortexSetup.sh",
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        for placeholder in REQUIRED_PLACEHOLDERS:
            assert placeholder in content


def test_cloudflare_provisioner_emits_placeholders_not_literal_mcp_secrets():
    content = (ROOT / "integrations/cloudflare/provision-machine.sh").read_text(encoding="utf-8")
    mcp_section = content.split('MCP_JSON="$(cat <<EOF', 1)[1].split("EOF", 1)[0]

    for placeholder in REQUIRED_PLACEHOLDERS:
        assert f"\\{placeholder}" in mcp_section
    assert '"CF-Access-Client-Secret": "$CSECRET"' not in mcp_section
