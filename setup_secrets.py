"""
One-time setup script: stores the Lakebase URL in the Databricks secret scope.

RoamAI reuses the SAME Lakebase URL secret you set up for Day 2 / Day 3
(scope=database, key=lakebase-url), so you almost certainly don't need to
run this again.

Run this only if:
  - You're in a fresh Databricks workspace
  - The `database/lakebase-url` secret doesn't exist yet
  - Your Lakebase password was rotated

All third-party APIs used by RoamAI (Open-Meteo, Wikipedia) are FREE and
require no API keys, so no other secrets are needed.

Usage:
    python setup_secrets.py
"""

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
import getpass

w = WorkspaceClient()

# Uncomment on first run only, then re-comment
# w.secrets.create_scope(scope="database")

w.secrets.put_secret(
    scope="database",
    key="lakebase-url",
    string_value=getpass.getpass("Paste your Lakebase URL: ")
)

w.secrets.put_acl(
    scope="database",
    principal="users",
    permission=workspace.AclPermission.READ,
)

print("Lakebase URL stored at database/lakebase-url")
