"""Daily Entry page: one block per customer, with as many products as you like inside it.

Each customer block = Type, Customer, Date  +  any number of product lines (Product, Quantity, Rate, Total)  +  one big
Notes box (scrolls when the text is long).  Every product line becomes one ledger entry.
Total of a line = Quantity x Rate.  Leave Quantity empty and the Total is simply the amount typed (use this for payments).
The Notes of a block are stored with the first product line that gets added (so a note is not repeated on every line).

Rows added here do NOT go into the customer's ledger straight away. They appear in the "Waiting" list below
and are saved automatically 24 hours later. Until then a row can be deleted (e.g. the customer brought the goods
back) or saved early with "Save now".
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCompleter, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QScrollArea,
    QScroller, QVBoxLayout, QWidget,
)

from .. import dates, money, viewmodel
from ..labels import JAMA_LABEL, QUICK_PAYMENT_ITEM, UDHAAR_LABEL, type_label
from ..service import (
    MAX_TEXT, PENDING_HOURS, CreditLimitError, DuplicateEntryError, KhataError, KhataService,
)
from .widgets import Card, DateField, fit_columns, make_table, plain_button, primary_button, set_cell

START_CARDS = 1
START_LINES = 2
QTY_W, RATE_W, TOTAL_W, REMOVE_W = 90, 120, 120, 34

PCOL_CUSTOMER, PCOL_TYPE, PCOL_PRODUCT, PCOL_DATE, PCOL_AMOUNT, PCOL_LEFT, PCOL_ACTIONS = range(7)
PENDING_HEADERS = ["Customer", "Type", "Product", "Date", "Amount", "Saves in", ""]


def row_total_paise(quantity_text: str, amount_text: str) -> int | None:
    """Automatic total of one line in paise, or None when the numbers are blank / not valid yet.

    Quantity and Rate both filled -> Quantity x Rate.  Only the amount filled -> that amount.
    """
    amount_text = (amount_text or "").strip()
    quantity_text = (quantity_text or "").strip()
    if not amount_text:
        return None
    try:
        amount = money.rupees_to_paise(amount_text)
        if not quantity_text:
            return amount
        return money.compute_amount_paise(money.parse_quantity(quantity_text), amount)
    except money.MoneyError:
        return None


def line_is_empty(product: str, qty: str, amount: str) -> bool:
    return not ((product or "").strip() or (qty or "").strip() or (amount or "").strip())


def line_values(txn_type: str, txn_date: str, product: str, qty: str, amount: str, notes: str = "") -> dict:
    """The arguments of ``KhataService.add_pending_entry`` for one product line (without ``customer_id``)."""
    qty = (qty or "").strip()
    amount = (amount or "").strip()
    product = (product or "").strip()
    if not product and txn_type == "JAMA":
        product = QUICK_PAYMENT_ITEM
    both = bool(qty and amount)
    return {
        "txn_type": txn_type,
        "txn_date": txn_date,
        "item": product,
        "quantity": qty,
        "rate": amount if both else "",
        "amount": None if both else amount,
        "notes": (notes or "").strip(),
    }


class _NoWheelCombo(QComboBox):
    """A combo inside a scrolling page must not change its value when the mouse wheel only meant to scroll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):  # noqa: N802 (Qt name)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def _enable_touch_scroll(widget) -> None:
    """Finger swipe scrolls the area on touch screens (no effect with a mouse). Never fatal."""
    try:
        QScroller.grabGesture(widget, QScroller.ScrollerGestureType.TouchGesture)
    except Exception:  # pragma: no cover - platform without touch support
        pass


def fill_customer_combo(combo: QComboBox, customers, keep_id=None) -> None:
    typed = combo.currentText()
    if keep_id is None and typed.strip():
        keep_id = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    for s in customers:
        combo.addItem(s.customer.name, s.customer.id)
    index = combo.findData(keep_id) if keep_id is not None else -1
    combo.setCurrentIndex(index)           # -1 = nothing chosen yet
    if index < 0:
        # A name that is typed but not (yet) a customer stays; a chosen customer that no longer exists is cleared.
        combo.setEditText(typed if (keep_id is None and typed.strip()) else "")
    combo.blockSignals(False)


