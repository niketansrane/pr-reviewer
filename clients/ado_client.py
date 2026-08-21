# ado_client.py

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


class AdoClientError(Exception):
    """Raised when an Azure DevOps API request fails."""


@dataclass(frozen=True)
class AdoConfig:
    """Azure DevOps connection configuration."""

    organization: str
    project: str
    repository_id: str
    api_version: str = "7.1"


class AdoClient:
    """
    Read-only Azure DevOps client for a code review agent.

    Supported operations:
        - get_pr()
        - get_pr_diff()
        - get_file_from_remote_on_target_branch()
        - get_commit_history()
        - get_pr_commits()
        - get_pr_threads()
    """

    def __init__(
        self,
        organization: str | None = None,
        project: str | None = None,
        repository_id: str | None = None,
        *,
        pat: str | None = None,
        api_version: str = "7.1",
        timeout: int = 30,
    ) -> None:
        organization = organization or os.getenv("ADO_ORGANIZATION")
        project = project or os.getenv("ADO_PROJECT")
        repository_id = repository_id or os.getenv("ADO_REPO_ID")

        missing_settings = [
            name
            for name, value in (
                ("ADO_ORGANIZATION", organization),
                ("ADO_PROJECT", project),
                ("ADO_REPO_ID", repository_id),
            )
            if not value
        ]
        if missing_settings:
            raise ValueError(
                "Azure DevOps configuration not found. Set "
                f"{', '.join(missing_settings)} in the .env file or pass the "
                "corresponding values explicitly."
            )

        self.config = AdoConfig(
            organization=organization,
            project=project,
            repository_id=repository_id,
            api_version=api_version,
        )

        self.timeout = timeout
        self.pat = pat or os.getenv("PAT")

        if not self.pat:
            raise ValueError(
                "Azure DevOps PAT not found. Set PAT in the .env file or pass pat explicitly."
            )

        self.base_url = (
            f"https://dev.azure.com/{self.config.organization}/{self.config.project}/"
        )

        self.session = requests.Session()
        self._configure_session()

    def _configure_session(self) -> None:
        credentials = base64.b64encode(f":{self.pat}".encode()).decode()

        self.session.headers.update(
            {
                "Authorization": f"Basic {credentials}",
                "Accept": "application/json",
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        request_params = dict(params or {})
        request_params.setdefault("api-version", self.config.api_version)

        response = self.session.request(
            method=method,
            url=url,
            params=request_params,
            json=json,
            timeout=self.timeout,
        )

        if not response.ok:
            raise AdoClientError(
                f"Azure Devops Request Failed: {response.status_code} {response.reason}\n URL: {response.url}, Response: {response.text[:100]}"
            )

        if not response.content:
            return {}
        return response.json()

    @property
    def repository_path(self) -> str:
        """Return the repository API path."""

        return f"_apis/git/repositories/{self.config.repository_id}"

    # ------------------------------------------------------------------
    # Pull Request
    # ------------------------------------------------------------------

    def get_pr(self, pull_request_id: int) -> dict[str, Any]:
        """
        Get complete metadata for a pull request.
        """

        return self._request(
            "GET",
            f"{self.repository_path}/pullRequests/{pull_request_id}",
        )

    def get_pr_diff(self, pull_request_id: int) -> str:
        """Return a unified diff for all files changed in the latest PR iteration."""

        iterations = self._request(
            "GET",
            f"{self.repository_path}/pullRequests/{pull_request_id}/iterations",
        )

        iteration_list = iterations.get("value", [])

        if not iteration_list:
            raise AdoClientError(
                f"No iterations found for pull request {pull_request_id}"
            )

        latest_iteration = max(
            iteration_list,
            key=lambda iteration: iteration["id"],
        )

        iteration_id = latest_iteration["id"]

        changes = self._request(
            "GET",
            f"{self.repository_path}"
            f"/pullRequests/{pull_request_id}"
            f"/iterations/{iteration_id}/changes",
            params={"$top": 2000},
        )

        change_entries = changes.get("changeEntries", [])

        base_commit = latest_iteration["targetRefCommit"]["commitId"]
        target_commit = latest_iteration["sourceRefCommit"]["commitId"]

        diffs: list[str] = []

        for change in change_entries:
            item = change["item"]

            # Ignore directories.
            if item.get("isFolder", False):
                continue

            path = item["path"]
            change_type = change["changeType"]

            old_content = ""
            new_content = ""

            if change_type != "add":
                old_content = self._get_file_content(
                    path=path,
                    commit=base_commit,
                )

            if change_type != "delete":
                new_content = self._get_file_content(
                    path=path,
                    commit=target_commit,
                )

            diff = unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a{path}" if old_content else "/dev/null",
                tofile=f"b{path}" if new_content else "/dev/null",
            )

            diff_text = "".join(diff)

            if diff_text:
                diffs.append(diff_text)

        return "\n".join(diffs)

    def _get_file_content(
        self,
        *,
        path: str,
        commit: str,
    ) -> str:
        """Get a file's text content at a specific commit."""

        response = self.session.get(
            f"{self.base_url}{self.repository_path}/items",
            params={
                "path": path,
                "versionDescriptor.version": commit,
                "versionDescriptor.versionType": "commit",
                "includeContent": "true",
                "api-version": self.config.api_version,
            },
            timeout=self.timeout,
        )

        if not response.ok:
            raise AdoClientError(
                f"Failed to retrieve file content: "
                f"{response.status_code} {response.reason}\n"
                f"Path: {path}\n"
                f"Commit: {commit}\n"
                f"Response: {response.text[:1000]}"
            )

        data = response.json()

        if data.get("contentMetadata", {}).get("isBinary"):
            return ""

        return data.get("content", "")


if __name__ == "__main__":
    ado_client = AdoClient()
    pr_details = ado_client.get_pr_diff(123)
    print(pr_details)
