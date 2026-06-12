"""Scanner and migration script distribution endpoints."""

import os

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "cortex-scanner.py")
MIGRATE_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "cortex-migrate.py")
SCANNER_VERSION = "1.0"
MIGRATE_VERSION = "1.0"


@router.get("/script")
async def get_scanner_script():
    """Serve the standalone scanner script for client-side execution."""
    with open(SCRIPT_PATH, "r") as f:
        content = f.read()
    return PlainTextResponse(
        content=content,
        headers={"X-Scanner-Version": SCANNER_VERSION},
    )


@router.get("/migrate-script")
async def get_migrate_script():
    """Serve the migration script for renaming Archon artifacts to Cortex on connected projects."""
    with open(MIGRATE_SCRIPT_PATH, "r") as f:
        content = f.read()
    return PlainTextResponse(
        content=content,
        headers={
            "Content-Disposition": 'attachment; filename="cortex-migrate.py"',
            "X-Migrate-Version": MIGRATE_VERSION,
        },
    )
