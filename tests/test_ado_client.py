import os
import unittest
from unittest.mock import Mock, call, patch

import requests

from clients.ado_client import AdoClient, AdoClientError


class AdoClientConfigurationTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "ADO_ORGANIZATION": "example-org",
            "PAT": "example-pat",
        },
        clear=True,
    )
    def test_loads_connection_settings_from_environment(self) -> None:
        client = AdoClient()

        self.assertEqual(client.config.organization, "example-org")

    @patch.dict(os.environ, {"PAT": "example-pat"}, clear=True)
    def test_reports_missing_organization(self) -> None:
        with self.assertRaisesRegex(ValueError, "ADO_ORGANIZATION"):
            AdoClient()

    @patch.dict(
        os.environ,
        {"ADO_ORGANIZATION": "example-org", "PAT": "example-pat"},
        clear=True,
    )
    def test_get_pr_uses_organization_scoped_endpoint(self) -> None:
        client = AdoClient()
        response = Mock(
            ok=True,
            content=b"{}",
            json=Mock(return_value={"pullRequestId": 123}),
        )
        client.session.request = Mock(return_value=response)

        self.assertEqual(client.get_pr(123), {"pullRequestId": 123})
        client.session.request.assert_called_once_with(
            method="GET",
            url="https://dev.azure.com/example-org/_apis/git/pullrequests/123",
            params={"api-version": "7.1"},
            json=None,
            timeout=30,
        )

    @patch.dict(
        os.environ,
        {"ADO_ORGANIZATION": "example-org", "PAT": "example-pat"},
        clear=True,
    )
    def test_request_returns_raw_response(self) -> None:
        client = AdoClient()
        response = Mock(ok=True)
        client.session.request = Mock(return_value=response)

        self.assertIs(client._request("GET", "_apis/example"), response)
        response.json.assert_not_called()

    @patch.dict(
        os.environ,
        {"ADO_ORGANIZATION": "example-org", "PAT": "example-pat"},
        clear=True,
    )
    def test_request_json_wraps_invalid_json(self) -> None:
        client = AdoClient()
        response = Mock(
            ok=True,
            content=b"not json",
            url="https://dev.azure.com/example-org/_apis/example",
        )
        response.json.side_effect = requests.exceptions.JSONDecodeError(
            "Invalid JSON",
            "not json",
            0,
        )
        client.session.request = Mock(return_value=response)

        with self.assertRaisesRegex(AdoClientError, "invalid JSON"):
            client._request_json("GET", "_apis/example")

    @patch.dict(
        os.environ,
        {"ADO_ORGANIZATION": "example-org", "PAT": "example-pat"},
        clear=True,
    )
    def test_get_pr_diff_uses_context_from_each_pull_request(self) -> None:
        client = AdoClient()
        first_pr = {
            "repository": {
                "id": "first-repo",
                "project": {"id": "first-project-id", "name": "First Project"},
            }
        }
        second_pr = {
            "repository": {
                "id": "second-repo",
                "project": {"id": "second-project-id", "name": "Second Project"},
            }
        }
        iterations = {
            "value": [
                {
                    "id": 1,
                    "targetRefCommit": {"commitId": "base"},
                    "sourceRefCommit": {"commitId": "source"},
                }
            ]
        }

        with patch.object(
            client,
            "_request_json",
            side_effect=[
                first_pr,
                iterations,
                {"changeEntries": []},
                second_pr,
                iterations,
                {"changeEntries": []},
            ],
        ) as request:
            self.assertEqual(client.get_pr_diff(123), "")
            self.assertEqual(client.get_pr_diff(456), "")

        self.assertEqual(
            request.call_args_list[1].kwargs["base_url"],
            "https://dev.azure.com/example-org/first-project-id/",
        )
        self.assertIn("first-repo", request.call_args_list[1].args[1])
        self.assertEqual(
            request.call_args_list[4].kwargs["base_url"],
            "https://dev.azure.com/example-org/second-project-id/",
        )
        self.assertIn("second-repo", request.call_args_list[4].args[1])

    @patch.dict(
        os.environ,
        {"ADO_ORGANIZATION": "example-org", "PAT": "example-pat"},
        clear=True,
    )
    def test_get_pr_diff_uses_original_path_for_renamed_file(self) -> None:
        client = AdoClient()
        pull_request = {
            "repository": {
                "id": "example-repo",
                "project": {"id": "example-project"},
            }
        }
        iterations = {
            "value": [
                {
                    "id": 1,
                    "targetRefCommit": {"commitId": "base"},
                    "sourceRefCommit": {"commitId": "source"},
                }
            ]
        }
        changes = {
            "changeEntries": [
                {
                    "changeType": "rename",
                    "originalPath": "/old.py",
                    "item": {"path": "/new.py"},
                }
            ]
        }

        with (
            patch.object(
                client,
                "_request_json",
                side_effect=[pull_request, iterations, changes],
            ),
            patch.object(
                client,
                "_get_file_content",
                side_effect=["old\n", "new\n"],
            ) as get_file_content,
        ):
            diff = client.get_pr_diff(123)

        self.assertIn("--- a/old.py", diff)
        self.assertIn("+++ b/new.py", diff)
        self.assertEqual(
            get_file_content.call_args_list,
            [
                call(
                    path="/old.py",
                    commit="base",
                    project_url="https://dev.azure.com/example-org/example-project/",
                    repository_path="_apis/git/repositories/example-repo",
                ),
                call(
                    path="/new.py",
                    commit="source",
                    project_url="https://dev.azure.com/example-org/example-project/",
                    repository_path="_apis/git/repositories/example-repo",
                ),
            ],
        )

    @patch.dict(
        os.environ,
        {"ADO_ORGANIZATION": "example-org", "PAT": "example-pat"},
        clear=True,
    )
    def test_get_pr_diff_preserves_empty_file_path(self) -> None:
        client = AdoClient()
        pull_request = {
            "repository": {
                "id": "example-repo",
                "project": {"id": "example-project"},
            }
        }
        iterations = {
            "value": [
                {
                    "id": 1,
                    "targetRefCommit": {"commitId": "base"},
                    "sourceRefCommit": {"commitId": "source"},
                }
            ]
        }
        changes = {
            "changeEntries": [
                {
                    "changeType": "edit",
                    "item": {"path": "/empty.py"},
                }
            ]
        }

        with (
            patch.object(
                client,
                "_request_json",
                side_effect=[pull_request, iterations, changes],
            ),
            patch.object(
                client,
                "_get_file_content",
                side_effect=["", "content\n"],
            ),
        ):
            diff = client.get_pr_diff(123)

        self.assertIn("--- a/empty.py", diff)
        self.assertIn("+++ b/empty.py", diff)

    @patch.dict(
        os.environ,
        {"ADO_ORGANIZATION": "example-org", "PAT": "example-pat"},
        clear=True,
    )
    def test_context_manager_closes_session(self) -> None:
        client = AdoClient()
        client.session.close = Mock()

        with client as entered_client:
            self.assertIs(entered_client, client)

        client.session.close.assert_called_once_with()

    def test_get_pr_context_requires_project_and_repository(self) -> None:
        with self.assertRaisesRegex(AdoClientError, "repository and project metadata"):
            AdoClient._get_pr_context({})


if __name__ == "__main__":
    unittest.main()
