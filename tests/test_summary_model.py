"""Quick-changes panel rows. Qt-free, so this runs headless without PySide6."""

import unittest
from pathlib import Path

from compare_tool.qtviewer.summary_model import summary_sections
from compare_tool.scanner import scan

FIX = Path(__file__).parent / 'fixtures'


class TestSummarySections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sections = dict(summary_sections(scan(FIX / 'old', FIX / 'new')))
        cls.model = dict(summary_sections(scan(FIX / 'model_old', FIX / 'model_new')))

    def test_updated_files_section_is_gone(self):
        # the folder tree already lists every changed file, so the panel no
        # longer restates them -- it opens straight at the semantic changes
        self.assertNotIn('Updated ARXML / A2L files', self.sections)

    def test_port_interfaces_carry_sign_kind_and_file(self):
        rows = self.sections['Port interfaces']
        added = next(r for r in rows if r.sign == '+')
        self.assertEqual(added.name, '/Interfaces/If_Torque')
        self.assertEqual(added.detail, 'SENDER-RECEIVER')
        self.assertTrue(added.rel.endswith('.arxml'))
        self.assertTrue(any(r.sign == '−' for r in rows))

    def test_a2l_objects_listed_with_kind(self):
        rows = self.sections['A2L variables']
        self.assertIn(('+', 'VehSpd', 'MEASUREMENT'),
                      {(r.sign, r.name, r.detail) for r in rows})

    def test_behaviour_sections_from_the_model_fixtures(self):
        ports = self.model['Ports']
        self.assertIn('+', {r.sign for r in ports})
        self.assertTrue(any(r.name == 'Ctrl.Out2' for r in ports))
        events = self.model['Events']
        changed = next(r for r in events if r.sign == '~')
        self.assertIn('→', changed.detail)
        self.assertTrue(any(r.name == 'Rte_Write_Out2_Diag'
                            for r in self.model['RTE access points']))

    def test_no_changes_gives_no_sections(self):
        self.assertEqual(summary_sections(scan(FIX / 'old', FIX / 'old')), [])

    def test_every_row_points_at_a_real_file(self):
        results = scan(FIX / 'old', FIX / 'new')
        for _title, rows in summary_sections(results):
            for row in rows:
                self.assertIn(row.rel, results)


if __name__ == '__main__':
    unittest.main()