class ProductLine(QWidget):
    """One product of a customer block: Product, Quantity, Rate, Total (auto), remove."""

    changed = Signal()
    removeRequested = Signal(object)
    enterOnRate = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.product = QLineEdit()
        self.product.setPlaceholderText("Product / item")
        self.product.setMaxLength(120)
        self.qty = QLineEdit()
        self.qty.setPlaceholderText("Qty")
        self.qty.setFixedWidth(QTY_W)
        self.rate = QLineEdit()
        self.rate.setPlaceholderText("Rate 0.00")
        self.rate.setFixedWidth(RATE_W)
        self.total = QLineEdit()
        self.total.setReadOnly(True)
        self.total.setPlaceholderText("auto")
        self.total.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.total.setFixedWidth(TOTAL_W)
        self.remove = plain_button("\u2715", danger=True)
        self.remove.setToolTip("Remove this product")
        self.remove.setFixedWidth(REMOVE_W)
        self.remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.product, 1)
        layout.addWidget(self.qty)
        layout.addWidget(self.rate)
        layout.addWidget(self.total)
        layout.addWidget(self.remove)

        self.qty.textChanged.connect(self._recalc)
        self.rate.textChanged.connect(self._recalc)
        self.product.textChanged.connect(lambda _t: self.changed.emit())
        self.remove.clicked.connect(lambda _c=False: self.removeRequested.emit(self))
        self.product.returnPressed.connect(self.qty.setFocus)
        self.qty.returnPressed.connect(self.rate.setFocus)
        self.rate.returnPressed.connect(lambda: self.enterOnRate.emit(self))

    def _recalc(self, _text=None) -> None:
        paise = row_total_paise(self.qty.text(), self.rate.text())
        self.total.setText("" if paise is None else money.format_inr(paise))
        self.changed.emit()

    def is_empty(self) -> bool:
        return line_is_empty(self.product.text(), self.qty.text(), self.rate.text())

    def total_paise(self) -> int:
        return row_total_paise(self.qty.text(), self.rate.text()) or 0

    def clear(self) -> None:
        for edit in (self.product, self.qty, self.rate):
            edit.clear()


