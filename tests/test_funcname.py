"""The enclosing-scope labels that feed the hunk captions and the Affected
list. These are navigation aids, so the bar is: name the obvious cases, and
stay silent (None) rather than guess where the shape is not a definition."""

import unittest

from compare_tool import funcname


def enc(text, language):
    return funcname.enclosing(text.split('\n'), language)


class TestC(unittest.TestCase):
    def test_plain_function_body(self):
        src = ('void foo(void)\n'
               '{\n'
               '    int x = 1;\n'
               '}\n')
        labels = enc(src, 'c')
        self.assertEqual(labels[0], 'foo')
        self.assertEqual(labels[1], 'foo')
        self.assertEqual(labels[2], 'foo')
        self.assertEqual(labels[3], 'foo')

    def test_static_and_qualifiers(self):
        src = 'static inline uint8_T Rte_Runnable_Step(int a)\n{\n  return a;\n}\n'
        self.assertEqual(enc(src, 'c')[2], 'Rte_Runnable_Step')

    def test_return_type_on_own_line(self):
        # Embedded Coder wraps a long signature: name is not on the type line
        src = 'static void\nModel_step(void)\n{\n  step();\n}\n'
        self.assertEqual(enc(src, 'c')[3], 'Model_step')

    def test_multiline_parameter_list(self):
        src = ('void Foo(int a,\n'
               '         int b)\n'
               '{\n'
               '  use(a, b);\n'
               '}\n')
        self.assertEqual(enc(src, 'c')[3], 'Foo')

    def test_line_after_close_is_unlabelled(self):
        src = 'void a(void)\n{\n}\n\nint g;\n'
        labels = enc(src, 'c')
        self.assertEqual(labels[1], 'a')
        self.assertIsNone(labels[3])  # blank line between functions
        self.assertIsNone(labels[4])  # a file-scope declaration, not a body

    def test_two_functions_do_not_bleed(self):
        src = ('int a(void)\n{\n  return 1;\n}\n'
               'int b(void)\n{\n  return 2;\n}\n')
        labels = enc(src, 'c')
        self.assertEqual(labels[2], 'a')
        self.assertEqual(labels[6], 'b')

    def test_nested_block_keeps_function_name(self):
        src = ('void f(void)\n{\n  if (x) {\n    y();\n  }\n}\n')
        labels = enc(src, 'c')
        self.assertEqual(labels[3], 'f')  # inside the if-block, still f

    def test_prototype_is_not_a_definition(self):
        src = 'void proto(int a);\nint next(void)\n{\n}\n'
        labels = enc(src, 'c')
        self.assertIsNone(labels[0])  # a declaration opens no body
        self.assertEqual(labels[2], 'next')

    def test_preprocessor_does_not_leak(self):
        src = '#include <stdio.h>\n#define N 4\nvoid real(void)\n{\n  z();\n}\n'
        labels = enc(src, 'c')
        self.assertIsNone(labels[0])
        self.assertEqual(labels[4], 'real')

    def test_data_initializer_is_not_a_function(self):
        src = 'const int T[] =\n{\n  1, 2, 3\n};\n'
        self.assertIsNone(enc(src, 'c')[2])

    def test_named_struct_tag(self):
        src = 'typedef struct Tag_T\n{\n  int a;\n} Tag_T;\n'
        self.assertEqual(enc(src, 'c')[2], 'Tag_T')

    def test_anonymous_struct_stays_unlabelled(self):
        # the name only exists after the closing brace; guessing it would be
        # worse than saying nothing
        src = 'typedef struct\n{\n  int a;\n} Anon_T;\n'
        self.assertIsNone(enc(src, 'c')[2])

    def test_brace_inside_string_is_not_structure(self):
        src = 'void f(void)\n{\n  p("}");\n  q();\n}\n'
        self.assertEqual(enc(src, 'c')[3], 'f')


