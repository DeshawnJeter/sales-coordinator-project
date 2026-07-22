"""Tkinter desktop GUI: load files -> validate -> generate report -> view -> export.

No command line, no config files, no raw error text — every failure the user
can hit is shown as a plain-English messagebox.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import export, ingestion, summary, validation

FILETYPES = [
    ('Sales data files', '*.csv *.tsv *.xlsx *.xls'),
    ('CSV files', '*.csv'),
    ('Excel files', '*.xlsx *.xls'),
    ('Tab-separated files', '*.tsv'),
    ('All files', '*.*'),
]

DECLINE_THRESHOLD_DEFAULT = 10  # percent, shown/edited in the GUI as a whole number


class SalesSummaryApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Weekly Sales Summary')
        self.root.geometry('720x520')

        # filename -> {"ok": bool, "message": str or None, "dataframe": df or None}
        self.loaded_files = {}
        self.report = None

        self._build_load_screen()

    # ---------- Load / validate screen ----------

    def _build_load_screen(self):
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill='both', expand=True)

        title = ttk.Label(container, text='Weekly Sales Summary', font=('Segoe UI', 16, 'bold'))
        title.pack(anchor='w')
        subtitle = ttk.Label(
            container,
            text='Load one or more sales export files (CSV, TSV, or Excel), then generate this week\'s report.',
            wraplength=680,
        )
        subtitle.pack(anchor='w', pady=(2, 12))

        button_row = ttk.Frame(container)
        button_row.pack(fill='x', pady=(0, 10))

        ttk.Button(button_row, text='Load Data Files...', command=self._on_load_files).pack(side='left')
        ttk.Button(button_row, text='Remove Selected', command=self._on_remove_selected).pack(side='left', padx=8)
        ttk.Button(button_row, text='Clear All', command=self._on_clear_all).pack(side='left')

        threshold_row = ttk.Frame(container)
        threshold_row.pack(fill='x', pady=(0, 10))
        ttk.Label(threshold_row, text='Flag a decline when sales drop more than').pack(side='left')
        self.threshold_var = tk.StringVar(value=str(DECLINE_THRESHOLD_DEFAULT))
        ttk.Entry(threshold_row, textvariable=self.threshold_var, width=4).pack(side='left', padx=4)
        ttk.Label(threshold_row, text='%').pack(side='left')

        list_frame = ttk.Frame(container)
        list_frame.pack(fill='both', expand=True)

        columns = ('status', 'filename', 'detail')
        self.file_tree = ttk.Treeview(list_frame, columns=columns, show='headings', selectmode='browse')
        self.file_tree.heading('status', text='Status')
        self.file_tree.heading('filename', text='File')
        self.file_tree.heading('detail', text='Details')
        self.file_tree.column('status', width=70, anchor='center')
        self.file_tree.column('filename', width=180)
        self.file_tree.column('detail', width=420)
        self.file_tree.pack(side='left', fill='both', expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.file_tree.yview)
        self.file_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side='right', fill='y')

        self.file_tree.tag_configure('fail', background='#fde2e2')
        self.file_tree.tag_configure('ok', background='#e3f7e3')

        bottom_row = ttk.Frame(container)
        bottom_row.pack(fill='x', pady=(12, 0))
        self.status_label = ttk.Label(bottom_row, text='No files loaded yet.')
        self.status_label.pack(side='left')

        self.generate_button = ttk.Button(
            bottom_row, text='Generate Report', command=self._on_generate_report, state='disabled'
        )
        self.generate_button.pack(side='right')

    def _on_load_files(self):
        paths = filedialog.askopenfilenames(title='Select sales data files', filetypes=FILETYPES)
        if not paths:
            return

        loaded = ingestion.load_files(paths)
        results = validation.validate_loaded_files(loaded)

        failed_messages = []
        for filename, result in results.items():
            self.loaded_files[filename] = result
            if not result['ok']:
                failed_messages.append(result['message'])

        self._refresh_file_list()

        if failed_messages:
            messagebox.showerror(
                'Some files have problems',
                '\n\n'.join(failed_messages) + '\n\nFix these files or remove them before generating a report.',
            )

    def _on_remove_selected(self):
        selection = self.file_tree.selection()
        if not selection:
            return
        for item_id in selection:
            filename = self.file_tree.item(item_id, 'values')[1]
            self.loaded_files.pop(filename, None)
        self._refresh_file_list()

    def _on_clear_all(self):
        self.loaded_files = {}
        self._refresh_file_list()

    def _refresh_file_list(self):
        self.file_tree.delete(*self.file_tree.get_children())
        for filename, result in self.loaded_files.items():
            status = 'OK' if result['ok'] else 'Problem'
            detail = 'Ready to use' if result['ok'] else result['message'].split('\n', 1)[-1].replace('• ', '')
            tag = 'ok' if result['ok'] else 'fail'
            self.file_tree.insert('', 'end', values=(status, filename, detail), tags=(tag,))

        total = len(self.loaded_files)
        failing = sum(1 for r in self.loaded_files.values() if not r['ok'])
        if total == 0:
            self.status_label.config(text='No files loaded yet.')
        elif failing:
            self.status_label.config(text=f'{total} file(s) loaded — {failing} have problems and must be fixed or removed.')
        else:
            self.status_label.config(text=f'{total} file(s) loaded and ready.')

        can_generate = total > 0 and failing == 0
        self.generate_button.config(state='normal' if can_generate else 'disabled')

    # ---------- Generate report ----------

    def _on_generate_report(self):
        valid_dataframes = [r['dataframe'] for r in self.loaded_files.values() if r['ok']]
        if not valid_dataframes:
            messagebox.showwarning('No data', 'Load at least one valid file before generating a report.')
            return

        try:
            threshold_pct = float(self.threshold_var.get())
        except ValueError:
            threshold_pct = DECLINE_THRESHOLD_DEFAULT
        threshold = max(threshold_pct, 0) / 100

        try:
            combined = ingestion.combine_dataframes(valid_dataframes)
            report = summary.build_report(combined, threshold=threshold)
        except Exception:
            messagebox.showerror(
                'Could not generate report',
                'Something went wrong while building the report. Please double-check that your '
                'files have valid dates and numbers in the sales, discount, and profit columns.',
            )
            return

        self.report = report
        self._show_report_window(report)

    # ---------- Report view ----------

    def _show_report_window(self, report):
        window = tk.Toplevel(self.root)
        window.title('Weekly Sales Report')
        window.geometry('820x640')

        container = ttk.Frame(window, padding=16)
        container.pack(fill='both', expand=True)

        period_text = self._format_period_text(report)
        ttk.Label(container, text='Weekly Sales Report', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(container, text=period_text, foreground='#555').pack(anchor='w', pady=(0, 10))

        paragraph_frame = ttk.Frame(container, padding=10, relief='groove')
        paragraph_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(paragraph_frame, text=report['paragraph'], wraplength=760, justify='left').pack(anchor='w')

        self._build_stat_row(container, report)

        if report['flags']:
            self._build_flags_box(container, report['flags'])

        notebook = ttk.Notebook(container)
        notebook.pack(fill='both', expand=True, pady=(10, 0))

        self._build_breakdown_tab(notebook, 'By Region', report['region_rows'])
        self._build_breakdown_tab(notebook, 'By Category', report['category_rows'])
        self._build_breakdown_tab(notebook, 'By Store', report['store_rows'])
        self._build_discount_tab(notebook, report['discount_rows'])

        export_row = ttk.Frame(container)
        export_row.pack(fill='x', pady=(10, 0))
        ttk.Button(export_row, text='Export / Share Report...', command=lambda: self._on_export(report)).pack(side='right')

    def _format_period_text(self, report):
        current = report['current_period']
        text = f"Current week: {current[0].strftime('%b %d, %Y')} - {current[1].strftime('%b %d, %Y')}"
        if report['has_prior_data']:
            prior = report['prior_period']
            text += f"   |   Prior week: {prior[0].strftime('%b %d, %Y')} - {prior[1].strftime('%b %d, %Y')}"
        else:
            text += '   |   No prior week data available for comparison'
        return text

    def _build_stat_row(self, parent, report):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 10))
        stats = [
            ('Total Sales', report['current_totals']['sales'], report['totals_change']['sales'], True),
            ('Total Profit', report['current_totals']['profit'], report['totals_change']['profit'], True),
            ('Total Orders', report['current_totals']['orders'], report['totals_change']['orders'], False),
        ]
        for label, value, change, is_currency in stats:
            card = ttk.Frame(row, padding=10, relief='ridge')
            card.pack(side='left', fill='x', expand=True, padx=4)
            ttk.Label(card, text=label, foreground='#666').pack(anchor='w')
            value_text = f"${value:,.0f}" if is_currency else f"{value:,.0f}"
            ttk.Label(card, text=value_text, font=('Segoe UI', 14, 'bold')).pack(anchor='w')
            change_text = 'No prior week to compare' if change is None else f"{change * 100:+.1f}% vs. last week"
            ttk.Label(card, text=change_text).pack(anchor='w')

    def _build_flags_box(self, parent, flags):
        box = ttk.Frame(parent, padding=10, relief='solid')
        box.pack(fill='x', pady=(0, 10))
        ttk.Label(box, text=f'Flagged Issues ({len(flags)})', font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        for flag in flags:
            ttk.Label(box, text='• ' + self._flag_text(flag), wraplength=760, justify='left').pack(anchor='w')

    @staticmethod
    def _flag_text(flag):
        kind = flag['kind']
        if kind == 'margin':
            return (f"{flag['name']}: margin down {abs(flag['change']) * 100:.0f}% vs. typical "
                    f"({flag['margin_now'] * 100:.0f}% now vs {flag['margin_typical'] * 100:.0f}% typical)")
        label = {'region': 'Region', 'category': 'Category', 'store': 'Store', 'product': 'Product'}[kind]
        return f"{label} — {flag['name']}: sales down {abs(flag['change']) * 100:.0f}% vs. prior period"

    def _build_breakdown_tab(self, notebook, title, rows):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=title)

        columns = ('name', 'sales', 'profit', 'orders', 'change')
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        for col, label, width in [
            ('name', title.replace('By ', ''), 160), ('sales', 'Sales', 110), ('profit', 'Profit', 110),
            ('orders', 'Orders', 80), ('change', 'Change vs. Prior', 130),
        ]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor='center' if col != 'name' else 'w')
        tree.pack(fill='both', expand=True)
        tree.tag_configure('flag', background='#fde2e2')

        for r in rows:
            change_text = 'N/A' if r['sales_change'] is None else f"{r['sales_change'] * 100:+.1f}%"
            tag = 'flag' if (r['sales_change'] is not None and r['sales_change'] <= -0.10) else ''
            tree.insert('', 'end', values=(r['name'], f"${r['sales']:,.0f}", f"${r['profit']:,.0f}",
                                            r['orders'], change_text), tags=(tag,) if tag else ())

    def _build_discount_tab(self, notebook, rows):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text='Discounted Products')

        columns = ('product', 'discount', 'sales', 'margin_now', 'margin_typical', 'impact')
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        for col, label, width in [
            ('product', 'Product', 160), ('discount', 'Avg. Discount', 100), ('sales', 'Sales', 100),
            ('margin_now', 'Margin Now', 100), ('margin_typical', 'Typical Margin', 110),
            ('impact', 'Profit Impact', 140),
        ]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor='center' if col != 'product' else 'w')
        tree.pack(fill='both', expand=True)
        tree.tag_configure('flag', background='#fde2e2')

        for r in rows:
            margin_typical_text = 'N/A' if r['margin_typical'] is None else f"{r['margin_typical'] * 100:.0f}%"
            tag = 'flag' if (r['margin_change'] is not None and r['margin_change'] <= -0.15) else ''
            tree.insert('', 'end', values=(
                r['label'], f"{r['avg_discount'] * 100:.0f}%", f"${r['sales']:,.0f}",
                f"{r['margin_now'] * 100:.0f}%", margin_typical_text, r['impact_label'],
            ), tags=(tag,) if tag else ())

        if not rows:
            ttk.Label(frame, text='No discounted products found this period.').pack(anchor='w', pady=8)

    def _on_export(self, report):
        path = filedialog.asksaveasfilename(
            title='Save Report As',
            defaultextension='.xlsx',
            filetypes=[('Excel workbook', '*.xlsx')],
            initialfile='Weekly Sales Report.xlsx',
        )
        if not path:
            return
        try:
            export.export_report_to_excel(report, path)
        except Exception:
            messagebox.showerror(
                'Could not save report',
                'The report could not be saved. Make sure the file isn\'t open in another program '
                'and that you have permission to save to that location, then try again.',
            )
            return
        messagebox.showinfo('Report saved', f'Report saved to:\n{os.path.abspath(path)}')


def run():
    root = tk.Tk()
    SalesSummaryApp(root)
    root.mainloop()
