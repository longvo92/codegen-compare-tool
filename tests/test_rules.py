"""Unit tests for the normalization rule modules."""

import unittest

from compare_tool import a2l_rules, arxml_rules, c_rules


class TestCComments(unittest.TestCase):
    def test_line_comment(self):
        s = c_rules.strip_c_comments("int a; // note\nint b;")
        self.assertEqual(s, "int a;        \nint b;")

    def test_block_comment_multiline(self):
        src = "int a;/* one\ntwo */int b;"
        s = c_rules.strip_c_comments(src)
        self.assertEqual(s, "int a;      \n      int b;")
        self.assertEqual(s.count('\n'), src.count('\n'))

    def test_comment_marker_inside_string(self):
        src = 'char *s = "no // comment /* here";'
        self.assertEqual(c_rules.strip_c_comments(src), src)

    def test_string_with_escaped_quote(self):
        src = 'char *s = "a\\"b"; // tail'
        s = c_rules.strip_c_comments(src)
        self.assertTrue(s.startswith('char *s = "a\\"b"; '))
        self.assertNotIn('tail', s)

    def test_char_literal(self):
        src = "char c = '/'; // x"
        s = c_rules.strip_c_comments(src)
        self.assertTrue(s.startswith("char c = '/'; "))
        self.assertNotIn('x', s)


class TestRename(unittest.TestCase):
    def test_simple_consistent(self):
        old = "int rtb_A; rtb_A = rtb_A + 1;"
        new = "int rtb_B; rtb_B = rtb_B + 1;"
        self.assertEqual(c_rules.detect_renames(old, new), {'rtb_A': 'rtb_B'})

    def test_two_pairs(self):
        old = "x = a + b; y = a * b;"
        new = "x = c + d; y = c * d;"
        self.assertEqual(c_rules.detect_renames(old, new), {'a': 'c', 'b': 'd'})

    def test_inconsistent(self):
        old = "a = a + 1; z = a;"
        new = "b = b + 1; z = c;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_not_bijective(self):
        old = "x = a + b;"
        new = "x = c + c;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_non_identifier_change(self):
        old = "x = a + 1;"
        new = "x = a + 2;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_keyword_change_not_rename(self):
        old = "int x;"
        new = "long x;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_structural_change(self):
        old = "x = a;"
        new = "x = a + b;"
        self.assertIsNone(c_rules.detect_renames(old, new))

    def test_apply_map(self):
        self.assertEqual(
            c_rules.apply_rename_map("aa = aa + ab;", {'aa': 'zz'}),
            "zz = zz + ab;")


class TestAutogenNames(unittest.TestCase):
    def test_rtb_pair(self):
        self.assertTrue(c_rules.is_autogen_name_pair('rtb_Switch', 'rtb_Switch_h'))
        # rtb-to-rtb counts even when the root changed (signal relabeled)
        self.assertTrue(c_rules.is_autogen_name_pair('rtb_Sum1', 'rtb_SumOfElements'))

    def test_mangle_suffix_pair(self):
        self.assertTrue(c_rules.is_autogen_name_pair('Gain_Gain_c', 'Gain_Gain_o4'))
        self.assertTrue(c_rules.is_autogen_name_pair('UnitDelay_DSTATE', 'UnitDelay_DSTATE_l'))

    def test_temp_renumber_pair(self):
        self.assertTrue(c_rules.is_autogen_name_pair('tmp', 'tmp_0'))
        self.assertTrue(c_rules.is_autogen_name_pair('tmp_1', 'tmp_2'))
        self.assertTrue(c_rules.is_autogen_name_pair('i_0', 'i_3'))
        self.assertTrue(c_rules.is_autogen_name_pair('loop_ub', 'loop_ub_1'))

    def test_negative_pairs(self):
        self.assertFalse(c_rules.is_autogen_name_pair('x', 'x'))
        self.assertFalse(c_rules.is_autogen_name_pair('alpha', 'beta'))
        self.assertFalse(c_rules.is_autogen_name_pair('i_0', 'j_0'))
        # meaningful multi-letter tails are not mangle suffixes
        self.assertFalse(c_rules.is_autogen_name_pair('motor_in', 'motor_out'))
        self.assertFalse(c_rules.is_autogen_name_pair('sensor_id', 'sensor_io'))
        # numeric block suffixes (Sum1 vs Sum2) are meaningful names
        self.assertFalse(c_rules.is_autogen_name_pair('Sensor_1', 'Sensor_2'))

    def test_mangle_pair_rejected_when_name_preexists(self):
        # pos_x -> pos_y where pos_y already existed in OLD: real rewiring
        old_ids = {'pos_x', 'pos_y'}
        new_ids = {'pos_y'}
        self.assertFalse(c_rules.is_autogen_name_pair('pos_x', 'pos_y',
                                                      old_ids, new_ids))
        # rtb_* stays accepted even when names are reused across functions
        self.assertTrue(c_rules.is_autogen_name_pair(
            'rtb_Switch', 'rtb_Switch_h',
            {'rtb_Switch', 'rtb_Switch_h'}, {'rtb_Switch', 'rtb_Switch_h'}))

    def test_noise_map_chain_ok(self):
        # renumber shift tmp_0->tmp_1, tmp_1->tmp_2 is a chain, not a cycle
        m = c_rules.autogen_noise_map(
            ['tmp_0 = a; tmp_1 = b;'], ['tmp_1 = a; tmp_2 = b;'])
        self.assertEqual(m, {'tmp_0': 'tmp_1', 'tmp_1': 'tmp_2'})

    def test_noise_map_swap_rejected(self):
        # i_0 <-> i_1 swap is a semantic index change
        self.assertIsNone(c_rules.autogen_noise_map(
            ['y = a[i_0] + b[i_1];'], ['y = a[i_1] + b[i_0];']))

    def test_noise_map_conflict_rejected(self):
        self.assertIsNone(c_rules.autogen_noise_map(
            ['x = tmp_0; y = tmp_0;'], ['x = tmp_1; y = tmp_2;']))

    def test_noise_map_non_identifier_change_rejected(self):
        self.assertIsNone(c_rules.autogen_noise_map(
            ['rtb_A = u + 1;'], ['rtb_B = u + 2;']))


