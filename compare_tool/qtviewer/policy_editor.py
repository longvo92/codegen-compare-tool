"""Structured editor for the reusable Code Check policy."""

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFormLayout, QGroupBox,
                               QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..consistency import _CONFIG_LISTS, _EXCEPTION_RULES


_LIST_LABELS = {
    'forbidden_rte_prefixes': 'Forbidden RTE prefixes',
    'ignore_access_port_regex': 'Ignored access-port regex',
    'ignore_rte_call_regex': 'Ignored RTE-call regex',
    'forbidden_functions': 'Forbidden functions',
    'nvm_packages': 'NVM packages',
    'dem_packages': 'DEM packages',
    'nvm_interface_names': 'NVM interface names',
    'dem_interface_names': 'DEM interface names',
}

_MAPPING_COLUMNS = ('file', 'function', 'runnable', 'reason')
_EXCEPTION_COLUMNS = ('rule', 'reason', 'file', 'swc', 'runnable', 'port')
_COLUMN_LABELS = {
    'file': 'File', 'function': 'Function', 'runnable': 'Runnable',
    'reason': 'Reason', 'rule': 'Rule', 'swc': 'SWC', 'port': 'Port',
}

_RULE_LABELS = {
    'forbidden_rte_api': 'Forbidden RTE API',
    'no_matching_port_dataelement': 'No matching Port/DataElement',
    'missing_access_point_in_arxml': 'Missing ARXML access point',
    'inconsistent_arxml_access_mode': 'Inconsistent ARXML access mode',
    'access_mode_mismatch': 'Access mode mismatch',
    'orphan_access': 'Orphan access',
    'nvm_package': 'NVM package',
    'dem_package': 'DEM package',
    'forbidden_function': 'Forbidden function',
}


