import os
import tempfile
import unittest
from pathlib import Path

from housing_agent.retrieval import retrieve_source


@unittest.skipUnless(
    os.environ.get("RUN_LIVE_TESTS") == "1",
    "set RUN_LIVE_TESTS=1 to exercise an official live endpoint",
)
class LiveSourceTests(unittest.TestCase):
    def test_one_official_datagov_source(self):
        source = {
            "source_id": "live_ura_price",
            "source_type": "datagov_json",
            "retrieval_url": (
                "https://data.gov.sg/api/action/datastore_search?resource_id="
                "d_97f8a2e995022d311c6c68cfda6d034c&limit=5000"
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            result = retrieve_source(source, Path(temporary), max_retries=2)
        self.assertEqual(result.retrieval_status, "success", result.error_message)
        self.assertEqual(len(result.raw_file_sha256 or ""), 64)


if __name__ == "__main__":
    unittest.main()
