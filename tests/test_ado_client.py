import os
import unittest
from unittest.mock import Mock, patch

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
    def test_get_pr_diff_uses_context_from_each_pull_request(self) -> None:
        client = AdoClient()
        first_pr = {
            "repository": {
                "id": "first-repo",
                "project": {"name": "First Project"},
            }
        }
        second_pr = {
            "repository": {
                "id": "second-repo",
                "project": {"name": "Second Project"},
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
            "_request",
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
            "https://dev.azure.com/example-org/First%20Project/",
        )
        self.assertIn("first-repo", request.call_args_list[1].args[1])
        self.assertEqual(
            request.call_args_list[4].kwargs["base_url"],
            "https://dev.azure.com/example-org/Second%20Project/",
        )
        self.assertIn("second-repo", request.call_args_list[4].args[1])

    def test_get_pr_context_requires_project_and_repository(self) -> None:
        with self.assertRaisesRegex(AdoClientError, "repository and project metadata"):
            AdoClient._get_pr_context({})


if __name__ == "__main__":
    unittest.main()
