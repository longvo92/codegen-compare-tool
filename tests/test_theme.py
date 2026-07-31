"""The shared colour palettes.

The point of one seam per shared decision is that the surfaces cannot drift, so
what is tested here is that neither palette can go missing a role the other has,
that a role always resolves, and that the CSS emitter never writes a colour the
browser would read differently from Qt.
"""

import re
import unittest

from compare_tool import theme


class TestPalettes(unittest.TestCase):
    def test_both_themes_define_exactly_the_same_roles(self):
        # a role in one palette only paints one theme correctly and raises on
        # the other -- on whichever surface nobody happened to look at
        self.assertEqual(set(theme.PALETTES[theme.DARK]),
                         set(theme.PALETTES[theme.LIGHT]))

    def test_every_value_is_a_hex_colour(self):
        for name in theme.THEMES:
            for role, value in theme.palette(name).items():
                self.assertRegex(value, r'^#(?:[0-9a-f]{6}|[0-9a-f]{8})$',
                                 '{} {}'.format(name, role))

    def test_the_two_themes_are_actually_different(self):
        dark, light = theme.palette(theme.DARK), theme.palette(theme.LIGHT)
        self.assertNotEqual(dark['bg'], light['bg'])

    def test_dark_is_dark_and_light_is_light(self):
        def lum(value):
            h = value.lstrip('#')
            return sum(int(h[i:i + 2], 16) for i in (0, 2, 4))

        self.assertLess(lum(theme.color('bg', theme.DARK)), 250)
        self.assertGreater(lum(theme.color('bg', theme.LIGHT)), 500)

    def test_text_contrasts_with_its_own_background(self):
        # not a WCAG check, just the failure that actually happens: a role
        # copied from the other theme and left there
        for name in theme.THEMES:
            for fg, bg in (('fg', 'bg'), ('code-fg', 'code-bg'),
                           ('muted-fg', 'muted-bg')):
                def lum(role):
                    h = theme.color(role, name).lstrip('#')
                    return sum(int(h[i:i + 2], 16) for i in (0, 2, 4)) / 3

                self.assertGreater(abs(lum(fg) - lum(bg)), 40,
                                   '{} {} on {}'.format(name, fg, bg))


class TestLookup(unittest.TestCase):
    def test_an_unknown_theme_falls_back_instead_of_raising(self):
        # a colour scheme is never worth refusing to open the tool over
        self.assertEqual(theme.normalize('solarized'), theme.DEFAULT)
        self.assertEqual(theme.normalize(None), theme.DEFAULT)

    def test_an_unknown_role_raises(self):
        # the opposite call: a typo must not become a silently absent colour
        with self.assertRaises(KeyError):
            theme.color('no-such-role')

    def test_other_is_the_one_the_toggle_goes_to(self):
        self.assertEqual(theme.other(theme.DARK), theme.LIGHT)
        self.assertEqual(theme.other(theme.LIGHT), theme.DARK)

    def test_set_current_returns_what_took_effect(self):
        before = theme.current()
        try:
            self.assertEqual(theme.set_current(theme.LIGHT), theme.LIGHT)
            self.assertEqual(theme.c('bg'), theme.color('bg', theme.LIGHT))
            self.assertEqual(theme.set_current('nonsense'), theme.DEFAULT)
        finally:
            theme.set_current(before)


class TestCssVars(unittest.TestCase):
    def test_every_var_is_a_six_digit_hex(self):
        # Qt writes #aarrggbb and CSS reads #rrggbbaa, so an alpha role emitted
        # here would define a WRONG colour, not merely an unused one
        for name in theme.THEMES:
            for value in re.findall(r'--[\w-]+:(#[0-9a-f]+);',
                                    theme.css_vars(name)):
                self.assertEqual(len(value), 7, '{} {}'.format(name, value))

    def test_the_roles_the_report_uses_are_all_emitted(self):
        from compare_tool.report import _CSS
        emitted = set(re.findall(r'--([\w-]+):', theme.css_vars(theme.DARK)))
        for role in set(re.findall(r'var\(--([\w-]+)\)', _CSS)):
            self.assertIn(role, emitted, role)


if __name__ == '__main__':
    unittest.main()
