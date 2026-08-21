import os
import unittest
from unittest.mock import patch

from clients.ado_client import AdoClient


class AdoClientConfigurationTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "ADO_ORGANIZATION": "example-org",
            "ADO_PROJECT": "example-project",
            "ADO_REPO_ID": "example-repo",
            "PAT": "example-pat",
        },
        clear=True,
    )
    def test_loads_connection_settings_from_environment(self) -> None:
        client = AdoClient()

        self.assertEqual(client.config.organization, "example-org")
        self.assertEqual(client.config.project, "example-project")
        self.assertEqual(client.config.repository_id, "example-repo")

    @patch.dict(os.environ, {"PAT": "example-pat"}, clear=True)
    def test_reports_all_missing_connection_settings(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ADO_ORGANIZATION, ADO_PROJECT, ADO_REPO_ID",
        ):
            AdoClient()


if __name__ == "__main__":
    unittest.main()
