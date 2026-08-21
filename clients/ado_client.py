# ado_client.py

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()


class AdoClientError(Exception):
    """Raised when an Azure DevOps API request fails."""


@dataclass(frozen=True)
class AdoConfig:
    """Azure DevOps connection configuration."""

    organization: str
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
        *,
        pat: str | None = None,
        api_version: str = "7.1",
        timeout: int = 30,
    ) -> None:
        organization = organization or os.getenv("ADO_ORGANIZATION")

        if not organization:
            raise ValueError(
                "Azure DevOps organization not found. Set ADO_ORGANIZATION "
                "in the .env file or pass organization explicitly."
            )

        self.config = AdoConfig(
            organization=organization,
            api_version=api_version,
        )

        self.timeout = timeout
        self.pat = pat or os.getenv("PAT")

        if not self.pat:
            raise ValueError(
                "Azure DevOps PAT not found. Set PAT in the .env file or pass pat explicitly."
            )

        self.base_url = f"https://dev.azure.com/{self.config.organization}/"

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
        *,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        url = f"{base_url or self.base_url}{path}"

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

    @staticmethod
    def _get_pr_context(pull_request: dict[str, Any]) -> tuple[str, str]:
        repository = pull_request.get("repository")
        project = repository.get("project") if isinstance(repository, dict) else None

        repository_id = repository.get("id") if isinstance(repository, dict) else None
        project_name = project.get("name") if isinstance(project, dict) else None
        project_id = project.get("id") if isinstance(project, dict) else None

        if not repository_id or not (project_name or project_id):
            raise AdoClientError(
                "Pull request details did not include repository and project metadata."
            )

        return str(project_name or project_id), str(repository_id)

    # ------------------------------------------------------------------
    # Pull Request
    # ------------------------------------------------------------------

    def get_pr(self, pull_request_id: int) -> dict[str, Any]:
        """Get complete metadata for a pull request."""

        return self._request(
            "GET",
            f"_apis/git/pullrequests/{pull_request_id}",
        )

    def get_pr_diff(self, pull_request_id: int) -> str:
        """Return a unified diff for all files changed in the latest PR iteration."""

        pull_request = self.get_pr(pull_request_id)
        project, repository_id = self._get_pr_context(pull_request)
        project_url = f"{self.base_url}{quote(project, safe='')}/"
        repository_path = f"_apis/git/repositories/{repository_id}"

        iterations = self._request(
            "GET",
            f"{repository_path}/pullRequests/{pull_request_id}/iterations",
            base_url=project_url,
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
            f"{repository_path}"
            f"/pullRequests/{pull_request_id}"
            f"/iterations/{iteration_id}/changes",
            params={"$top": 2000},
            base_url=project_url,
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
                    project_url=project_url,
                    repository_path=repository_path,
                )

            if change_type != "delete":
                new_content = self._get_file_content(
                    path=path,
                    commit=target_commit,
                    project_url=project_url,
                    repository_path=repository_path,
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
        project_url: str,
        repository_path: str,
    ) -> str:
        """Get a file's text content at a specific commit."""

        response = self.session.get(
            f"{project_url}{repository_path}/items",
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