class PolicyEditor(QWidget):
    """Edit every policy field without exposing YAML syntax in the viewer."""

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._policy = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        lists_page = QWidget()
        lists_layout = QVBoxLayout(lists_page)
        lists_layout.addWidget(QLabel(tr('Double-click a value to edit it.')))
        self.lists = {}
        for key in _CONFIG_LISTS:
            group = QGroupBox(tr(_LIST_LABELS[key]))
            group_layout = QVBoxLayout(group)
            entries = QListWidget()
            entries.setObjectName(key)
            entries.setAccessibleName(tr(_LIST_LABELS[key]))
            entries.setSelectionMode(QAbstractItemView.SingleSelection)
            entries.setEditTriggers(QAbstractItemView.DoubleClicked |
                                    QAbstractItemView.EditKeyPressed)
            entries.setMinimumHeight(72)
            self.lists[key] = entries
            group_layout.addWidget(entries)
            buttons = QHBoxLayout()
            add = QPushButton(tr('Add…'))
            add.clicked.connect(lambda _=False, name=key: self._add_list_item(name))
            remove = QPushButton(tr('Remove selected'))
            remove.clicked.connect(lambda _=False, name=key: self._remove_list_item(name))
            buttons.addWidget(add)
            buttons.addWidget(remove)
            buttons.addStretch()
            group_layout.addLayout(buttons)
            lists_layout.addWidget(group)
        lists_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(lists_page)
        self.tabs.addTab(scroll, tr('Patterns & names'))

        rules_page = QWidget()
        rules_layout = QFormLayout(rules_page)
        self.rules = {}
        # Preserve the policy's declared rule order when loading it.
        self._rules_layout = rules_layout
        self.tabs.addTab(rules_page, tr('Rules'))

        self.mappings = self._table_page('Function mappings', _MAPPING_COLUMNS)
        self.exceptions = self._table_page('Exceptions', _EXCEPTION_COLUMNS)

        reason_row = QHBoxLayout()
        label = QLabel(tr('No RTE expected (reason)'))
        self.no_rte_expected = QLineEdit()
        label.setBuddy(self.no_rte_expected)
        reason_row.addWidget(label)
        reason_row.addWidget(self.no_rte_expected, 1)
        layout.addLayout(reason_row)

    def _table_page(self, title, columns):
        page = QWidget()
        layout = QVBoxLayout(page)
        table = QTableWidget(0, len(columns))
        table.setObjectName(title.lower().replace(' ', '_'))
        table.setHorizontalHeaderLabels([self._tr(_COLUMN_LABELS[key]) for key in columns])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(160)
        layout.addWidget(table)
        buttons = QHBoxLayout()
        add = QPushButton(self._tr('Add row'))
        add.clicked.connect(lambda: self._add_row(table, columns))
        remove = QPushButton(self._tr('Remove selected'))
        remove.clicked.connect(lambda: table.removeRow(table.currentRow())
                               if table.currentRow() >= 0 else None)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.tabs.addTab(page, self._tr(title))
        return table

    def _add_list_item(self, key):
        value, accepted = QInputDialog.getText(self, self._tr(_LIST_LABELS[key]),
                                               self._tr('Value'))
        if accepted and value.strip():
            item = QListWidgetItem(value.strip())
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.lists[key].addItem(item)

    def _remove_list_item(self, key):
        widget = self.lists[key]
        if widget.currentRow() >= 0:
            widget.takeItem(widget.currentRow())

    def _add_row(self, table, columns, entry=None):
        entry = entry or {}
        row = table.rowCount()
        table.insertRow(row)
        for column, key in enumerate(columns):
            if key == 'rule':
                combo = QComboBox()
                for rule in sorted(_EXCEPTION_RULES):
                    combo.addItem(rule, rule)
                combo.setCurrentIndex(combo.findData(entry.get(key, '')))
                table.setCellWidget(row, column, combo)
                continue
            item = QTableWidgetItem(entry.get(key, ''))
            table.setItem(row, column, item)
        return row

    def set_policy(self, policy):
        self._policy = deepcopy(policy)
        for key, widget in self.lists.items():
            widget.clear()
            for value in policy[key]:
                item = QListWidgetItem(value)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                widget.addItem(item)
        for combo in self.rules.values():
            self._rules_layout.removeRow(combo)
        self.rules.clear()
        for key, severity in policy['rules'].items():
            combo = QComboBox()
            combo.setObjectName(key)
            combo.setAccessibleName(key)
            for choice in ('fail', 'warn', 'skip', 'off'):
                combo.addItem(choice, choice)
            combo.setCurrentIndex(combo.findData(severity))
            self._rules_layout.addRow(self._tr(_RULE_LABELS[key]), combo)
            self.rules[key] = combo
        for table, name, columns in ((self.mappings, 'function_mappings', _MAPPING_COLUMNS),
                                     (self.exceptions, 'exceptions', _EXCEPTION_COLUMNS)):
            table.setRowCount(0)
            for entry in policy[name]:
                self._add_row(table, columns, entry)
        self.no_rte_expected.setText(policy['no_rte_expected'])

    @staticmethod
    def _rows(table, columns):
        result = []
        for row in range(table.rowCount()):
            entry = {key: (table.cellWidget(row, column).currentData()
                           if key == 'rule' else table.item(row, column).text().strip())
                     for column, key in enumerate(columns)}
            if columns == _EXCEPTION_COLUMNS:
                entry = {key: value for key, value in entry.items() if value}
            result.append(entry)
        return result

    def policy(self):
        value = deepcopy(self._policy)
        for key, widget in self.lists.items():
            value[key] = [widget.item(row).text().strip() for row in range(widget.count())]
        value['rules'] = {key: combo.currentData() for key, combo in self.rules.items()}
        value['function_mappings'] = self._rows(self.mappings, _MAPPING_COLUMNS)
        value['exceptions'] = self._rows(self.exceptions, _EXCEPTION_COLUMNS)
        value['no_rte_expected'] = self.no_rte_expected.text().strip()
        return value
