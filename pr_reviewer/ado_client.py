"""Read-only client for the Azure DevOps Git REST API."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any, Self
from urllib.parse import quote

import requests


class AdoClientError(Exception):
    """Raised when an Azure DevOps API request fails."""


@dataclass(frozen=True)
class AdoConfig:
    """Azure DevOps connection configuration."""

    organization: str
    api_version: str = "7.1"


@dataclass(frozen=True)
class FileChange:
    """Paths affected by a pull request change."""

    old_path: str | None
    new_path: str | None


class AdoClient:
    """
    Read-only Azure DevOps client for a code review agent.

    Supported operations are pull-request metadata and unified diff retrieval.
    """

    def __init__(
        self,
        organization: str | None = None,
        *,
        pat: str | None = None,
        api_version: str = "7.1",
        timeout: int = 30,
    ) -> None:
        organization = (organization or os.getenv("ADO_ORGANIZATION", "")).strip()

        if not organization:
            raise ValueError(
                "Azure DevOps organization not found. Set ADO_ORGANIZATION "
                "in the environment or pass organization explicitly."
            )

        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self.config = AdoConfig(
            organization=organization.strip("/"),
            api_version=api_version,
        )
        self.timeout = timeout
        self.pat = pat or os.getenv("ADO_PAT")

        if not self.pat:
            raise ValueError(
                "Azure DevOps PAT not found. Set ADO_PAT in the environment "
                "or pass pat explicitly."
            )

        encoded_organization = quote(self.config.organization, safe="")
        self.base_url = f"https://dev.azure.com/{encoded_organization}/"

        self.session = requests.Session()
        self._configure_session()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self.session.close()

    def get_pr(self, pull_request_id: int) -> dict[str, Any]:
        """Get complete metadata for a pull request."""

        self._validate_pull_request_id(pull_request_id)
        return self._request_json(
            "GET",
            f"_apis/git/pullrequests/{pull_request_id}",
        )

    def get_pr_diff(self, pull_request_id: int) -> str:
        """Return a unified diff for all files changed in the latest PR iteration."""

        self._validate_pull_request_id(pull_request_id)
        pull_request = self.get_pr(pull_request_id)
        project, repository_id = self._get_pr_context(pull_request)
        project_url = f"{self.base_url}{quote(project, safe='')}/"
        repository_path = f"_apis/git/repositories/{repository_id}"

        iterations = self._request_json(
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

        change_entries = self._get_iteration_changes(
            pull_request_id=pull_request_id,
            iteration_id=iteration_id,
            project_url=project_url,
            repository_path=repository_path,
        )

        base_commit = latest_iteration["targetRefCommit"]["commitId"]
        target_commit = latest_iteration["sourceRefCommit"]["commitId"]

        diffs: list[str] = []

        for change in change_entries:
            item = change["item"]

            # Ignore directories.
            if item.get("isFolder", False):
                continue

            file_change = self._parse_file_change(change)

            old_content = ""
            new_content = ""

            if file_change.old_path is not None:
                old_content = self._get_file_content(
                    path=file_change.old_path,
                    commit=base_commit,
                    project_url=project_url,
                    repository_path=repository_path,
                )

            if file_change.new_path is not None:
                new_content = self._get_file_content(
                    path=file_change.new_path,
                    commit=target_commit,
                    project_url=project_url,
                    repository_path=repository_path,
                )

            diff = unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=(
                    f"a{file_change.old_path}"
                    if file_change.old_path is not None
                    else "/dev/null"
                ),
                tofile=(
                    f"b{file_change.new_path}"
                    if file_change.new_path is not None
                    else "/dev/null"
                ),
            )

            diff_text = "".join(diff)

            if diff_text:
                diffs.append(diff_text)

        return "\n".join(diffs)

    def _get_iteration_changes(
        self,
        *,
        pull_request_id: int,
        iteration_id: int,
        project_url: str,
        repository_path: str,
    ) -> list[dict[str, Any]]:
        """Retrieve every page of changes for an iteration."""

        path = (
            f"{repository_path}/pullRequests/{pull_request_id}"
            f"/iterations/{iteration_id}/changes"
        )
        all_changes: list[dict[str, Any]] = []
        skip = 0

        while True:
            page = self._request_json(
                "GET",
                path,
                params={"$top": 2000, "$skip": skip},
                base_url=project_url,
            )
            entries = page.get("changeEntries", [])
            if not isinstance(entries, list):
                raise AdoClientError(
                    "Azure DevOps returned invalid pull request changes."
                )
            all_changes.extend(entries)

            next_skip = page.get("nextSkip")
            if not isinstance(next_skip, int) or next_skip <= skip:
                return all_changes
            skip = next_skip

    @staticmethod
    def _validate_pull_request_id(pull_request_id: int) -> None:
        if pull_request_id <= 0:
            raise ValueError("pull_request_id must be greater than zero")

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
    ) -> requests.Response:
        url = f"{base_url or self.base_url}{path}"

        request_params = dict(params or {})
        request_params.setdefault("api-version", self.config.api_version)

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=request_params,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise AdoClientError(f"Azure DevOps request failed: {url}") from error

        if not response.ok:
            raise AdoClientError(
                "Azure DevOps request failed: "
                f"{response.status_code} {response.reason}\n"
                f"URL: {response.url}\n"
                f"Response: {response.text[:1000]}"
            )

        return response

    def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        *,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            method,
            path,
            params=params,
            json=json,
            base_url=base_url,
        )

        if not response.content:
            return {}

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError as error:
            raise AdoClientError(
                f"Azure DevOps returned invalid JSON for {response.url}"
            ) from error

        if not isinstance(data, dict):
            raise AdoClientError(
                f"Azure DevOps returned unexpected JSON for {response.url}"
            )

        return data

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

        return str(project_id or project_name), str(repository_id)

    @staticmethod
    def _parse_file_change(change: dict[str, Any]) -> FileChange:
        item = change.get("item")
        path = item.get("path") if isinstance(item, dict) else None

        if not path:
            raise AdoClientError("Pull request change did not include a file path.")

        change_types = {
            value.strip().lower()
            for value in str(change.get("changeType", "")).split(",")
        }
        old_path = None if "add" in change_types else path
        new_path = None if "delete" in change_types else path

        if "rename" in change_types:
            old_path = (
                change.get("originalPath") or change.get("sourceServerItem") or old_path
            )

        return FileChange(old_path=old_path, new_path=new_path)

    def _get_file_content(
        self,
        *,
        path: str,
        commit: str,
        project_url: str,
        repository_path: str,
    ) -> str:
        """Get a file's text content at a specific commit."""

        data = self._request_json(
            "GET",
            f"{repository_path}/items",
            params={
                "path": path,
                "versionDescriptor.version": commit,
                "versionDescriptor.versionType": "commit",
                "includeContent": "true",
            },
            base_url=project_url,
        )

        if data.get("contentMetadata", {}).get("isBinary"):
            return ""

        content = data.get("content", "")
        if not isinstance(content, str):
            raise AdoClientError("Azure DevOps returned unexpected file content.")
        return content
