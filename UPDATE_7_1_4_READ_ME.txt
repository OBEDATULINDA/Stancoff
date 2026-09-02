STANCOFF / MOTHERS HARVEST UPDATE 7.1.4

Purpose:
- Ensures Edit/Delete actions are visible on existing and new commercial records.
- Files in this ZIP are at repository root (app.py, templates/, static/, etc.), not inside a Stancoff-main wrapper folder.
- Adds visible “Mothers Harvest v7.1.4” marker to commercial list pages.
- Adds Render startup log marker: === STANCOFF RELEASE 7.1.4 LOADED ===

Deployment:
1. Extract this ZIP.
2. Copy the CONTENTS into the ROOT of the GitHub repository, replacing matching files.
3. Commit changes.
4. Render redeploys.
5. Confirm Render log contains: === STANCOFF RELEASE 7.1.4 LOADED ===
6. Open /commercial/suppliers and confirm page shows Mothers Harvest v7.1.4.

Do not delete or recreate PostgreSQL.