class TestArxml(unittest.TestCase):
    def test_uuid(self):
        s = arxml_rules.strip_uuids('<E UUID="123-abc"><F UUID = "xyz"/></E>')
        self.assertEqual(s, '<E UUID=""><F UUID=""/></E>')

    def test_xml_comment_multiline(self):
        src = "<a><!-- one\ntwo --><b/></a>"
        s = arxml_rules.strip_xml_comments(src)
        self.assertEqual(s.count('\n'), src.count('\n'))
        self.assertNotIn('one', s)
        self.assertIn('<b/>', s)

    def test_admin_data_block(self):
        src = "<x>\n<ADMIN-DATA>\n<SD GID=\"d\">2026</SD>\n</ADMIN-DATA>\n<y/></x>"
        s = arxml_rules.strip_admin_data(src)
        self.assertEqual(s.count('\n'), src.count('\n'))
        self.assertNotIn('2026', s)
        self.assertIn('<y/>', s)

    def test_date(self):
        s = arxml_rules.strip_dates('<DATE>2026-01-05</DATE>')
        self.assertNotIn('2026', s)

    def test_shadow_equal_for_uuid_only(self):
        a = '<E UUID="1"><SHORT-NAME>X</SHORT-NAME></E>'
        b = '<E UUID="2"><SHORT-NAME>X</SHORT-NAME></E>'
        self.assertEqual(arxml_rules.arxml_shadow(a), arxml_rules.arxml_shadow(b))

    def test_shadow_differs_for_real_change(self):
        a = '<E UUID="1"><SHORT-NAME>X</SHORT-NAME></E>'
        b = '<E UUID="2"><SHORT-NAME>Y</SHORT-NAME></E>'
        self.assertNotEqual(arxml_rules.arxml_shadow(a), arxml_rules.arxml_shadow(b))


def _arxml(elements, pkg='Pkg'):
    return ('<AUTOSAR xmlns="http://autosar.org/schema/r4.0"><AR-PACKAGES>'
            '<AR-PACKAGE><SHORT-NAME>{}</SHORT-NAME><ELEMENTS>{}</ELEMENTS>'
            '</AR-PACKAGE></AR-PACKAGES></AUTOSAR>'.format(pkg, elements))


