"""Replace placeholder Playwright asset with bundled OrangeHRM E2E suite."""
import asyncio
import os
import uuid

from app.db.session import AsyncSessionLocal
from app.services.automation import AutomationService
from app.services.e2e_bundle import load_orangehrm_e2e_files


async def main() -> None:
    project_id = uuid.UUID("be157118-6293-48b2-a3c4-5a982d833b27")
    base_url = os.environ.get("BASE_URL", "https://example.com")

    async with AsyncSessionLocal() as db:
        svc = AutomationService(db)
        assets = await svc.list_assets(project_id)
        if not assets:
            print("No assets found")
            return
        asset = assets[0]
        files = load_orangehrm_e2e_files(base_url)
        asset.files = files
        asset.status = "ready"
        asset.version += 1
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(asset, "files")
        await db.commit()
        print(f"Updated asset {asset.name} v{asset.version} with {len(files)} E2E files")


if __name__ == "__main__":
    asyncio.run(main())
