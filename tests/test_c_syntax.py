"""Call inventory regressions reduced from MATLAB R2024a AUTOSAR exports."""

import tempfile
import unittest
from pathlib import Path

from compare_tool.c_syntax import scan_calls
from compare_tool.scanner import scan


class TestCallInventory(unittest.TestCase):
    def test_matlab_pim_stub_definitions_and_storage_are_not_calls(self):
        functions, calls = scan_calls('''#include "Rte_Ctrl.h"
float32 Rte_Pim_Ctrl_Buffer_data;
float32* Rte_Pim_Ctrl_Buffer(void)
{
  return &Rte_Pim_Ctrl_Buffer_data;
}
''')
        self.assertEqual([f['name'] for f in functions], ['Rte_Pim_Ctrl_Buffer'])
        self.assertEqual(calls, [])

    def test_prototypes_do_not_hide_adjacent_real_calls(self):
        _, calls = scan_calls('''#include "Rte_Ctrl.h"
extern Std_ReturnType Rte_Read_Input_Value(float32 *value);
FUNC(void, CODE) Rte_Write_Output_Value(float32 value);
void Ctrl_Step(void) {
  extern void Rte_Call_Service_Reset(void);
  Rte_Read_Input_Value(&value);
  Rte_Write_Output_Value(value);
  Rte_Call_Service_Reset();
}
''')
        rte = [c for c in calls if c.name.startswith('Rte_')]
        self.assertEqual([(c.name, c.line, c.function) for c in rte], [
            ('Rte_Read_Input_Value', 6, 'Ctrl_Step'),
            ('Rte_Write_Output_Value', 7, 'Ctrl_Step'),
            ('Rte_Call_Service_Reset', 8, 'Ctrl_Step'),
        ])

    def test_wrapped_nested_calls_keep_source_positions(self):
        _, calls = scan_calls('''void Ctrl_Step(void)
{
  /* A multiline MATLAB block description:
   * Rte_Call_NotExecuted();
   */
  Rte_IWrite_Ctrl_Step_Output_Value
    (Rte_IRead_Ctrl_Step_Input_Value());
}
''')
        self.assertEqual([(c.line, c.function) for c in calls],
                         [(6, 'Ctrl_Step'), (7, 'Ctrl_Step')])

    def test_strings_chars_and_indirect_member_calls_are_not_direct_calls(self):
        _, calls = scan_calls('''void Ctrl_Step(void) {
  const char *s = "Rte_Read_Fake_Value() {";
  char c = '}';
  /* Rte_Call_Fake(); */
  obj.Rte_Call_Fake();
  obj -> Rte_Call_Fake();
  Rte_Read_Input_Value(&value);
}
''')
        self.assertEqual([c.name for c in calls], ['Rte_Read_Input_Value'])

    def test_compound_control_prefixes_are_calls_not_declarations(self):
        _, calls = scan_calls('''void Step(void) {
  if (flag) return *banned(); else return *banned();
  do banned(); while (flag);
  extern unsigned int *banned(void);
}
''')
        self.assertEqual([c.name for c in calls], ['banned'] * 3)

    def test_adjacent_definitions_and_autosar_macros(self):
        functions, calls = scan_calls('''void First(void) {} void Second(void) { Rte_Read_P_D(); }
FUNC(void, CODE) Third(void) { Rte_Write_P_D(); }
''')
        self.assertEqual([f['name'] for f in functions], ['First', 'Second', 'Third'])
        self.assertEqual([c.function for c in calls if c.name.startswith('Rte_')],
                         ['Second', 'Third'])

    def test_unresolved_calls_remain_visible(self):
        _, calls = scan_calls('''#define ACCESS() Rte_Read_P_D()
UNSUPPORTED_SIGNATURE(Step) { Rte_Write_P_D(); }
''')
        rte = [c for c in calls if c.name.startswith('Rte_')]
        self.assertEqual([c.name for c in rte], ['Rte_Read_P_D', 'Rte_Write_P_D'])
        self.assertTrue(all(c.function is None for c in rte))

    def test_incomplete_function_does_not_discard_its_calls(self):
        _, calls = scan_calls('void Step(void) { Rte_Read_P_D();')
        self.assertEqual([(c.name, c.function) for c in calls if c.name.startswith('Rte_')],
                         [('Rte_Read_P_D', None)])

    def test_comparison_keeps_real_verdict_without_inventing_rte_accesses(self):
        with tempfile.TemporaryDirectory() as temp:
            old, new = Path(temp) / 'old', Path(temp) / 'new'
            old.mkdir()
            new.mkdir()
            original = 'void Step(void) { Rte_Read_Input_Value(&value); }\n'
            (old / 'Ctrl.c').write_text(original, encoding='utf-8')
            current = original + '''float32 Rte_Pim_Ctrl_Buffer_data;
float32* Rte_Pim_Ctrl_Buffer(void) { return &Rte_Pim_Ctrl_Buffer_data; }
const char *log = "Rte_Write_Fake_Value()";
'''
            (new / 'Ctrl.c').write_text(current, encoding='utf-8')
            result = scan(old, new)['Ctrl.c']
            self.assertEqual(result['status'], 'real-change')
            self.assertNotIn('rte', result)
            (new / 'Ctrl.c').write_text(current.replace('Rte_Read_Input_Value',
                                                       'Rte_Read_Other_Value'), encoding='utf-8')
            result = scan(old, new)['Ctrl.c']
            self.assertEqual(result['status'], 'real-change')
            self.assertEqual(result['rte'], {'added': ['Rte_Read_Other_Value'],
                                             'removed': ['Rte_Read_Input_Value']})