class TestInterfaceExtraction(unittest.TestCase):
    def test_basic_kinds(self):
        src = _arxml(
            '<SENDER-RECEIVER-INTERFACE><SHORT-NAME>If_A</SHORT-NAME>'
            '</SENDER-RECEIVER-INTERFACE>'
            '<CLIENT-SERVER-INTERFACE><SHORT-NAME>If_B</SHORT-NAME>'
            '</CLIENT-SERVER-INTERFACE>')
        self.assertEqual(arxml_rules.extract_interfaces(src), {
            '/Pkg/If_A': 'SENDER-RECEIVER-INTERFACE',
            '/Pkg/If_B': 'CLIENT-SERVER-INTERFACE',
        })

    def test_nested_packages_qualify_path(self):
        src = ('<AUTOSAR><AR-PACKAGES><AR-PACKAGE><SHORT-NAME>Top</SHORT-NAME>'
               '<AR-PACKAGES><AR-PACKAGE><SHORT-NAME>Sub</SHORT-NAME><ELEMENTS>'
               '<NV-DATA-INTERFACE><SHORT-NAME>If_Nv</SHORT-NAME></NV-DATA-INTERFACE>'
               '</ELEMENTS></AR-PACKAGE></AR-PACKAGES></AR-PACKAGE>'
               '</AR-PACKAGES></AUTOSAR>')
        self.assertEqual(arxml_rules.extract_interfaces(src),
                         {'/Top/Sub/If_Nv': 'NV-DATA-INTERFACE'})

    def test_non_interface_elements_ignored(self):
        src = _arxml('<IMPLEMENTATION-DATA-TYPE><SHORT-NAME>Speed_T</SHORT-NAME>'
                     '</IMPLEMENTATION-DATA-TYPE>')
        self.assertEqual(arxml_rules.extract_interfaces(src), {})

    def test_malformed_xml_returns_none(self):
        self.assertIsNone(arxml_rules.extract_interfaces('<AUTOSAR><oops'))

    def test_diff_added_removed(self):
        old = _arxml('<SENDER-RECEIVER-INTERFACE><SHORT-NAME>If_Old</SHORT-NAME>'
                     '</SENDER-RECEIVER-INTERFACE>')
        new = _arxml('<CLIENT-SERVER-INTERFACE><SHORT-NAME>If_New</SHORT-NAME>'
                     '</CLIENT-SERVER-INTERFACE>')
        self.assertEqual(arxml_rules.interface_diff(old, new), {
            'added': [('/Pkg/If_New', 'CLIENT-SERVER-INTERFACE')],
            'removed': [('/Pkg/If_Old', 'SENDER-RECEIVER-INTERFACE')],
        })

    def test_diff_one_side_missing_file(self):
        text = _arxml('<TRIGGER-INTERFACE><SHORT-NAME>If_T</SHORT-NAME>'
                      '</TRIGGER-INTERFACE>')
        self.assertEqual(arxml_rules.interface_diff(None, text), {
            'added': [('/Pkg/If_T', 'TRIGGER-INTERFACE')], 'removed': []})
        self.assertEqual(arxml_rules.interface_diff(text, None), {
            'added': [], 'removed': [('/Pkg/If_T', 'TRIGGER-INTERFACE')]})

    def test_diff_parse_error_returns_none(self):
        good = _arxml('')
        self.assertIsNone(arxml_rules.interface_diff(good, '<broken'))
        self.assertIsNone(arxml_rules.interface_diff('<broken', good))


_SWC = (
    '<APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>Ctrl</SHORT-NAME>'
    '<PORTS>'
    '<R-PORT-PROTOTYPE><SHORT-NAME>In1</SHORT-NAME>'
    '<REQUIRED-INTERFACE-TREF>/If/If_Speed</REQUIRED-INTERFACE-TREF>'
    '</R-PORT-PROTOTYPE>'
    '<P-PORT-PROTOTYPE><SHORT-NAME>Out1</SHORT-NAME>'
    '<PROVIDED-INTERFACE-TREF>/If/If_Cmd</PROVIDED-INTERFACE-TREF>'
    '</P-PORT-PROTOTYPE>'
    '</PORTS>'
    '<INTERNAL-BEHAVIORS><SWC-INTERNAL-BEHAVIOR><SHORT-NAME>IB</SHORT-NAME>'
    '<EVENTS><TIMING-EVENT><SHORT-NAME>TE</SHORT-NAME>'
    '<START-ON-EVENT-REF>/Pkg/Ctrl/IB/Run_Step</START-ON-EVENT-REF>'
    '<PERIOD>0.01</PERIOD></TIMING-EVENT></EVENTS>'
    '<RUNNABLES><RUNNABLE-ENTITY><SHORT-NAME>Run_Step</SHORT-NAME>'
    '<SYMBOL>Ctrl_Step</SYMBOL></RUNNABLE-ENTITY></RUNNABLES>'
    '</SWC-INTERNAL-BEHAVIOR></INTERNAL-BEHAVIORS>'
    '</APPLICATION-SW-COMPONENT-TYPE>')


