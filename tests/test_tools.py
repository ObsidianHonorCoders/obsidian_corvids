import json
import unittest

from tools import AVAILABLE_TOOLS


class DemonstrationToolTests(unittest.TestCase):
    def test_all_tools_are_explicitly_simulated(self):
        outputs = [json.loads(tool()) for tool in AVAILABLE_TOOLS]
        self.assertEqual(len(outputs), 4)
        for output in outputs:
            self.assertIn("SIMULATED", output["data_status"])

    def test_demo_security_and_uptime_are_not_claimed_as_facts(self):
        outputs = {json.loads(tool())["role"]: json.loads(tool()) for tool in AVAILABLE_TOOLS}
        self.assertEqual(outputs["CISO"]["pci_dss_compliance"], "Not assessed")
        self.assertEqual(outputs["CISO"]["active_vulnerabilities"], "Not assessed")
        self.assertEqual(outputs["COO"]["active_infrastructure"], "Not monitored")


if __name__ == "__main__":
    unittest.main()