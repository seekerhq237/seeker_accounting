"""Print and export service for Treasury Transactions and Transaction Register.

Handles all three output formats (PDF, Word, Excel) for:
  - Single treasury transaction detail document
  - Treasury transaction register list
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from seeker_accounting.modules.companies.dto.company_dto import CompanyDetailDTO
from seeker_accounting.modules.treasury.dto.treasury_transaction_dto import (
    TreasuryTransactionDetailDTO,
    TreasuryTransactionListItemDTO,
)
from seeker_accounting.platform.printing.html_builder import (
    build_company_header,
    build_data_table,
    build_document_title_block,
    build_key_value_grid,
    build_section_title,
    build_summary_box,
    fmt_decimal,
    h,
    wrap_html,
)
from seeker_accounting.platform.printing.print_data_protocol import (
    CompanyHeaderData,
    PageSize,
    PrintExportResult,
    PrintFormat,
)

if TYPE_CHECKING:
    from seeker_accounting.modules.companies.services.company_logo_service import CompanyLogoService
    from seeker_accounting.modules.companies.services.company_service import CompanyService
    from seeker_accounting.modules.treasury.services.treasury_transaction_service import TreasuryTransactionService
    from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder
    from seeker_accounting.platform.printing.print_engine import PrintEngine
    from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder


class TreasuryTransactionPrintService:
    """Renders treasury transaction documents to PDF, Word, or Excel."""

    def __init__(
        self,
        print_engine: "PrintEngine",
        treasury_transaction_service: "TreasuryTransactionService",
        company_service: "CompanyService",
        company_logo_service: "CompanyLogoService",
    ) -> None:
        self._engine = print_engine
        self._txn_service = treasury_transaction_service
        self._company_service = company_service
        self._logo_service = company_logo_service

    # ── Public API ──────────────────────────────────────────────────────────────

    def print_transaction(
        self,
        company_id: int,
        transaction_id: int,
        result: PrintExportResult,
    ) -> None:
        """Render a single treasury transaction to the chosen format and path."""
        txn = self._txn_service.get_treasury_transaction(company_id, transaction_id)
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._detail_html(header, txn, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._detail_word(header, txn, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._detail_excel(header, txn, result.page_size, result.orientation)
            wb.save(result.output_path)

    def print_transaction_list(
        self,
        company_id: int,
        transactions: list[TreasuryTransactionListItemDTO],
        result: PrintExportResult,
    ) -> None:
        """Render the transaction register (list) to the chosen format and path."""
        company = self._company_service.get_company(company_id)
        header = self._make_company_header(company)

        if result.format == PrintFormat.PDF:
            html = self._list_html(header, transactions, result.page_size)
            self._engine.render_pdf(
                html, result.output_path,
                page_size=result.page_size,
                orientation=result.orientation,
            )
        elif result.format == PrintFormat.WORD:
            doc = self._list_word(header, transactions, result.page_size, result.orientation)
            doc.save(result.output_path)
        else:
            wb = self._list_excel(header, transactions, result.page_size, result.orientation)
            wb.save(result.output_path)

    # ── Company header ──────────────────────────────────────────────────────────

    def _make_company_header(self, company: CompanyDetailDTO) -> CompanyHeaderData:
        logo_path: str | None = None
        if company.logo_storage_path:
            resolved = self._logo_service.resolve_logo_path(company.logo_storage_path)
            if resolved:
                logo_path = str(resolved)
        return CompanyHeaderData(
            name=company.display_name,
            legal_name=(
                company.legal_name
                if company.legal_name and company.legal_name != company.display_name
                else None
            ),
            address_line_1=company.address_line_1,
            address_line_2=company.address_line_2,
            city=company.city,
            region=company.region,
            country=company.country_code,
            phone=company.phone,
            email=company.email,
            tax_identifier=company.tax_identifier,
            registration_number=company.registration_number,
            logo_path=logo_path,
        )

    # ── Formatting helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _fmt_date(d: date | None) -> str:
        return d.strftime("%d/%m/%Y") if d else "—"

    @staticmethod
    def _fmt_amount(v: Decimal | None) -> str:
        return fmt_decimal(v) if v is not None else "—"

    # ── Detail HTML ─────────────────────────────────────────────────────────────

    def _detail_html(
        self,
        company: CompanyHeaderData,
        txn: TreasuryTransactionDetailDTO,
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block("Treasury Transaction", subtitle=txn.transaction_number),
            build_key_value_grid([
                ("Transaction #", txn.transaction_number),
                ("Type", txn.transaction_type_code.replace("_", " ").title()),
                ("Financial Account", txn.financial_account_name),
                ("Date", self._fmt_date(txn.transaction_date)),
                ("Currency", txn.currency_code),
                ("Exchange Rate", str(txn.exchange_rate) if txn.exchange_rate else "—"),
                ("Reference", txn.reference_number or "—"),
                ("Status", txn.status_code.title()),
            ]),
        ]

        if txn.lines:
            parts.append(build_section_title("Line Items"))
            line_cols = ["#", "Account", "Description", "Amount"]
            line_rows = [
                [
                    str(ln.line_number),
                    f"{ln.account_code} — {ln.account_name}",
                    ln.line_description or "",
                    self._fmt_amount(ln.amount),
                ]
                for ln in txn.lines
            ]
            trailing = ["", "", "TOTAL", self._fmt_amount(txn.total_amount)]
            parts.append(build_data_table(
                line_cols, line_rows,
                numeric_columns={3},
                total_row=trailing,
            ))

        summary = build_summary_box([
            ("Total Amount", self._fmt_amount(txn.total_amount)),
        ], highlight_last=False)
        parts.append(
            '<table style="width:100%;"><tr>'
            '<td style="vertical-align:top;width:50%;"></td>'
            f'<td style="vertical-align:top;width:50%;">{summary}</td>'
            '</tr></table>'
        )

        if txn.description:
            parts.append(build_section_title("Description"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(txn.description)}</p>'
            )
        if txn.notes:
            parts.append(build_section_title("Notes"))
            parts.append(
                f'<p style="font-size:9pt;color:#444;margin:4px 0;">{h(txn.notes)}</p>'
            )

        return wrap_html("".join(parts), page_size=page_size)

    # ── Detail Word ─────────────────────────────────────────────────────────────

    def _detail_word(
        self,
        company: CompanyHeaderData,
        txn: TreasuryTransactionDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title("Treasury Transaction", subtitle=txn.transaction_number)
        doc.add_key_value_grid([
            ("Transaction #", txn.transaction_number),
            ("Type", txn.transaction_type_code.replace("_", " ").title()),
            ("Financial Account", txn.financial_account_name),
            ("Date", self._fmt_date(txn.transaction_date)),
            ("Currency", txn.currency_code),
            ("Exchange Rate", str(txn.exchange_rate) if txn.exchange_rate else "—"),
            ("Reference", txn.reference_number or "—"),
            ("Status", txn.status_code.title()),
        ])

        if txn.lines:
            doc.add_section_title("Line Items")
            line_cols = ["#", "Account", "Description", "Amount"]
            line_rows = [
                [
                    str(ln.line_number),
                    f"{ln.account_code} — {ln.account_name}",
                    ln.line_description or "",
                    self._fmt_amount(ln.amount),
                ]
                for ln in txn.lines
            ]
            doc.add_data_table(
                line_cols, line_rows,
                numeric_columns={3},
                total_row=["", "", "TOTAL", self._fmt_amount(txn.total_amount)],
            )

        doc.add_summary_pairs([
            ("Total Amount", self._fmt_amount(txn.total_amount)),
        ])

        if txn.description:
            doc.add_section_title("Description")
            doc.add_paragraph(txn.description, italic=True)
        if txn.notes:
            doc.add_section_title("Notes")
            doc.add_paragraph(txn.notes, italic=True)
        return doc

    # ── Detail Excel ────────────────────────────────────────────────────────────

    def _detail_excel(
        self,
        company: CompanyHeaderData,
        txn: TreasuryTransactionDetailDTO,
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Transaction")
        sh.write_document_header(company, f"Treasury Transaction — {txn.transaction_number}")
        sh.write_key_value_pairs([
            ("Type", txn.transaction_type_code.replace("_", " ").title()),
            ("Financial Account", txn.financial_account_name),
            ("Date", self._fmt_date(txn.transaction_date)),
            ("Currency", txn.currency_code),
            ("Exchange Rate", str(txn.exchange_rate) if txn.exchange_rate else "—"),
            ("Reference", txn.reference_number or "—"),
            ("Status", txn.status_code.title()),
        ])
        sh.write_blank_row()
        sh.write_table_header(["#", "Account", "Description", "Amount"])
        for ln in txn.lines:
            sh.write_table_row([
                ln.line_number,
                f"{ln.account_code} — {ln.account_name}",
                ln.line_description or "",
                ln.amount,
            ], numeric_columns={3})
        sh.write_totals_row(["", "", "Total", txn.total_amount])
        sh.write_branded_footer()
        return wb

    # ── List HTML ───────────────────────────────────────────────────────────────

    def _list_html(
        self,
        company: CompanyHeaderData,
        transactions: list[TreasuryTransactionListItemDTO],
        page_size: PageSize,
    ) -> str:
        parts: list[str] = [
            build_company_header(company),
            build_document_title_block(
                "Treasury Transaction Register",
                subtitle=f"{len(transactions)} transaction(s)",
            ),
        ]
        cols = ["Number", "Type", "Financial Account", "Date", "Currency", "Amount", "Status", "Reference"]
        rows = [
            [
                t.transaction_number,
                t.transaction_type_code.replace("_", " ").title(),
                t.financial_account_name,
                self._fmt_date(t.transaction_date),
                t.currency_code,
                self._fmt_amount(t.total_amount),
                t.status_code.title(),
                t.reference_number or "",
            ]
            for t in transactions
        ]
        total_amount = sum(t.total_amount for t in transactions)
        total_row = [
            f"{len(transactions)} transactions", "", "", "", "",
            fmt_decimal(total_amount),
            "", "",
        ]
        parts.append(build_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=total_row,
            nowrap_columns={0, 1, 3, 4, 6},
            column_widths={
                0: "14%",
                1: "14%",
                2: "20%",
                3: "10%",
                4: "8%",
                5: "10%",
                6: "8%",
                7: "16%",
            },
        ))
        return wrap_html("".join(parts), page_size=page_size)

    # ── List Word ───────────────────────────────────────────────────────────────

    def _list_word(
        self,
        company: CompanyHeaderData,
        transactions: list[TreasuryTransactionListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "WordDocumentBuilder":
        from seeker_accounting.platform.printing.word_builder import WordDocumentBuilder

        doc = WordDocumentBuilder(page_size=page_size, orientation=orientation)
        doc.add_company_header(company)
        doc.add_document_title(
            "Treasury Transaction Register",
            subtitle=f"{len(transactions)} transaction(s)",
        )
        cols = ["Number", "Type", "Financial Account", "Date", "Currency", "Amount", "Status", "Reference"]
        rows = [
            [
                t.transaction_number,
                t.transaction_type_code.replace("_", " ").title(),
                t.financial_account_name,
                self._fmt_date(t.transaction_date),
                t.currency_code,
                self._fmt_amount(t.total_amount),
                t.status_code.title(),
                t.reference_number or "",
            ]
            for t in transactions
        ]
        total_amount = sum(t.total_amount for t in transactions)
        doc.add_data_table(
            cols, rows,
            numeric_columns={5},
            total_row=[
                f"{len(transactions)} transactions", "", "", "", "",
                fmt_decimal(total_amount),
                "", "",
            ],
        )
        return doc

    # ── List Excel ──────────────────────────────────────────────────────────────

    def _list_excel(
        self,
        company: CompanyHeaderData,
        transactions: list[TreasuryTransactionListItemDTO],
        page_size: PageSize,
        orientation,
    ) -> "ExcelWorkbookBuilder":
        from seeker_accounting.platform.printing.excel_builder import ExcelWorkbookBuilder

        wb = ExcelWorkbookBuilder(page_size=page_size, orientation=orientation)
        sh = wb.add_sheet("Transaction Register")
        sh.write_document_header(company, "Treasury Transaction Register")
        sh.write_blank_row()
        sh.write_table_header([
            "Number", "Type", "Financial Account", "Date", "Currency", "Amount", "Status", "Reference",
        ])
        for t in transactions:
            sh.write_table_row([
                t.transaction_number,
                t.transaction_type_code.replace("_", " ").title(),
                t.financial_account_name,
                self._fmt_date(t.transaction_date),
                t.currency_code,
                t.total_amount,
                t.status_code.title(),
                t.reference_number or "",
            ], numeric_columns={5})
        sh.write_totals_row([
            f"{len(transactions)} transactions", "", "", "", "",
            sum(t.total_amount for t in transactions),
            "", "",
        ])
        sh.write_branded_footer()
        sh.set_column_widths({1: 16, 2: 16, 3: 24, 4: 14, 5: 10, 6: 18, 7: 10, 8: 16})
        return wb