class TestSwcExtraction(unittest.TestCase):
    def test_ports_runnables_events(self):
        swcs = arxml_rules.extract_swcs(_arxml(_SWC))
        self.assertEqual(list(swcs), ['/Pkg/Ctrl'])
        body = swcs['/Pkg/Ctrl']
        self.assertEqual(body['ports'],
                         {'In1': 'R-PORT If_Speed', 'Out1': 'P-PORT If_Cmd'})
        self.assertEqual(body['runnables'], {'Run_Step': 'Ctrl_Step'})
        self.assertEqual(body['events'], {'TE': 'TIMING 0.01s on Run_Step'})

    def test_malformed_returns_none(self):
        self.assertIsNone(arxml_rules.extract_swcs('<AUTOSAR><oops'))

    def test_diff_added_port_and_changed_period(self):
        new = _SWC.replace('0.01', '0.02').replace(
            '</PORTS>',
            '<P-PORT-PROTOTYPE><SHORT-NAME>Out2</SHORT-NAME>'
            '<PROVIDED-INTERFACE-TREF>/If/If_Diag</PROVIDED-INTERFACE-TREF>'
            '</P-PORT-PROTOTYPE></PORTS>')
        d = arxml_rules.swc_diff(_arxml(_SWC), _arxml(new))
        self.assertEqual(d['ports']['added'],
                         [('/Pkg/Ctrl', 'Out2', 'P-PORT If_Diag')])
        self.assertEqual(d['events']['changed'],
                         [('/Pkg/Ctrl', 'TE', 'TIMING 0.01s on Run_Step',
                           'TIMING 0.02s on Run_Step')])
        self.assertFalse(arxml_rules.swc_diff_empty(d))

    def test_diff_one_side_missing_file(self):
        d = arxml_rules.swc_diff(None, _arxml(_SWC))
        self.assertEqual(d['swcs']['added'], ['/Pkg/Ctrl'])
        self.assertEqual([r[:2] for r in d['ports']['added']],
                         [('/Pkg/Ctrl', 'In1'), ('/Pkg/Ctrl', 'Out1')])
        d = arxml_rules.swc_diff(_arxml(_SWC), None)
        self.assertEqual(d['swcs']['removed'], ['/Pkg/Ctrl'])

    def test_diff_parse_error_returns_none(self):
        self.assertIsNone(arxml_rules.swc_diff(_arxml(_SWC), '<broken'))

    def test_diff_equal_is_empty(self):
        d = arxml_rules.swc_diff(_arxml(_SWC), _arxml(_SWC))
        self.assertTrue(arxml_rules.swc_diff_empty(d))


class TestRteCalls(unittest.TestCase):
    def test_extract_unique_sorted(self):
        src = ('x = Rte_Read_In1_Speed(&u);\n'
               'Rte_Write_Out1_Cmd(u);\n'
               'Rte_Write_Out1_Cmd(v);\n'
               'y = Rte_IrvRead_Step_State();\n')
        self.assertEqual(c_rules.extract_rte_calls(src),
                         ['Rte_IrvRead_Step_State', 'Rte_Read_In1_Speed',
                          'Rte_Write_Out1_Cmd'])

    def test_commented_call_not_counted(self):
        src = '/* Rte_Write_Old_Cmd(u); */\nRte_Read_In1_Speed(&u);\n'
        self.assertEqual(c_rules.extract_rte_calls(src), ['Rte_Read_In1_Speed'])

    def test_non_api_identifier_ignored(self):
        # Rte_Foo_x has no standard API verb -> not summarized (fail-safe)
        self.assertEqual(c_rules.extract_rte_calls('Rte_Foo_x();'), [])

    def test_diff(self):
        d = c_rules.rte_diff('Rte_Read_A_a(&x);', 'Rte_Read_A_a(&x); Rte_Call_B_Op();')
        self.assertEqual(d, {'added': ['Rte_Call_B_Op'], 'removed': []})

    def test_diff_one_side_missing_file(self):
        d = c_rules.rte_diff(None, 'Rte_Write_P_d(x);')
        self.assertEqual(d, {'added': ['Rte_Write_P_d'], 'removed': []})