class CustomerBlock(Card):
    """Type + Customer + Date, many product lines, and one big scrolling Notes box."""

    changed = Signal()
    removeRequested = Signal(object)

    def __init__(self, customers, parent=None):
        super().__init__(parent=parent)
        self.type_box = _NoWheelCombo()
        self.type_box.addItem(UDHAAR_LABEL, "UDHAAR")
        self.type_box.addItem(JAMA_LABEL, "JAMA")

        self.customer = _NoWheelCombo()
        self.customer.setEditable(True)
        self.customer.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.customer.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.customer.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.customer.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.customer.lineEdit().setPlaceholderText("Customer")
        fill_customer_combo(self.customer, customers)

        self.date = DateField()
        self.remove_block = plain_button("Remove customer", danger=True)
        self.remove_block.setToolTip("Remove this whole customer block")
        self.remove_block.clicked.connect(lambda _c=False: self.removeRequested.emit(self))

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.type_box)
        top.addWidget(self.customer, 1)
        top.addWidget(self.date)
        top.addWidget(self.remove_block)
        self.body.addLayout(top)

        headings = QHBoxLayout()
        headings.setContentsMargins(0, 0, 0, 0)
        headings.setSpacing(8)
        for text, width in (("Product", None), ("Quantity", QTY_W), ("Rate (per unit)", RATE_W),
                            ("Total (auto)", TOTAL_W), ("", REMOVE_W)):
            label = QLabel(text)
            label.setObjectName("muted")
            if width:
                label.setFixedWidth(width)
            headings.addWidget(label, 0 if width else 1)
        self.body.addLayout(headings)

        self.lines_layout = QVBoxLayout()
        self.lines_layout.setSpacing(6)
        self.body.addLayout(self.lines_layout)
        self.lines: list[ProductLine] = []

        self.add_product = plain_button("+ Add product")
        self.add_product.setToolTip("Another product for the same customer")
        self.add_product.clicked.connect(lambda _c=False: self.add_line(focus=True))
        self.block_total = QLabel("")
        self.block_total.setObjectName("h2")
        foot = QHBoxLayout()
        foot.addWidget(self.add_product)
        foot.addStretch(1)
        foot.addWidget(self.block_total)
        self.body.addLayout(foot)

        notes_label = QLabel("Notes (optional) - the box scrolls if the text is long")
        notes_label.setObjectName("muted")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Write notes here. Long text? Scroll or swipe inside the box.")
        self.notes.setMinimumHeight(110)
        self.notes.setMaximumHeight(200)
        self.notes.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.notes.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.notes.textChanged.connect(self._limit_notes)
        _enable_touch_scroll(self.notes.viewport())
        self.body.addWidget(notes_label)
        self.body.addWidget(self.notes)

        self.type_box.currentIndexChanged.connect(lambda _i: self.changed.emit())
        for _ in range(START_LINES):
            self.add_line()

    # ---------------------------------------------------------------- lines
    def add_line(self, focus: bool = False) -> ProductLine:
        line = ProductLine()
        self.lines.append(line)
        self.lines_layout.addWidget(line)
        line.changed.connect(self._update_total)
        line.removeRequested.connect(self.remove_line)
        line.enterOnRate.connect(self._enter_on_rate)
        self._update_total()
        if focus:
            line.product.setFocus()
        return line

    def remove_line(self, line: ProductLine) -> None:
        if line not in self.lines:
            return
        if len(self.lines) == 1:
            line.clear()           # the block always keeps at least one line
        else:
            self.lines.remove(line)
            self.lines_layout.removeWidget(line)
            line.setParent(None)
            line.deleteLater()
        self._update_total()

    def _enter_on_rate(self, line: ProductLine) -> None:
        index = self.lines.index(line) if line in self.lines else -1
        if index == len(self.lines) - 1:
            self.add_line(focus=True)
        elif index >= 0:
            self.lines[index + 1].product.setFocus()

    def filled_lines(self) -> list[ProductLine]:
        return [ln for ln in self.lines if not ln.is_empty()]

    # ---------------------------------------------------------------- state
    def txn_type(self) -> str:
        return self.type_box.currentData()

    def notes_text(self) -> str:
        return self.notes.toPlainText().strip()

    def is_empty(self) -> bool:
        return not self.filled_lines() and not self.notes_text()

    def total_paise(self) -> int:
        return sum(ln.total_paise() for ln in self.lines)

    def _limit_notes(self) -> None:
        text = self.notes.toPlainText()
        if len(text) > MAX_TEXT:
            self.notes.blockSignals(True)
            self.notes.setPlainText(text[:MAX_TEXT])
            cursor = self.notes.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.notes.setTextCursor(cursor)
            self.notes.blockSignals(False)
        self.changed.emit()

    def _update_total(self) -> None:
        filled = len(self.filled_lines())
        self.block_total.setText(f"{filled} product(s)   Total {money.format_inr(self.total_paise())}" if filled else "")
        self.changed.emit()