class TestCpp(unittest.TestCase):
    def test_namespace_class_method_nest(self):
        src = ('namespace drv {\n'
               'class Motor {\n'
               'public:\n'
               '  void step(int n) {\n'
               '    x = n;\n'
               '  }\n'
               '};\n'
               '}\n')
        labels = enc(src, 'cpp')
        self.assertEqual(labels[0], 'drv')            # namespace scope
        self.assertEqual(labels[1], 'drv / Motor')    # class inside namespace
        self.assertEqual(labels[4], 'Motor / step')   # method body, innermost

    def test_a_namespace_does_not_swallow_the_function(self):
        # the single-open-scope walk C uses would label this 'ns'; the brace
        # stack keeps the function name
        src = 'namespace ns {\nint compute() {\n  return 1;\n}\n}\n'
        self.assertEqual(enc(src, 'cpp')[2], 'ns / compute')

    def test_out_of_line_method_keeps_its_qualifier(self):
        src = 'void Motor::stop() {\n  y = 0;\n}\n'
        self.assertEqual(enc(src, 'cpp')[1], 'Motor::stop')

    def test_destructor(self):
        src = 'Motor::~Motor() {\n  cleanup();\n}\n'
        self.assertEqual(enc(src, 'cpp')[1], 'Motor::~Motor')

    def test_enum_class_names_the_enum_not_class(self):
        src = 'enum class Color {\n  Red,\n  Green\n};\n'
        self.assertEqual(enc(src, 'cpp')[1], 'Color')

    def test_control_block_opens_no_scope(self):
        src = 'int f() {\n  if (x) {\n    g();\n  }\n}\n'
        self.assertEqual(enc(src, 'cpp')[2], 'f')  # inside the if, still f

    def test_call_with_brace_argument_is_not_a_scope(self):
        # f({...}) is a call, not a definition -- the '{' sits inside parens
        src = 'int g() {\n  f({1, 2});\n  return 0;\n}\n'
        self.assertEqual(enc(src, 'cpp')[1], 'g')

    def test_brace_inside_string_is_not_structure(self):
        src = 'void f() {\n  log("}");\n  q();\n}\n'
        self.assertEqual(enc(src, 'cpp')[2], 'f')


class TestPython(unittest.TestCase):
    SRC = ('import os\n'
           '\n'
           'class Limiter:\n'
           '    def __init__(self, c):\n'
           '        self.c = c\n'
           '\n'
           '    def step(self, r):\n'
           '        return min(r, self.c)\n'
           '\n'
           'def helper(x):\n'
           '    return x + 1\n')

    def test_method_inside_class(self):
        labels = enc(self.SRC, 'python')
        self.assertEqual(labels[3], 'Limiter / __init__')
        self.assertEqual(labels[4], 'Limiter / __init__')  # body by indent
        self.assertEqual(labels[6], 'Limiter / step')

    def test_top_level_function(self):
        labels = enc(self.SRC, 'python')
        self.assertEqual(labels[9], 'helper')
        self.assertEqual(labels[10], 'helper')

    def test_module_level_lines_are_unlabelled(self):
        labels = enc(self.SRC, 'python')
        self.assertIsNone(labels[0])  # import, at module level
        self.assertIsNone(labels[1])  # blank line before the class
        # the class line names itself, like a C function's signature line does
        self.assertEqual(labels[2], 'Limiter')

    def test_def_inside_a_docstring_is_not_a_definition(self):
        src = ('def real(x):\n'
               '    """example:\n'
               '        def fake():\n'
               '            pass\n'
               '    """\n'
               '    return x\n')
        labels = enc(src, 'python')
        self.assertEqual(labels[5], 'real')      # the real body
        # the fake 'def' inside the docstring never opened a scope
        self.assertEqual(labels[3], 'real')

    def test_dedent_closes_the_function(self):
        src = 'def a():\n    return 1\nb = 2\n'
        labels = enc(src, 'python')
        self.assertEqual(labels[1], 'a')
        self.assertIsNone(labels[2])  # dedented back to module level