_A2L = (
    'ASAP2_VERSION 1 71\n'
    '/begin PROJECT Demo ""\n'
    '  /begin MODULE Ctrl ""\n'
    '    /begin CHARACTERISTIC K_Gain "gain /begin MEASUREMENT Fake"\n'
    '      VALUE 0x80001000 __Scalar 100 CM_Gain 0 10\n'
    '      /begin IF_DATA XCP\n'
    '      /end IF_DATA\n'
    '    /end CHARACTERISTIC\n'
    '    /* /begin CHARACTERISTIC Commented "x" */\n'
    '    /begin MEASUREMENT EngSpd "engine speed" UWORD CM_EngSpd 1 100 0 8000\n'
    '    /end MEASUREMENT\n'
    '  /end MODULE\n'
    '/end PROJECT\n')


class TestA2l(unittest.TestCase):
    def test_extract(self):
        # the '/begin' inside the description string and the commented-out
        # block must not fake objects
        self.assertEqual(a2l_rules.extract_objects(_A2L),
                         {'K_Gain': 'CHARACTERISTIC', 'EngSpd': 'MEASUREMENT'})

    def test_extract_name_on_next_line(self):
        src = '/begin MEASUREMENT\n  VehSpd "v" UWORD CM 1 100 0 300\n/end MEASUREMENT\n'
        self.assertEqual(a2l_rules.extract_objects(src), {'VehSpd': 'MEASUREMENT'})

    def test_shadow_equal_for_comment_only(self):
        a = '/* Mon */\n/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        b = '/* Tue */\n/begin MEASUREMENT M "d" UWORD CM 1 100 0 1\n/end MEASUREMENT\n'
        self.assertEqual(a2l_rules.a2l_shadow(a), a2l_rules.a2l_shadow(b))

    def test_backslash_is_literal_not_escape(self):
        # A2L strings have no C escapes: a description ending in a literal
        # backslash (a Windows path) must not swallow its closing quote and
        # blank the objects that follow
        src = (
            '/begin CHARACTERISTIC PathCal "C:\\cal\\"\n'
            '  VALUE 0x1000 __S 100 CM 0 10\n'
            '/end CHARACTERISTIC\n'
            '/begin MEASUREMENT Speed "speed sig" UWORD CM_S 1 100 0 300\n'
            '/end MEASUREMENT\n')
        self.assertEqual(a2l_rules.extract_objects(src),
                         {'PathCal': 'CHARACTERISTIC', 'Speed': 'MEASUREMENT'})

    def test_doubled_quote_stays_inside_string(self):
        src = ('/begin MEASUREMENT M "say ""hi"" /begin MEASUREMENT Fake"'
               ' UWORD CM 1 100 0 1\n/end MEASUREMENT\n')
        self.assertEqual(a2l_rules.extract_objects(src), {'M': 'MEASUREMENT'})

    def test_comment_after_backslash_string_is_stripped(self):
        a = 'VAL "C:\\cal\\" /* built Mon */\n'
        b = 'VAL "C:\\cal\\" /* built Tue */\n'
        self.assertEqual(a2l_rules.a2l_shadow(a), a2l_rules.a2l_shadow(b))

    def test_diff_added_removed(self):
        new = _A2L.replace(
            '    /begin MEASUREMENT EngSpd "engine speed" UWORD CM_EngSpd 1 100 0 8000\n'
            '    /end MEASUREMENT\n',
            '    /begin MEASUREMENT VehSpd "vehicle speed" UWORD CM_VehSpd 1 100 0 300\n'
            '    /end MEASUREMENT\n')
        self.assertEqual(a2l_rules.a2l_diff(_A2L, new), {
            'added': [('VehSpd', 'MEASUREMENT')],
            'removed': [('EngSpd', 'MEASUREMENT')],
        })

    def test_diff_equal_is_empty(self):
        self.assertEqual(a2l_rules.a2l_diff(_A2L, _A2L),
                         {'added': [], 'removed': []})

    def test_diff_one_side_missing_file(self):
        d = a2l_rules.a2l_diff(None, _A2L)
        self.assertEqual(d['added'], [('EngSpd', 'MEASUREMENT'),
                                      ('K_Gain', 'CHARACTERISTIC')])
        self.assertEqual(d['removed'], [])
        d = a2l_rules.a2l_diff(_A2L, None)
        self.assertEqual(d['added'], [])
        self.assertEqual(d['removed'], [('EngSpd', 'MEASUREMENT'),
                                        ('K_Gain', 'CHARACTERISTIC')])


if __name__ == '__main__':
    unittest.main()
