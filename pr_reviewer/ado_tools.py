from __future__ import annotations

import re
from typing import Literal

from copilot import Tool
from copilot.tools import define_tool
from pydantic import AliasPath, BaseModel, ConfigDict, Field

from pr_reviewer.ado_client import AdoClient


class PullRequestParams(BaseModel):
    pull_request_id: int = Field(
        gt=0,
        description="Positive Azure DevOps pull request identifier.",
    )


class PullRequestDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(validation_alias="pullRequestId")
    title: str
    status: str
    source_branch: str = Field(validation_alias="sourceRefName")
    target_branch: str = Field(validation_alias="targetRefName")
    author: str = Field(validation_alias=AliasPath("createdBy", "displayName"))
    description: str | None = None


class FileChange(BaseModel):
    old_path: str | None
    new_path: str | None
    change_type: Literal["added", "deleted", "modified", "renamed"]
    diff: str


class PullRequestDiff(BaseModel):
    files: list[FileChange]


_DIFF_HEADER = re.compile(
    r"^--- (?P<old_path>[^\r\n]+)\r?\n"
    r"\+\+\+ (?P<new_path>[^\r\n]+)\r?\n"
    r"(?=@@ )",
    re.MULTILINE,
)


def _normalize_diff_path(path: str, prefix: str) -> str | None:
    if path == "/dev/null":
        return None
    return path.removeprefix(prefix)


def _parse_pull_request_diff(diff: str) -> PullRequestDiff:
    matches = list(_DIFF_HEADER.finditer(diff))

    if diff and not matches:
        raise ValueError("Azure DevOps returned an unrecognized unified diff.")

    files: list[FileChange] = []
    for index, match in enumerate(matches):
        old_path = _normalize_diff_path(match.group("old_path"), "a")
        new_path = _normalize_diff_path(match.group("new_path"), "b")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(diff)

        if old_path is None:
            change_type = "added"
        elif new_path is None:
            change_type = "deleted"
        elif old_path != new_path:
            change_type = "renamed"
        else:
            change_type = "modified"

        files.append(
            FileChange(
                old_path=old_path,
                new_path=new_path,
                change_type=change_type,
                diff=diff[match.start() : end],
            )
        )

    return PullRequestDiff(files=files)


def create_ado_tools(ado_client: AdoClient) -> list[Tool]:
    @define_tool(
        description=(
            "Get essential metadata for an Azure DevOps pull request, including "
            "its title, description, status, source and target branches, and author. "
            "Use this to understand the purpose and state of a PR."
        ),
        skip_permission=True,
    )
    def get_pr_details(params: PullRequestParams) -> PullRequestDetails:
        response = ado_client.get_pr(params.pull_request_id)
        return PullRequestDetails.model_validate(response)

    @define_tool(
        description=(
            "Get the complete diff for an Azure DevOps pull request, organized "
            "by file and including added, deleted, and modified lines. Use this "
            "when you need to inspect the actual code changes in a PR."
        ),
        skip_permission=True,
    )
    def get_pr_diff(params: PullRequestParams) -> PullRequestDiff:
        diff = ado_client.get_pr_diff(pull_request_id=params.pull_request_id)
        return _parse_pull_request_diff(diff)

    return [get_pr_details, get_pr_diff]