class DailyEntryPage(QWidget):
    def __init__(self, service: KhataService, on_saved, info, warn, confirm, parent=None, new_customer=None):
        super().__init__(parent)
        self.service = service
        self._on_saved = on_saved
        self._info = info
        self._warn = warn
        self._confirm = confirm
        self._new_customer = new_customer  # callable(name) -> new customer id or None (None = cancelled)
        self._customers: list = []
        self._busy = False
        self.blocks: list[CustomerBlock] = []

        self.blocks_layout = QVBoxLayout()
        self.blocks_layout.setContentsMargins(0, 0, 6, 0)
        self.blocks_layout.setSpacing(12)
        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addLayout(self.blocks_layout)
        holder_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(holder)
        _enable_touch_scroll(self.scroll.viewport())

        self.summary = QLabel("")
        self.summary.setObjectName("h2")
        add_block = plain_button("+ Add customer")
        add_block.setToolTip("Another customer block")
        add_block.clicked.connect(lambda: self.add_block(focus=True))
        clear = plain_button("Clear all")
        clear.clicked.connect(self.clear_all)
        self.new_customer_button = plain_button("+ New customer")
        self.new_customer_button.setToolTip("Add a customer without leaving this page; it is selected in the block you are on")
        self.new_customer_button.clicked.connect(self._new_customer_clicked)
        self.new_customer_button.setVisible(new_customer is not None)
        self.save_button = primary_button("Add entries (saved in 24 hours)")
        self.save_button.clicked.connect(self.save_all)

        bar = QHBoxLayout()
        bar.addWidget(add_block)
        bar.addWidget(clear)
        bar.addWidget(self.new_customer_button)
        bar.addWidget(self.summary, 1)
        bar.addWidget(self.save_button)

        hint = QLabel("Pick a customer, then add as many products as needed (+ Add product, or press Enter in the Rate box). "
                      "Total = Quantity x Rate; leave Quantity empty to enter a single amount, e.g. a payment. "
                      f"Added entries wait in the list below and are saved into the customer's ledger automatically "
                      f"after {PENDING_HOURS} hours. Delete one there if the customer returns the goods.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)

        self.pending_title = QLabel("")
        self.pending_title.setObjectName("h2")
        self.pending_table = make_table(PENDING_HEADERS)
        self.pending_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.pending_table.verticalHeader().setDefaultSectionSize(42)
        fit_columns(self.pending_table, PCOL_PRODUCT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.scroll, 4)
        layout.addLayout(bar)
        layout.addWidget(hint)
        layout.addWidget(self.pending_title)
        layout.addWidget(self.pending_table, 2)

        for _ in range(START_CARDS):
            self.add_block()
        self.refresh_pending()

    # ------------------------------------------------------------ customers
    def set_customers(self, summaries) -> None:
        """Refresh the customer lists in every block (keeps what was already chosen)."""
        self._customers = list(summaries)
        for block in self.blocks:
            fill_customer_combo(block.customer, self._customers)

    # ------------------------------------------------------------ blocks
    def add_block(self, focus: bool = False) -> CustomerBlock:
        block = CustomerBlock(self._customers)
        if self.blocks:                      # same type and date as the block above; the customer is new
            previous = self.blocks[-1]
            block.type_box.setCurrentIndex(previous.type_box.currentIndex())
            block.date.setDate(previous.date.date())
        self.blocks.append(block)
        self.blocks_layout.addWidget(block)
        block.changed.connect(self._update_summary)
        block.removeRequested.connect(self.remove_block)
        self._update_summary()
        if focus:
            block.customer.setFocus()
            self.scroll.ensureWidgetVisible(block)
        return block

    def remove_block(self, block: CustomerBlock) -> None:
        if block not in self.blocks:
            return
        if not block.is_empty() and not self._confirm("Remove customer", "Remove this customer block and everything typed in it?"):
            return
        self.blocks.remove(block)
        self.blocks_layout.removeWidget(block)
        block.setParent(None)
        block.deleteLater()
        if not self.blocks:
            self.add_block()
        self._update_summary()

    def clear_all(self) -> None:
        if self._has_data() and not self._confirm("Clear all", "Remove everything typed on this page?"):
            return
        for block in list(self.blocks):
            self.blocks.remove(block)
            self.blocks_layout.removeWidget(block)
            block.setParent(None)
            block.deleteLater()
        for _ in range(START_CARDS):
            self.add_block()
        self._update_summary()

    def _has_data(self) -> bool:
        return any(not b.is_empty() for b in self.blocks)

    # ------------------------------------------------------------ totals
    def _update_summary(self) -> None:
        count = 0
        udhaar = jama = 0
        for block in self.blocks:
            count += len(block.filled_lines())
            if block.txn_type() == "UDHAAR":
                udhaar += block.total_paise()
            else:
                jama += block.total_paise()
        self.summary.setText(f"{count} entries   |   {UDHAAR_LABEL} {money.format_inr(udhaar)}   "
                             f"{JAMA_LABEL} {money.format_inr(jama)}")

    # ------------------------------------------------------------ customers (typed names / new customer)
    def _customer_id(self, combo: QComboBox) -> int:
        text = combo.currentText().strip()
        if not text:
            raise KhataError("Select a customer")
        index = combo.findText(text, Qt.MatchFlag.MatchFixedString)
        if index < 0 and self._new_customer is not None and self._confirm(
                "New customer", f"There is no customer named '{text}'.\n\nAdd it as a new customer now?"):
            new_id = self._new_customer(text)
            if new_id is not None:
                self._set_combo_customer(combo, new_id)
                index = combo.findData(new_id)
        if index < 0:
            raise KhataError(f"No customer named '{text}'. Pick one from the list.")
        return combo.itemData(index)

    def _set_combo_customer(self, combo: QComboBox, customer_id: int) -> None:
        index = combo.findData(customer_id)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _target_block(self) -> CustomerBlock:
        """The block a new customer goes into: the first block that has data but no customer, else the first block
        with no customer, else the last block."""
        no_customer = [b for b in self.blocks if not b.customer.currentText().strip()]
        for block in no_customer:
            if not block.is_empty():
                return block
        return no_customer[0] if no_customer else self.blocks[-1]

    def _new_customer_clicked(self) -> None:
        if self._new_customer is None or not self.blocks:
            return
        block = self._target_block()
        combo = block.customer
        typed = combo.currentText().strip() if combo.currentIndex() < 0 else ""
        new_id = self._new_customer(typed)
        if new_id is None:
            return
        self._set_combo_customer(block.customer, new_id)   # same widget, lists were refreshed meanwhile
        block.lines[0].product.setFocus()

    # ------------------------------------------------------------ saving
    def _add_pending(self, customer_id: int, values: dict, label: str) -> bool:
        """Queue one product line (it is saved into the ledger after 24 hours). Returns False when the person chose
        not to add it (duplicate / over limit)."""
        if values["quantity"] and not values["rate"]:
            raise KhataError("Enter the Rate (per unit) as well, or clear the Quantity")
        allow_duplicate = False
        allow_over_limit = False
        while True:
            try:
                self.service.add_pending_entry(customer_id=customer_id, allow_duplicate=allow_duplicate,
                                               allow_over_limit=allow_over_limit, **values)
                return True
            except DuplicateEntryError as exc:
                if allow_duplicate or not self._confirm("Possible duplicate", f"{label}: {exc}\n\nAdd it again anyway?"):
                    return False
                allow_duplicate = True
            except CreditLimitError as exc:
                if allow_over_limit or not self._confirm("Credit limit exceeded", f"{label}: {exc}\n\nAdd this entry anyway?"):
                    return False
                allow_over_limit = True

    def save_all(self) -> None:
        if self._busy:
            return
        blocks = [b for b in self.blocks if not b.is_empty()]
        if not blocks:
            self._info("Nothing to save", "Type at least one entry first.")
            return
        self._busy = True
        self.save_button.setEnabled(False)
        added = 0
        skipped = 0
        error: str | None = None
        try:
            for block in blocks:
                number = self.blocks.index(block) + 1
                lines = block.filled_lines()
                if not lines:
                    error = f"Customer {number}: add at least one product (or clear the notes)"
                    break
                try:
                    customer_id = self._customer_id(block.customer)
                except KhataError as exc:
                    error = f"Customer {number}: {exc}"
                    break
                stop = False
                for line in lines:
                    label = f"Customer {number}, product {block.lines.index(line) + 1}"
                    try:
                        values = line_values(block.txn_type(), block.date.text_dmy(), line.product.text(),
                                             line.qty.text(), line.rate.text(), block.notes_text())
                        if self._add_pending(customer_id, values, label):
                            added += 1
                            block.remove_line(line)      # saved: gone from the page
                            block.notes.clear()          # the notes went along with this entry; do not repeat them
                        else:
                            skipped += 1
                    except KhataError as exc:
                        error = f"{label}: {exc}"
                        stop = True
                        break
                if not block.filled_lines() and not block.notes_text():
                    self.remove_block(block)             # fully added -> block disappears (empty, so no question)
                if stop:
                    break
            if added:
                self._on_saved()
            self._update_summary()
            if error:
                self._warn("Cannot add", f"{error}\n\n{added} entries before it were added. "
                                         "Fix this one and press the button again.")
            else:
                message = (f"{added} entries added. They will be saved into the customers' ledgers "
                           f"automatically after {PENDING_HOURS} hours.\nUntil then you can delete them from the "
                           "list below.")
                if skipped:
                    message += f"\n{skipped} entry(ies) were not added and are still on the page."
                self._info("Added", message)
        finally:
            self._busy = False
            self.save_button.setEnabled(True)

    # ------------------------------------------------------------ waiting list (24 hours)
    def refresh_pending(self) -> None:
        """Reload the list of rows that are waiting to be saved (also updates the 'Saves in' countdown)."""
        try:
            pending = self.service.list_pending()
        except KhataError:
            pending = []
        table = self.pending_table
        table.setRowCount(0)
        for p in pending:
            row = table.rowCount()
            table.insertRow(row)
            set_cell(table, row, PCOL_CUSTOMER, p.customer_name)
            set_cell(table, row, PCOL_TYPE, type_label(p.txn_type))
            set_cell(table, row, PCOL_PRODUCT, p.item)
            set_cell(table, row, PCOL_DATE, dates.format_date(p.txn_date))
            set_cell(table, row, PCOL_AMOUNT, money.format_inr(p.amount_paise), right=True)
            set_cell(table, row, PCOL_LEFT, viewmodel.time_left_text(self.service.seconds_until_post(p)))

            box = QWidget()
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(4, 2, 4, 2)
            box_layout.setSpacing(6)
            save_now = plain_button("Save now")
            save_now.setToolTip("Put this entry into the customer's ledger right away")
            save_now.clicked.connect(lambda _c=False, pid=p.id: self._save_pending_now(pid))
            delete = plain_button("Delete", danger=True)
            delete.setToolTip("Remove this entry. It will not be saved in the ledger (e.g. goods returned)")
            delete.clicked.connect(lambda _c=False, pid=p.id: self._delete_pending(pid))
            box_layout.addWidget(save_now)
            box_layout.addWidget(delete)
            table.setCellWidget(row, PCOL_ACTIONS, box)
        if pending:
            self.pending_title.setText(f"Waiting to be saved ({len(pending)}) – saved into the ledger automatically "
                                       f"after {PENDING_HOURS} hours")
        else:
            self.pending_title.setText("Waiting to be saved – nothing right now")

    def _describe(self, p) -> str:
        return (f"{p.customer_name}\n{type_label(p.txn_type)}  {money.format_inr(p.amount_paise)}  –  {p.item}\n"
                f"Date {dates.format_date(p.txn_date)}")

    def _delete_pending(self, pending_id: int) -> None:
        try:
            p = self.service.get_pending_entry(pending_id)
        except KhataError as exc:
            self._warn("Cannot delete", str(exc))
            self.refresh_pending()
            return
        if not self._confirm("Delete entry", f"Delete this entry?\n\n{self._describe(p)}\n\n"
                                              "It will NOT be saved in the customer's ledger."):
            return
        try:
            self.service.delete_pending(pending_id)
        except KhataError as exc:
            self._warn("Cannot delete", str(exc))
        self.refresh_pending()

    def _save_pending_now(self, pending_id: int) -> None:
        try:
            p = self.service.get_pending_entry(pending_id)
        except KhataError as exc:
            self._warn("Cannot save", str(exc))
            self.refresh_pending()
            return
        if not self._confirm("Save now", f"Put this entry into the customer's ledger now?\n\n{self._describe(p)}"):
            return
        try:
            self.service.post_pending(pending_id)
        except KhataError as exc:
            self._warn("Cannot save", str(exc))
            self.refresh_pending()
            return
        self._on_saved()  # refreshes the whole window, including this list
