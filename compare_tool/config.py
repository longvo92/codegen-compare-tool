"""Portable, versioned application settings. Importing this module needs no Qt or YAML."""

import os
import re
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

from . import consistency, theme


def defaults():
    return {
        'schema_version': 1,
        'appearance': {'language': 'en', 'theme': theme.LIGHT},
        'display': {'comment': True, 'unimportant': True, 'hide_identical': False},
        'compare': {'exclude': [], 'arxml_only': False, 'skip_var_renames': False,
                    'custom_rules': [], 'check_consistency': False, 'exit_zero': False},
        'code_check': {'exclude': [], 'ignore_regex': '',
                       'policy': consistency.load_checker_config(None)},
        'report': {'theme': theme.DARK, 'enabled': True, 'max_diff_lines': 0},
    }


def settings_path():
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming')
        return base / 'CodeGenStudio' / 'settings.yaml'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'CodeGenStudio' / 'settings.yaml'
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'codegen-studio' / 'settings.yaml'


def _merge(base, supplied, location='config'):
    if not isinstance(supplied, dict):
        raise ValueError('{} must be an object'.format(location))
    for key, value in supplied.items():
        if key not in base:
            raise ValueError('unknown setting: {}.{}'.format(location, key))
        if isinstance(base[key], dict):
            _merge(base[key], value, '{}.{}'.format(location, key))
        else:
            base[key] = value


def validate(supplied):
    config = defaults()
    _merge(config, supplied)
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('unsupported schema_version')
    if config['appearance']['language'] not in ('en', 'vi'):
        raise ValueError('appearance.language must be en or vi')
    for section in ('appearance', 'report'):
        if config[section]['theme'] not in theme.THEMES:
            raise ValueError('{}.theme is invalid'.format(section))
    for section, keys in (('display', ('comment', 'unimportant', 'hide_identical')),
                          ('compare', ('arxml_only', 'skip_var_renames', 'check_consistency', 'exit_zero')),
                          ('report', ('enabled',))):
        for key in keys:
            if type(config[section][key]) is not bool:
                raise ValueError('{}.{} must be boolean'.format(section, key))
    if type(config['report']['max_diff_lines']) is not int or config['report']['max_diff_lines'] < 0:
        raise ValueError('report.max_diff_lines must be a nonnegative integer')
    for section in ('compare', 'code_check'):
        value = config[section]['exclude']
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            raise ValueError('{}.exclude must be a list of nonempty strings'.format(section))
    if not isinstance(config['code_check']['ignore_regex'], str):
        raise ValueError('code_check.ignore_regex must be a string')
    policy = config['code_check']['policy']
    consistency._validate_config(policy)
    consistency.validate_checker_regex(policy, config['code_check']['ignore_regex'])
    rules = config['compare']['custom_rules']
    if not isinstance(rules, list):
        raise ValueError('compare.custom_rules must be a list')
    from .userrules import _parse_rule
    for rule in rules:
        warnings = []
        if isinstance(rule, dict) and 'extensions' in rule:
            extensions = rule['extensions']
            if extensions not in (None, '*') and (not isinstance(extensions, list) or
                                                    not all(isinstance(ext, str) for ext in extensions)):
                raise ValueError('custom rule extensions must be a list of strings')
        if _parse_rule(rule, warnings) is None or warnings:
            raise ValueError('invalid custom rule: {}'.format('; '.join(warnings)))
        if set(rule) - {'name', 'pattern', 'replacement', 'extensions'}:
            raise ValueError('unknown custom rule field')
    return config


def _yaml():
    try:
        import yaml
    except ImportError as exc:
        raise ValueError('YAML config requires PyYAML; install codegen-compare-tool[config]') from exc
    return yaml


def parse_yaml(raw):
    yaml = _yaml()

    class UniqueLoader(yaml.SafeLoader):
        pass

    # YAML 1.1 treats policy severities `off`/`on` as booleans. The app schema
    # uses only true/false for flags; leave policy words as strings.
    UniqueLoader.yaml_implicit_resolvers = {
        key: [(tag, pattern) for tag, pattern in resolvers
              if tag != 'tag:yaml.org,2002:bool']
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    boolean = re.compile(r'^(?:true|false)$', re.IGNORECASE)
    UniqueLoader.add_implicit_resolver('tag:yaml.org,2002:bool', boolean, 'tTfF')

    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if not isinstance(key, str) or key in result:
                raise ValueError('duplicate or non-string YAML key: {}'.format(key))
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        supplied = yaml.load(raw, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ValueError('invalid YAML: {}'.format(exc)) from exc
    return supplied


def load(path):
    supplied = parse_yaml(Path(path).read_text(encoding='utf-8'))
    return validate(supplied)


def save(path, config):
    yaml = _yaml()
    value = validate(deepcopy(config))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.settings-', suffix='.yaml', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            yaml.safe_dump(value, stream, allow_unicode=True, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def compile_rules(config):
    from .userrules import _parse_rule
    return tuple(_parse_rule(item, []) for item in config['compare']['custom_rules'])