class TestArxml(unittest.TestCase):
    SRC = ('<AR-PACKAGE>\n'
           '  <SHORT-NAME>Ctrl</SHORT-NAME>\n'
           '  <ELEMENTS>\n'
           '    <RUNNABLE-ENTITY>\n'
           '      <SHORT-NAME>Step</SHORT-NAME>\n'
           '      <PERIOD>0.01</PERIOD>\n'
           '    </RUNNABLE-ENTITY>\n'
           '  </ELEMENTS>\n'
           '</AR-PACKAGE>\n')

    def test_innermost_named_scope_with_parent(self):
        labels = enc(self.SRC, 'arxml')
        # the PERIOD line sits inside the runnable, inside the package
        self.assertEqual(labels[5], 'Ctrl / Step')

    def test_outer_scope_before_inner_opens(self):
        labels = enc(self.SRC, 'arxml')
        self.assertEqual(labels[2], 'Ctrl')  # <ELEMENTS>, still only Ctrl named

    def test_self_closing_element_opens_nothing(self):
        src = ('<A>\n  <SHORT-NAME>Top</SHORT-NAME>\n  <REF DEST="X"/>\n</A>\n')
        self.assertEqual(enc(src, 'arxml')[2], 'Top')


class TestA2l(unittest.TestCase):
    def test_characteristic_name(self):
        src = ('/begin MODULE M ""\n'
               '  /begin CHARACTERISTIC K_Gain "gain"\n'
               '    VALUE 0x1000\n'
               '  /end CHARACTERISTIC\n'
               '/end MODULE\n')
        labels = enc(src, 'a2l')
        self.assertEqual(labels[2], 'K_Gain')
        self.assertEqual(labels[0], 'M')

    def test_begin_inside_comment_ignored(self):
        src = ('/begin MEASUREMENT Speed "s"\n'
               '  /* /begin CHARACTERISTIC Fake */\n'
               '  ECU_ADDRESS 0x1\n'
               '/end MEASUREMENT\n')
        self.assertEqual(enc(src, 'a2l')[2], 'Speed')

    def test_block_without_identifier_falls_back_to_kind(self):
        src = '/begin MOD_PAR "comment only"\n  X 1\n/end MOD_PAR\n'
        self.assertEqual(enc(src, 'a2l')[1], 'MOD_PAR')


class TestUnknownLanguage(unittest.TestCase):
    def test_plain_text_is_all_none(self):
        labels = funcname.enclosing(['a', 'b', 'c'], None)
        self.assertEqual(labels, [None, None, None])

    def test_length_always_matches(self):
        for lang in ('c', 'arxml', 'a2l', None):
            self.assertEqual(len(funcname.enclosing(['x'] * 5, lang)), 5)


class TestHunkHelpers(unittest.TestCase):
    def test_hunk_label_prefers_new_side(self):
        old = ['a', 'a', None]
        new = ['b', 'b', 'b']
        h = {'kind': 'real', 'old_range': [0, 1], 'new_range': [0, 1]}
        self.assertEqual(funcname.hunk_label(old, new, h), 'b')

    def test_hunk_label_falls_back_for_pure_delete(self):
        old = ['gone', 'gone']
        new = [None]
        # a pure deletion: new_range is an empty insertion point past the end
        h = {'kind': 'real', 'old_range': [0, 2], 'new_range': [1, 1]}
        self.assertEqual(funcname.hunk_label(old, new, h), 'gone')

    def test_affected_dedupes_and_skips_noise(self):
        old = ['f', 'f', 'g', 'h']
        new = ['f', 'f', 'g', 'h']
        hunks = [
            {'kind': 'real', 'old_range': [0, 1], 'new_range': [0, 1]},
            {'kind': 'comment', 'old_range': [1, 2], 'new_range': [1, 2]},
            {'kind': 'real', 'old_range': [1, 2], 'new_range': [1, 2]},  # still f
            {'kind': 'moved', 'old_range': [2, 3], 'new_range': [2, 3]},
        ]
        self.assertEqual(funcname.affected(old, new, hunks), ['f', 'g'])


if __name__ == '__main__':
    unittest.main()
