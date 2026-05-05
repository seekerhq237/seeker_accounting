# UI Inline Styles & Hardcoded Color Audit (Phase 1)

Scope: every match of `setStyleSheet(`, hex color (`#RRGGBB`), or `rgb(`/`rgba(`
inside `src/seeker_accounting/**/*.py`, excluding the design-system files
(`shared/ui/styles/tokens.py`, `palette.py`, `qss_builder.py`).

This is a catalogue only. **Do not** fix these as part of Phase 1 / Task A;
each entry should be migrated in later tasks to the new tokens / palette /
QSS rules introduced here.

## Recommended replacement targets

| Hardcoded pattern                  | Recommended replacement                                                                                  |
|------------------------------------|----------------------------------------------------------------------------------------------------------|
| status / chip color pairs          | `palette.status_<family>_{bg,fg,border}` via `QWidget#StatusChip[chipFamily=success|warning|danger|info|neutral|accent]` |
| toolbar / command surfaces         | `palette.command_bar_*` via `QWidget#CommandBar` / `QToolButton#CommandBarButton` / `QFrame#CommandBarSeparator`         |
| table header / row stripe colors   | `palette.data_table_*` via `QTableView#EnterpriseTable` + `QWidget#DataTableToolbar`                                     |
| generic surface / border           | existing `palette.{workspace_surface,secondary_surface,border_default,border_strong,divider_subtle}`                     |
| generic text                       | existing `palette.{text_primary,text_secondary,text_muted}`                                                              |
| accent / brand                     | existing `palette.{accent,accent_hover,accent_soft,accent_soft_strong,accent_text}`                                      |
| magic px sizes for chip/cmd/table  | corresponding new `SizeTokens` field (`chip_*`, `command_bar_*`, `data_table_*`)                                         |

**Total flagged lines:** 675 across 116 files.

---

## `src/seeker_accounting/app/entry/get_started_window.py`

- L48: `_BG = "#F5F7FB"` -> replace hex with palette field
- L49: `_SURFACE = "#FFFFFF"` -> replace hex with palette field
- L50: `_RAISED = "#FFFFFF"` -> replace hex with palette field
- L51: `_CARD = "#F8FAFD"` -> replace hex with palette field
- L52: `_BORDER = "#D9E2EC"` -> replace hex with palette field
- L53: `_BORDER_STRONG = "#C5D0DD"` -> replace hex with palette field
- L54: `_TEXT = "#182230"` -> replace hex with palette field
- L55: `_TEXT_SEC = "#526071"` -> replace hex with palette field
- L56: `_TEXT_MUTED = "#7A8797"` -> replace hex with palette field
- L57: `_ACCENT = "#2363EA"` -> replace hex with palette field
- L58: `_ACCENT_HOVER = "#1B55D1"` -> replace hex with palette field
- L59: `_ACCENT_SOFT = "#F3F7FF"` -> replace hex with palette field
- L60: `_SUCCESS = "#13795B"` -> replace hex with palette field
- L61: `_WARNING = "#B7791F"` -> replace hex with palette field
- L62: `_DANGER = "#C53030"` -> replace hex with palette field
- L63: `_INFO = "#2563EB"` -> replace hex with palette field
- L64: `_DIVIDER = "#E5EBF3"` -> replace hex with palette field
- L169: `color: #FFFFFF;` -> replace hex with palette field
- L210: `color: #FFFFFF;` -> replace hex with palette field
- L329: `lbl.setStyleSheet(f"font-size: {size - 4}px; background: transparent; border: none;")` -> move to QSS rule + objectName; reference palette/tokens
- L357: `badge.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L358: `f"background: {_ACCENT}; color: #FFFFFF; border-radius: 18px; "` -> replace hex with palette field
- L387: `icon_lbl.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L399: `title_lbl.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L440: `name_lbl.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L446: `desc_lbl.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L516: `self.setStyleSheet(_QSS)` -> move to QSS rule + objectName; reference palette/tokens
- L554: `bottom.setStyleSheet(f"background: {_CARD}; border-top: 1px solid {_DIVIDER};")` -> move to QSS rule + objectName; reference palette/tokens
- L563: `self._btn_skip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L574: `self._btn_back.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L601: `self._btn_next.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L602: `f'QPushButton {{ background: {_ACCENT}; color: #FFFFFF; border: none;'` -> replace hex with palette field
- L630: `hero_icon.setStyleSheet("font-size: 56px; background: transparent;")` -> move to QSS rule + objectName; reference palette/tokens
- L664: `badge_frame.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L672: `badge_text.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L973: `icon.setStyleSheet("font-size: 52px; background: transparent;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/app/entry/splash_screen.py`

- L31: `_BG_COLOR = QColor("#F7F8FC")` -> replace hex with palette field
- L32: `_TITLEBAR_BG = QColor("#E6EAF2")` -> replace hex with palette field
- L33: `_BADGE_BLUE = QColor("#2F66E8")` -> replace hex with palette field
- L34: `_BADGE_GLOW = QColor("#5A86F2")` -> replace hex with palette field
- L35: `_TEXT_COLOR = QColor("#182230")` -> replace hex with palette field
- L36: `_TEXT_SECONDARY = QColor("#526071")` -> replace hex with palette field
- L37: `_TEXT_MUTED = QColor("#7A8797")` -> replace hex with palette field
- L38: `_STATUS_COLOR = QColor("#8E99A8")` -> replace hex with palette field
- L39: `_WHITE = QColor("#FFFFFF")` -> replace hex with palette field
- L414: `label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L427: `label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L441: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L447: `f"QPushButton:hover {{ background-color: #2558CC; }}"` -> replace hex with palette field
- L448: `f"QPushButton:pressed {{ background-color: #1E4BB5; }}"` -> replace hex with palette field
- L459: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L475: `label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L489: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L491: `"QPushButton:hover { background: rgba(0,0,0,0.04); border-radius: 6px; }"` -> replace rgb()/rgba() with palette field
- L505: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L507: `"QPushButton:hover { background: rgba(0,0,0,0.04); border-radius: 6px; }"` -> replace rgb()/rgba() with palette field
- L521: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L523: `"QPushButton:hover { background: rgba(0,0,0,0.04); border-radius: 6px; }"` -> replace rgb()/rgba() with palette field
- L535: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L542: `f"  background: rgba(0,0,0,0.10);"` -> replace rgb()/rgba() with palette field
- L546: `f"  background: rgba(0,0,0,0.18);"` -> replace rgb()/rgba() with palette field

## `src/seeker_accounting/app/shell/workspace_host.py`

- L135: `# makes theme switching (app.setStyleSheet) fast — Qt cost is` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/db/migrations/versions/c4d5e6f7a8b9_slice_14d_ias_ifrs_income_statement.py`

- L171: `"section_background": "#F3F4F6",` -> replace hex with palette field
- L172: `"subtotal_background": "#E5E7EB",` -> replace hex with palette field
- L173: `"statement_background": "#FFFFFF",` -> replace hex with palette field
- L189: `"section_background": "#EEF2F7",` -> replace hex with palette field
- L190: `"subtotal_background": "#DDE5EF",` -> replace hex with palette field
- L191: `"statement_background": "#FFFFFF",` -> replace hex with palette field
- L207: `"section_background": "#EAF0FF",` -> replace hex with palette field
- L208: `"subtotal_background": "#DCE7F7",` -> replace hex with palette field
- L209: `"statement_background": "#FCFCFD",` -> replace hex with palette field

## `src/seeker_accounting/modules/accounting/journals/ui/account_cell_widget.py`

- L113: `self._code_edit.setStyleSheet("")` -> move to QSS rule + objectName; reference palette/tokens
- L115: `self._code_edit.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L116: `"QLineEdit { border: 1px solid #E53E3E; background: #FFF5F5; }"` -> replace hex with palette field

## `src/seeker_accounting/modules/administration/ui/abnormal_shutdown_dialog.py`

- L57: `header.setStyleSheet("font-size: 13px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens
- L69: `info.setStyleSheet("color: #666; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/administration/ui/admin_abnormal_session_dialog.py`

- L25: `_ATTENTION_STYLE = "background-color: #FFF3CD; color: #856404; font-weight: 600; padding: 2px 6px;"` -> replace hex with palette field
- L59: `header.setStyleSheet("font-size: 13px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/administration/ui/backup_import_preview_dialog.py`

- L110: `header.setStyleSheet("background:#1E3A5F;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L114: `title.setStyleSheet("font-size:14px;font-weight:600;color:#F9FAFB;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L121: `meta_lbl.setStyleSheet("font-size:11px;color:#93C5FD;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L161: `self._status_label.setStyleSheet("font-size:11px;color:#6B7280;padding:4px 20px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L166: `footer.setStyleSheet("border-top:1px solid #E5E7EB;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L177: `self._confirm_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L178: `"background:#1E3A5F;color:white;padding:6px 18px;"` -> replace hex with palette field
- L193: `val_lbl.setStyleSheet("font-size:18px;font-weight:700;color:#1E3A5F;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L195: `lbl_lbl.setStyleSheet("font-size:10px;color:#6B7280;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/budgeting/ui/budget_editor_dialog.py`

- L283: `self._reason_label.setStyleSheet("color: #6b7280; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L354: `self._footer_label.setStyleSheet("font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/companies/ui/company_purge_export_dialog.py`

- L53: `icon_label.setStyleSheet("font-size: 32px; color: #D97706;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L59: `heading.setStyleSheet("font-size: 14px; color: #1F2937;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L68: `body.setStyleSheet("font-size: 12px; color: #6B7280;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L78: `export_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L79: `"QPushButton { background: #3B82F6; color: #fff; border: none; "` -> replace hex with palette field
- L81: `"QPushButton:hover { background: #2563EB; }"` -> replace hex with palette field
- L88: `delete_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L89: `"QPushButton { background: #EF4444; color: #fff; border: none; "` -> replace hex with palette field
- L91: `"QPushButton:hover { background: #DC2626; }"` -> replace hex with palette field

## `src/seeker_accounting/modules/companies/ui/organisation_settings_page.py`

- L109: `self._logo_label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L110: `"QLabel { border: 1px solid #E5E7EB; border-radius: 8px; "` -> replace hex with palette field
- L111: `"background: #F9FAFB; color: #9CA3AF; font-size: 11px; }"` -> replace hex with palette field
- L120: `self._display_name_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L126: `self._legal_name_label.setStyleSheet("font-size: 13px; color: #6B7280;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L142: `divider.setStyleSheet("color: #E5E7EB;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L195: `lbl.setStyleSheet("font-size: 11px; color: #9CA3AF; font-weight: 500;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L201: `val.setStyleSheet("font-size: 12px; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L266: `self._status_label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L268: `"background: #D1FAE5; color: #065F46;"` -> replace hex with palette field
- L272: `self._status_label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L274: `"background: #FEE2E2; color: #991B1B;"` -> replace hex with palette field

## `src/seeker_accounting/modules/companies/ui/system_admin_auth_dialog.py`

- L66: `icon.setStyleSheet("font-size: 30px; color: #374151;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L71: `heading.setStyleSheet("font-size: 16px; font-weight: 600; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L77: `sub.setStyleSheet("font-size: 11px; color: #6B7280;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L86: `self._username_field.setStyleSheet(self._field_style())` -> move to QSS rule + objectName; reference palette/tokens
- L93: `self._password_field.setStyleSheet(self._field_style())` -> move to QSS rule + objectName; reference palette/tokens
- L99: `unlock_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L100: `"QPushButton { background: #1D4ED8; color: #fff; border: none; "` -> replace hex with palette field
- L102: `"QPushButton:hover { background: #1E40AF; }"` -> replace hex with palette field
- L110: `cancel_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L111: `"QPushButton { color: #6B7280; border: none; font-size: 12px; }"` -> replace hex with palette field
- L112: `"QPushButton:hover { color: #374151; }"` -> replace hex with palette field
- L142: `"QLineEdit { border: 1px solid #D1D5DB; border-radius: 4px; "` -> replace hex with palette field
- L143: `"padding: 0 10px; font-size: 13px; color: #111827; background: #F9FAFB; }"` -> replace hex with palette field
- L144: `"QLineEdit:focus { border-color: #3B82F6; background: #fff; }"` -> replace hex with palette field

## `src/seeker_accounting/modules/companies/ui/system_admin_dialog.py`

- L85: `header.setStyleSheet("background: #1E3A5F;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L90: `title_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #F9FAFB;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L95: `sub_lbl.setStyleSheet("font-size: 11px; color: #93C5FD;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L127: `self._table.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L128: `"QTableWidget { border: none; outline: none; background: #FFFFFF; "` -> replace hex with palette field
- L129: `"alternate-background-color: #F8FAFC; }"` -> replace hex with palette field
- L130: `"QTableWidget::item { padding: 0 8px; border: none; color: #111827; }"` -> replace hex with palette field
- L131: `"QHeaderView::section { background: #F1F5F9; border: none; border-bottom: 1px solid #E2E8F0; "` -> replace hex with palette field
- L132: `"padding: 8px; font-size: 11px; font-weight: 600; color: #475569; }"` -> replace hex with palette field
- L140: `footer.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L141: `"background: #F8FAFC; border-top: 1px solid #E2E8F0;"` -> replace hex with palette field
- L148: `refresh_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L149: `"QPushButton { background: transparent; border: 1px solid #CBD5E1; "` -> replace hex with palette field
- L150: `"border-radius: 4px; padding: 0 12px; font-size: 12px; color: #475569; }"` -> replace hex with palette field
- L151: `"QPushButton:hover { background: #F1F5F9; }"` -> replace hex with palette field
- L157: `export_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L158: `"QPushButton { background: transparent; border: 1px solid #CBD5E1; "` -> replace hex with palette field
- L159: `"border-radius: 4px; padding: 0 12px; font-size: 12px; color: #475569; }"` -> replace hex with palette field
- L160: `"QPushButton:hover { background: #F1F5F9; }"` -> replace hex with palette field
- L167: `import_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L168: `"QPushButton { background: transparent; border: 1px solid #CBD5E1; "` -> replace hex with palette field
- L169: `"border-radius: 4px; padding: 0 12px; font-size: 12px; color: #475569; }"` -> replace hex with palette field
- L170: `"QPushButton:hover { background: #F1F5F9; }"` -> replace hex with palette field
- L178: `close_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L179: `"QPushButton { background: #374151; color: #fff; border: none; "` -> replace hex with palette field
- L181: `"QPushButton:hover { background: #1F2937; }"` -> replace hex with palette field
- L207: `status_chip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L245: `return "Pending Deletion", "background: #FEF3C7; color: #92400E;"` -> replace hex with palette field
- L247: `return "Active", "background: #D1FAE5; color: #065F46;"` -> replace hex with palette field
- L248: `return "Deactivated", "background: #F3F4F6; color: #6B7280;"` -> replace hex with palette field
- L260: `restore_btn = self._small_btn("Restore", "#0369A1", "#075985")` -> replace hex with palette field
- L265: `deact_btn = self._small_btn("Deactivate", "#6B7280", "#4B5563")` -> replace hex with palette field
- L269: `sched_btn = self._small_btn("Schedule Deletion", "#DC2626", "#B91C1C")` -> replace hex with palette field
- L274: `react_btn = self._small_btn("Reactivate", "#059669", "#047857")` -> replace hex with palette field
- L278: `sched_btn = self._small_btn("Schedule Deletion", "#DC2626", "#B91C1C")` -> replace hex with palette field
- L289: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/companies/ui/system_admin_password_change_dialog.py`

- L69: `warn_icon.setStyleSheet("font-size: 28px;")` -> move to QSS rule + objectName; reference palette/tokens
- L74: `heading.setStyleSheet("font-size: 15px; font-weight: 700; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L85: `notice.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L86: `"font-size: 11px; color: #B45309; background: #FFFBEB; "` -> replace hex with palette field
- L87: `"border: 1px solid #FDE68A; border-radius: 4px; padding: 8px;"` -> replace hex with palette field
- L94: `new_lbl.setStyleSheet("font-size: 12px; color: #374151; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L101: `self._new_password_field.setStyleSheet(self._field_style())` -> move to QSS rule + objectName; reference palette/tokens
- L105: `confirm_lbl.setStyleSheet("font-size: 12px; color: #374151; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L112: `self._confirm_field.setStyleSheet(self._field_style())` -> move to QSS rule + objectName; reference palette/tokens
- L118: `save_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L119: `"QPushButton { background: #059669; color: #fff; border: none; "` -> replace hex with palette field
- L121: `"QPushButton:hover { background: #047857; }"` -> replace hex with palette field
- L131: `"QLineEdit { border: 1px solid #D1D5DB; border-radius: 4px; "` -> replace hex with palette field
- L132: `"padding: 0 10px; font-size: 13px; color: #111827; background: #F9FAFB; }"` -> replace hex with palette field
- L133: `"QLineEdit:focus { border-color: #3B82F6; background: #fff; }"` -> replace hex with palette field

## `src/seeker_accounting/modules/contracts_projects/ui/project_workspace_window.py`

- L77: `"active":    ("#dcfce7", "#166534"),` -> replace hex with palette field
- L78: `"draft":     ("#e0f2fe", "#075985"),` -> replace hex with palette field
- L79: `"on_hold":   ("#fef3c7", "#92400e"),` -> replace hex with palette field
- L80: `"completed": ("#ede9fe", "#5b21b6"),` -> replace hex with palette field
- L81: `"closed":    ("#e5e7eb", "#374151"),` -> replace hex with palette field
- L82: `"cancelled": ("#fee2e2", "#991b1b"),` -> replace hex with palette field
- L83: `"submitted": ("#e0f2fe", "#075985"),` -> replace hex with palette field
- L84: `"approved":  ("#dcfce7", "#166534"),` -> replace hex with palette field
- L85: `"superseded":("#e5e7eb", "#374151"),` -> replace hex with palette field
- L86: `"inactive":  ("#e5e7eb", "#374151"),` -> replace hex with palette field
- L91: `bg, fg = _STATUS_COLORS.get((code or "").lower(), ("#e5e7eb", "#374151"))` -> replace hex with palette field
- L180: `self._type_chip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L181: `"padding: 2px 8px; border-radius: 8px; background: #eef1f5; "` -> replace hex with palette field
- L182: `"color: #374151; font-weight: 500;"` -> replace hex with palette field
- L205: `caption.setStyleSheet("color: #6b7280; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L207: `value.setStyleSheet("color: #111827; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L241: `tile.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L242: `"QFrame { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; }"` -> replace hex with palette field
- L248: `cap.setStyleSheet("color: #6b7280; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L255: `value.setStyleSheet("color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L282: `self._jobs_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L303: `self._budgets_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L338: `self._commitments_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L359: `self._costs_subtitle.setStyleSheet("color: #6b7280; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L537: `self._status_chip.setStyleSheet(_status_style(detail.status_code))` -> move to QSS rule + objectName; reference palette/tokens
- L728: `variance_label.setStyleSheet("color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L732: `color = "#166534" if val >= 0 else "#991b1b"` -> replace hex with palette field
- L734: `color = "#111827"` -> replace hex with palette field
- L735: `variance_label.setStyleSheet(f"color: {color};")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/dashboard/ui/dashboard_page.py`

- L750: `_AGING_COLORS_LIGHT = ["#2363EA", "#3B82F6", "#F59E0B", "#F97316", "#EF4444"]` -> replace hex with palette field
- L751: `_AGING_COLORS_DARK = ["#4D84F1", "#60A5FA", "#F6C453", "#FB923C", "#F87171"]` -> replace hex with palette field
- L780: `bg = QColor("#273247") if is_dark else QColor("#D9E2EC")` -> replace hex with palette field
- L827: `_TREND_INFLOW_LIGHT = "#10B981"` -> replace hex with palette field
- L828: `_TREND_OUTFLOW_LIGHT = "#F59E0B"` -> replace hex with palette field
- L829: `_TREND_INFLOW_DARK = "#34D399"` -> replace hex with palette field
- L830: `_TREND_OUTFLOW_DARK = "#FBBF24"` -> replace hex with palette field
- L831: `_TREND_GRID_LIGHT = "#E5E7EB"` -> replace hex with palette field
- L832: `_TREND_GRID_DARK = "#273247"` -> replace hex with palette field
- L833: `_TREND_AXIS_LIGHT = "#6B7280"` -> replace hex with palette field
- L834: `_TREND_AXIS_DARK = "#9CA3AF"` -> replace hex with palette field

## `src/seeker_accounting/modules/fixed_assets/ui/depreciation_schedule_preview_dialog.py`

- L352: `body {{ font-family: Arial, sans-serif; font-size: 10pt; color: #1a1a1a; margin: 20px; }}` -> replace hex with palette field
- L360: `th {{ background-color: #1e3a5f; color: #fff; padding: 7px 12px;` -> replace hex with palette field
- L363: `td {{ padding: 5px 12px; border-bottom: 1px solid #e8e8e8; }}` -> replace hex with palette field
- L365: `tr.even {{ background: #ffffff; }}` -> replace hex with palette field
- L366: `tr.odd {{ background: #f6f8fb; }}` -> replace hex with palette field

## `src/seeker_accounting/modules/management_reporting/ui/contract_summary_page.py`

- L432: `margin_label.setStyleSheet(f"color: {palette.success};")` -> move to QSS rule + objectName; reference palette/tokens
- L434: `margin_label.setStyleSheet(f"color: {palette.danger};")` -> move to QSS rule + objectName; reference palette/tokens
- L500: `lbl.setStyleSheet("")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/management_reporting/ui/project_variance_analysis_page.py`

- L177: `self._status_chip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L528: `v_label.setStyleSheet(f"color: {palette.success};")` -> move to QSS rule + objectName; reference palette/tokens
- L530: `v_label.setStyleSheet(f"color: {palette.danger};")` -> move to QSS rule + objectName; reference palette/tokens
- L544: `"On Track": (palette.success, "#E6F7F1" if palette.name == "light" else "#0D3326"),` -> replace hex with palette field
- L545: `"Watch": (palette.warning, "#FFF8E6" if palette.name == "light" else "#332D12"),` -> replace hex with palette field
- L546: `"Over Budget": (palette.danger, "#FEF0F0" if palette.name == "light" else "#331414"),` -> replace hex with palette field
- L547: `"Critical": (palette.danger, "#FEF0F0" if palette.name == "light" else "#331414"),` -> replace hex with palette field
- L551: `self._status_chip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L740: `lbl.setStyleSheet("")` -> move to QSS rule + objectName; reference palette/tokens
- L742: `self._status_chip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/services/payroll_export_service.py`

- L50: `body { font-family: 'Segoe UI', Arial, Helvetica, sans-serif; font-size: 10pt; color: #1F2933; margin: 20px; }` -> replace hex with palette field
- L51: `h1 { font-size: 14pt; color: #2F4F6F; margin: 0 0 2px 0; }` -> replace hex with palette field
- L52: `.subtitle { font-size: 10pt; color: #6B7280; margin-bottom: 14px; }` -> replace hex with palette field
- L54: `th { background-color: #2F4F6F; color: #fff; padding: 6px 10px; font-size: 8.5pt; font-weight: 600; text-align: left; }` -> replace hex with palette field
- L56: `td { padding: 4px 10px; border-bottom: 1px solid #EAF1F7; }` -> replace hex with palette field
- L58: `tr.even { background: #ffffff; }` -> replace hex with palette field
- L59: `tr.odd { background: #F6F8FB; }` -> replace hex with palette field
- L60: `.total-row td { font-weight: 700; border-top: 2px solid #2F4F6F; background: #EAF1F7; color: #2F4F6F; }` -> replace hex with palette field
- L64: `.footer { font-size: 7.5pt; color: #9CA3AF; margin-top: 14px; text-align: right; }` -> replace hex with palette field
- L65: `.warning-bar { padding: 6px 10px; background: #fff8e1; border-left: 3px solid #f9a825; font-size: 8.5pt; color: #6d4c00; margin-bottom: 10px; }` -> replace hex with palette field

## `src/seeker_accounting/modules/payroll/services/payroll_payslip_html_builder.py`

- L71: `--c-primary: #2F4F6F;` -> replace hex with palette field
- L72: `--c-primary-dark: #1E3A5F;` -> replace hex with palette field
- L73: `--c-accent: #2E7D4F;` -> replace hex with palette field
- L74: `--c-accent-bg: #EDF7F1;` -> replace hex with palette field
- L75: `--c-accent-border: #C3DFD0;` -> replace hex with palette field
- L76: `--c-tint: #EAF1F7;` -> replace hex with palette field
- L77: `--c-border: #D6E0EA;` -> replace hex with palette field
- L78: `--c-text: #1F2933;` -> replace hex with palette field
- L79: `--c-muted: #6B7280;` -> replace hex with palette field
- L80: `--c-faint: #9CA3AF;` -> replace hex with palette field
- L81: `--c-stripe: #F6F8FB;` -> replace hex with palette field
- L82: `--c-bg: #ffffff;` -> replace hex with palette field
- L198: `border-bottom: 1px solid #EEF1F4;` -> replace hex with palette field
- L260: `margin-top: 8px; border-top: 1px solid #EEF1F4; padding-top: 3px;` -> replace hex with palette field
- L265: `padding: 4px 8px; background: #FFF8E1;` -> replace hex with palette field
- L266: `border-left: 3px solid #F9A825;` -> replace hex with palette field
- L267: `font-size: 7pt; color: #6D4C00; margin-bottom: 6px;` -> replace hex with palette field
- L274: `body { background: #ffffff; }` -> replace hex with palette field

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_export_dialog.py`

- L81: `self._warning_frame.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L82: `"QFrame { background: #fff8e1; border-left: 3px solid #f9a825; padding: 8px 10px; }"` -> replace hex with palette field
- L94: `ctx_label.setStyleSheet("font-size: 11px; color: #555;")` -> move to QSS rule + objectName; reference palette/tokens
- L110: `info.setStyleSheet("font-size: 11px; color: #444;")` -> move to QSS rule + objectName; reference palette/tokens
- L169: `lbl.setStyleSheet("font-size: 10px; color: #6d4c00;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_input_batch_dialog.py`

- L162: `self._header_label.setStyleSheet("font-weight: 600; font-size: 13px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_payment_record_dialog.py`

- L69: `info.setStyleSheet("font-weight: 600; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_post_run_dialog.py`

- L84: `self._validation_label.setStyleSheet("font-weight: 600; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L103: `quickfix_label.setStyleSheet("font-size: 11px; color: #666;")` -> move to QSS rule + objectName; reference palette/tokens
- L108: `self._btn_open_role_mappings.setStyleSheet("font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L114: `self._btn_open_payroll_setup.setStyleSheet("font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L120: `self._btn_open_fiscal_periods.setStyleSheet("font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L135: `self._status_label.setStyleSheet("font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L177: `self._status_label.setStyleSheet("color: #c0392b; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L184: `self._status_label.setStyleSheet("color: #1a7a2e; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_run_dialog.py`

- L61: `info_label.setStyleSheet("color: #666; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_run_employee_detail_dialog.py`

- L56: `self._header.setStyleSheet("font-weight: 600; font-size: 13px;")` -> move to QSS rule + objectName; reference palette/tokens
- L69: `title.setStyleSheet("font-size: 10px; color: #666;")` -> move to QSS rule + objectName; reference palette/tokens
- L71: `val.setStyleSheet("font-weight: 600; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens
- L95: `self._summary_label.setStyleSheet("font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_run_posting_detail_dialog.py`

- L23: `"posted": "#1a7a2e",` -> replace hex with palette field
- L24: `"approved": "#2471a3",` -> replace hex with palette field
- L25: `"calculated": "#7d6608",` -> replace hex with palette field
- L27: `"voided": "#c0392b",` -> replace hex with palette field
- L69: `title.setStyleSheet("font-weight: 700; font-size: 14px;")` -> move to QSS rule + objectName; reference palette/tokens
- L79: `meta.setStyleSheet("font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L84: `je_label.setStyleSheet("font-size: 11px; color: #555;")` -> move to QSS rule + objectName; reference palette/tokens
- L96: `info.setStyleSheet("font-size: 11px; color: #555;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/dialogs/payroll_summary_dialog.py`

- L172: `lbl.setStyleSheet("font-weight: 600; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens
- L181: `lbl.setStyleSheet("font-size: 11px; color: #555;")` -> move to QSS rule + objectName; reference palette/tokens
- L183: `val.setStyleSheet("font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/dialogs/payslip_preview_dialog.py`

- L75: `btn_bar.setStyleSheet("background: #F3F5F7; border-top: 1px solid #D6E0EA;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L84: `export_btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L85: `"QPushButton { background: #2F4F6F; color: #ffffff; border: 1px solid #2F4F6F; "` -> replace hex with palette field
- L87: `"QPushButton:hover { background: #1E3A5F; border-color: #1E3A5F; }"` -> replace hex with palette field
- L88: `"QPushButton:pressed { background: #1A3356; }"` -> replace hex with palette field
- L139: `"<body style='font-family:Segoe UI;padding:24px;color:#c0392b'>"` -> replace hex with palette field

## `src/seeker_accounting/modules/payroll/ui/dialogs/validation_check_detail_dialog.py`

- L289: `"error":   ("ERROR",   "#dc3545"),` -> replace hex with palette field
- L290: `"warning": ("WARNING", "#fd7e14"),` -> replace hex with palette field
- L291: `"info":    ("INFO",    "#0d6efd"),` -> replace hex with palette field
- L334: `sev_label, sev_color = _SEVERITY_META.get(check.severity, ("INFO", "#0d6efd"))` -> replace hex with palette field
- L338: `badge.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L345: `title_lbl.setStyleSheet("font-size: 15px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens
- L380: `msg_lbl.setStyleSheet("font-size: 13px; line-height: 1.5; padding: 2px 0;")` -> move to QSS rule + objectName; reference palette/tokens
- L400: `fix_lbl.setStyleSheet("font-size: 13px; line-height: 1.65;")` -> move to QSS rule + objectName; reference palette/tokens
- L420: `btn_bar.setStyleSheet("border-top: 1px solid #e0e0e0;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L436: `lbl.setStyleSheet("font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/employee_hub_window.py`

- L181: `self._number_chip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L182: `"padding: 2px 8px; border-radius: 8px; background: #eef1f5; "` -> replace hex with palette field
- L183: `"color: #374151; font-weight: 500;"` -> replace hex with palette field
- L320: `self._status_chip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L322: `+ (" background: #e6f4ea; color: #1a7a2e;" if active` -> replace hex with palette field
- L323: `else " background: #fde8e8; color: #9b1c1c;")` -> replace hex with palette field
- L383: `lab.setStyleSheet("color: #6b7280;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L472: `pill.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L474: `" background: #fff7e6; color: #b25503; font-weight: 600;"` -> replace hex with palette field
- L478: `pill.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L480: `" background: #e6f4ea; color: #1a7a2e; font-weight: 600;"` -> replace hex with palette field

## `src/seeker_accounting/modules/payroll/ui/payroll_accounting_workspace.py`

- L67: `"posted": "#1a7a2e",` -> replace hex with palette field
- L68: `"approved": "#2471a3",` -> replace hex with palette field
- L69: `"calculated": "#7d6608",` -> replace hex with palette field
- L71: `"voided": "#c0392b",` -> replace hex with palette field
- L130: `title.setStyleSheet("font-weight: 600; font-size: 14px;")` -> move to QSS rule + objectName; reference palette/tokens
- L135: `self._company_label.setStyleSheet("color: #666; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L617: `lines_lbl.setStyleSheet("font-size: 11px; font-weight: 600; margin-top: 6px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/payroll_calculation_workspace.py`

- L767: `emp_header.setStyleSheet("font-size: 11px; font-weight: 600; margin-top: 6px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/payroll_operations_workspace.py`

- L57: `"error": "#dc3545",` -> replace hex with palette field
- L58: `"warning": "#fd7e14",` -> replace hex with palette field
- L59: `"info": "#0d6efd",` -> replace hex with palette field
- L88: `title.setStyleSheet("font-weight: 600; font-size: 14px;")` -> move to QSS rule + objectName; reference palette/tokens
- L93: `self._company_label.setStyleSheet("color: #666; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L285: `self._summary_label.setStyleSheet("font-size: 12px; padding: 4px;")` -> move to QSS rule + objectName; reference palette/tokens
- L299: `hint.setStyleSheet("color: #888; font-size: 11px; padding: 1px 0 4px 0;")` -> move to QSS rule + objectName; reference palette/tokens
- L327: `f"<b style='color: #28a745;'>Ready</b> — "` -> replace hex with palette field
- L333: `f"<b style='color: #dc3545;'>Not Ready</b> — "` -> replace hex with palette field
- L411: `self._preview_label.setStyleSheet("font-size: 11px; padding: 6px; background: #f8f9fa; border-radius: 4px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L544: `self._file_label.setStyleSheet("color: #666; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens
- L706: `export_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #555;")` -> move to QSS rule + objectName; reference palette/tokens
- L1062: `body { font-family: 'Segoe UI', Arial, Helvetica, sans-serif; font-size: 10pt; color: #1F2933; }` -> replace hex with palette field
- L1068: `.company-banner .name-cell { font-size: 14pt; font-weight: 700; color: #2F4F6F; }` -> replace hex with palette field
- L1070: `color: #6E859B; letter-spacing: 1px; line-height: 1.4; }` -> replace hex with palette field
- L1071: `hr.sep { border: none; border-top: 1px solid #D6E0EA; margin: 6px 0; }` -> replace hex with palette field
- L1075: `.id-card { border: 1px solid #D6E0EA; border-radius: 4px; overflow: hidden; background: #fff; }` -> replace hex with palette field
- L1076: `.identity-header { font-size: 8.5pt; font-weight: 600; color: #2F4F6F; background: #EAF1F7;` -> replace hex with palette field
- L1077: `padding: 5px 10px; letter-spacing: 0.4px; border-bottom: 1px solid #D6E0EA; }` -> replace hex with palette field
- L1081: `color: #6B7280; padding-right: 8px; }` -> replace hex with palette field
- L1082: `.id-row-value { font-size: 9pt; font-weight: 600; color: #1F2933; }` -> replace hex with palette field
- L1084: `.context-bar { background: #EAF1F7; margin-bottom: 14px; border-radius: 3px; }` -> replace hex with palette field
- L1087: `.context-bar .ctx-label { font-size: 7.5pt; color: #6B7280; }` -> replace hex with palette field
- L1088: `.context-bar .ctx-value { font-size: 9pt; font-weight: 600; color: #1F2933; }` -> replace hex with palette field
- L1089: `.context-bar .ctx-sep { width: 1px; background: #D6E0EA; padding: 0; }` -> replace hex with palette field
- L1091: `.section-header { font-size: 9pt; font-weight: 600; color: #2F4F6F;` -> replace hex with palette field
- L1092: `padding: 2px 0; margin: 10px 0 0 0; border-bottom: 2px solid #2F4F6F; }` -> replace hex with palette field
- L1093: `h2 { font-size: 12pt; margin-top: 12px; margin-bottom: 4px; color: #2F4F6F; }` -> replace hex with palette field
- L1095: `td { border-bottom: 1px solid #EAF1F7; padding: 3px 10px; text-align: left; }` -> replace hex with palette field
- L1097: `th { background: #2F4F6F; color: #fff; padding: 5px 10px; font-size: 8.5pt; font-weight: 600; text-align: left; }` -> replace hex with palette field
- L1099: `.total-row { font-weight: 700; background: #EAF1F7; }` -> replace hex with palette field
- L1100: `.total-row td { border-top: 2px solid #2F4F6F; color: #2F4F6F; }` -> replace hex with palette field
- L1101: `tr:nth-child(even) { background: #F6F8FB; }` -> replace hex with palette field
- L1105: `.bases-strip td { background: #EAF1F7; border: 1px solid #D6E0EA; border-radius: 3px;` -> replace hex with palette field
- L1107: `.bases-strip .b-label { font-size: 7.5pt; color: #6B7280; text-transform: uppercase; letter-spacing: 0.5px; }` -> replace hex with palette field
- L1108: `.bases-strip .b-value { font-size: 10.5pt; font-weight: 600; color: #2F4F6F; }` -> replace hex with palette field
- L1110: `.net-box { margin: 14px 0; background: #EDF7F1; border: 1px solid #C3DFD0;` -> replace hex with palette field
- L1114: `.net-box .label { font-size: 9pt; color: #2E7D4F; }` -> replace hex with palette field
- L1115: `.net-box .label-main { font-size: 11pt; font-weight: 600; color: #2E7D4F; }` -> replace hex with palette field
- L1116: `.net-box .amount { font-size: 9.5pt; color: #2E7D4F; font-weight: 600; text-align: right; }` -> replace hex with palette field
- L1117: `.net-box .amount-main { font-size: 16pt; font-weight: 700; color: #2E7D4F; text-align: right; }` -> replace hex with palette field
- L1118: `.net-sep { border: none; border-top: 1px solid #C3DFD0; margin: 0; }` -> replace hex with palette field
- L1122: `font-size: 8pt; color: #6B7280; border: none; background: transparent; }` -> replace hex with palette field
- L1123: `.sig-line { border-top: 1px solid #6E859B; padding-top: 4px; margin-top: 36px; }` -> replace hex with palette field
- L1126: `.footer { font-size: 7.5pt; color: #9CA3AF; margin-top: 14px; text-align: right; }` -> replace hex with palette field
- L1260: `parts.append(f'<h1 style="color:#2F4F6F">{data.company_name}</h1>')` -> replace hex with palette field
- L1287: `parts.append('<div class="section"><h3 style="color:#2F4F6F">Summary</h3><table>')` -> replace hex with palette field

## `src/seeker_accounting/modules/payroll/ui/payroll_run_employee_window.py`

- L115: `title.setStyleSheet("font-size: 10px; color: #666;")` -> move to QSS rule + objectName; reference palette/tokens
- L117: `val.setStyleSheet("font-weight: 600; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/payroll/ui/wizards/employee_payroll_setup_wizard.py`

- L356: `status.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L357: `"color:#1a7a2e;" if ok else "color:#b25503;"` -> replace hex with palette field

## `src/seeker_accounting/modules/payroll/ui/wizards/remittance_wizard.py`

- L469: `f"<span style='color:#c62828;'>(overdue by {-days} days)</span>"` -> replace hex with palette field
- L715: `issue = f"<br><span style='color:#c62828;'><b>Cannot create:</b> {err}</span>" if err else ""` -> replace hex with palette field

## `src/seeker_accounting/modules/purchases/services/purchase_bill_print_service.py`

- L216: `'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Supplier</div>'` -> replace hex with palette field
- L217: `f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'` -> replace hex with palette field
- L219: `f'<div style="font-size:9pt;color:#6b7280;">{h(bill.supplier_code)}</div>'` -> replace hex with palette field
- L223: `f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'` -> replace hex with palette field
- L225: `f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'` -> replace hex with palette field
- L243: `'<td style="width:8px;border-left:1px solid #d0d7de;"></td>'` -> replace hex with palette field

## `src/seeker_accounting/modules/purchases/services/supplier_payment_print_service.py`

- L206: `'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Paid To</div>'` -> replace hex with palette field
- L207: `f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'` -> replace hex with palette field
- L209: `f'<div style="font-size:9pt;color:#6b7280;">{h(payment.supplier_code)}</div>'` -> replace hex with palette field
- L213: `f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'` -> replace hex with palette field
- L215: `f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'` -> replace hex with palette field
- L232: `'<td style="width:8px;border-left:1px solid #d0d7de;"></td>'` -> replace hex with palette field

## `src/seeker_accounting/modules/reporting/export/pdf_renderer.py`

- L25: `_BRAND_PRIMARY = "#1E3A5F"` -> replace hex with palette field
- L26: `_BRAND_LIGHT = "#F0F3F7"` -> replace hex with palette field
- L27: `_BRAND_BORDER = "#D0D7DE"` -> replace hex with palette field
- L28: `_SECTION_BG = "#EDF1F6"` -> replace hex with palette field
- L29: `_SUBTOTAL_BG = "#F5F6F8"` -> replace hex with palette field
- L30: `_TOTAL_BG = "#E6EAF0"` -> replace hex with palette field
- L31: `_HIGHLIGHT_BG = "#FFFCE8"` -> replace hex with palette field
- L292: `color: #1a1a1a;` -> replace hex with palette field

## `src/seeker_accounting/modules/reporting/services/balance_sheet_template_service.py`

- L19: `section_background="#F3F4F6",` -> replace hex with palette field
- L20: `subtotal_background="#E5E7EB",` -> replace hex with palette field
- L21: `statement_background="#FFFFFF",` -> replace hex with palette field
- L34: `section_background="#F8FAFC",` -> replace hex with palette field
- L35: `subtotal_background="#E2E8F0",` -> replace hex with palette field
- L36: `statement_background="#FFFFFF",` -> replace hex with palette field
- L49: `section_background="#EEF2FF",` -> replace hex with palette field
- L50: `subtotal_background="#DCE7F7",` -> replace hex with palette field
- L51: `statement_background="#FCFCFD",` -> replace hex with palette field

## `src/seeker_accounting/modules/reporting/services/ohada_income_statement_template_service.py`

- L19: `section_background="#F3F4F6",` -> replace hex with palette field
- L20: `subtotal_background="#E5E7EB",` -> replace hex with palette field
- L21: `statement_background="#FFFFFF",` -> replace hex with palette field
- L34: `section_background="#F8FAFC",` -> replace hex with palette field
- L35: `subtotal_background="#E2E8F0",` -> replace hex with palette field
- L36: `statement_background="#FFFFFF",` -> replace hex with palette field
- L49: `section_background="#EEF2FF",` -> replace hex with palette field
- L50: `subtotal_background="#DCE7F7",` -> replace hex with palette field
- L51: `statement_background="#FCFCFD",` -> replace hex with palette field

## `src/seeker_accounting/modules/reporting/specs/ias_income_statement_spec.py`

- L57: `section_background="#F3F4F6",` -> replace hex with palette field
- L58: `subtotal_background="#E5E7EB",` -> replace hex with palette field
- L59: `statement_background="#FFFFFF",` -> replace hex with palette field
- L73: `section_background="#EEF2F7",` -> replace hex with palette field
- L74: `subtotal_background="#DDE5EF",` -> replace hex with palette field
- L75: `statement_background="#FFFFFF",` -> replace hex with palette field
- L89: `section_background="#EAF0FF",` -> replace hex with palette field
- L90: `subtotal_background="#DCE7F7",` -> replace hex with palette field
- L91: `statement_background="#FCFCFD",` -> replace hex with palette field

## `src/seeker_accounting/modules/reporting/ui/dialogs/balance_sheet_template_preview_dialog.py`

- L136: `swatch.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L137: `f"background-color: {color_hex}; border: 1px solid #CBD5E1; border-radius: 6px;"` -> replace hex with palette field
- L348: `table.setStyleSheet(f"background: {self._template_dto.statement_background};")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/reporting/ui/dialogs/ias_balance_sheet_window.py`

- L131: `sep.setStyleSheet("background: palette(mid);")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/reporting/ui/dialogs/ias_income_statement_template_preview_dialog.py`

- L90: `table.setStyleSheet(f"background: {self._template_dto.statement_background};")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/reporting/ui/dialogs/ias_income_statement_window.py`

- L148: `sep.setStyleSheet("background: palette(mid);")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/reporting/ui/dialogs/ohada_balance_sheet_window.py`

- L134: `sep.setStyleSheet("background: palette(mid);")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/reporting/ui/dialogs/ohada_income_statement_template_preview_dialog.py`

- L90: `table.setStyleSheet(f"background: {self._template_dto.statement_background};")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/reporting/ui/dialogs/ohada_income_statement_window.py`

- L142: `sep.setStyleSheet("background: palette(mid);")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/reporting/ui/widgets/reporting_context_strip.py`

- L71: `sep.setStyleSheet("background: palette(mid);")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/sales/services/customer_receipt_print_service.py`

- L208: `'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Received From</div>'` -> replace hex with palette field
- L209: `f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'` -> replace hex with palette field
- L211: `f'<div style="font-size:9pt;color:#6b7280;">{h(receipt.customer_code)}</div>'` -> replace hex with palette field
- L215: `f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'` -> replace hex with palette field
- L217: `f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'` -> replace hex with palette field
- L234: `'<td style="width:8px;border-left:1px solid #d0d7de;"></td>'` -> replace hex with palette field

## `src/seeker_accounting/modules/sales/services/sales_invoice_print_service.py`

- L222: `'color:#6b7280;letter-spacing:0.5px;margin-bottom:4px;">Bill To</div>'` -> replace hex with palette field
- L223: `f'<div style="font-weight:700;font-size:11pt;color:#1a1a1a;margin-bottom:2px;">'` -> replace hex with palette field
- L225: `f'<div style="font-size:9pt;color:#6b7280;">{h(invoice.customer_code)}</div>'` -> replace hex with palette field
- L229: `f'<td style="font-size:7.5pt;color:#6b7280;text-transform:uppercase;'` -> replace hex with palette field
- L231: `f'<td style="font-size:9pt;font-weight:600;color:#1a1a1a;padding:2px 0;">{h(v)}</td>'` -> replace hex with palette field
- L249: `'<td style="width:8px;border-left:1px solid #d0d7de;"></td>'` -> replace hex with palette field

## `src/seeker_accounting/modules/taxation/services/tax_return_pdf_export_service.py`

- L198: `body { font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937;` -> replace hex with palette field
- L201: `color: #374151; margin-bottom: 14px; line-height: 1.4; }` -> replace hex with palette field
- L203: `font-size: 10pt; color: #111827; }` -> replace hex with palette field
- L204: `.official-header .motto { font-style: italic; color: #6b7280; }` -> replace hex with palette field
- L207: `margin: 8px 0 4px 0; color: #111827;` -> replace hex with palette field
- L208: `border-top: 2px solid #111827; border-bottom: 2px solid #111827;` -> replace hex with palette field
- L210: `.form-subtitle { text-align: center; color: #4b5563; font-size: 9pt;` -> replace hex with palette field
- L212: `.identity { border: 1px solid #cbd5e1; padding: 8px 12px;` -> replace hex with palette field
- L216: `.identity td.k { color: #6b7280; width: 130px; font-size: 9pt; }` -> replace hex with palette field
- L217: `.identity td.v { color: #111827; font-weight: 600; }` -> replace hex with palette field
- L220: `border: 1.5px solid #4b5563; vertical-align: middle;` -> replace hex with palette field
- L222: `line-height: 12px; font-weight: 700; color: #111827; }` -> replace hex with palette field
- L225: `.section h2 { font-size: 11pt; margin: 0 0 4px 0; color: #111827;` -> replace hex with palette field
- L226: `background: #1f2937; color: #f9fafb;` -> replace hex with palette field
- L230: `border: 1px solid #1f2937; }` -> replace hex with palette field
- L231: `table.form th, table.form td { border: 1px solid #cbd5e1;` -> replace hex with palette field
- L233: `table.form th { background: #f3f4f6; color: #374151; text-align: left;` -> replace hex with palette field
- L236: `text-align: center; color: #1e3a8a; font-weight: 600; }` -> replace hex with palette field
- L237: `table.form td.label { color: #1f2937; }` -> replace hex with palette field
- L242: `table.form td.rate { text-align: center; color: #4b5563; width: 60px; }` -> replace hex with palette field
- L243: `table.form td.empty { color: #9ca3af; }` -> replace hex with palette field
- L244: `table.form tr.emphasis td { background: #f9fafb; font-weight: 700;` -> replace hex with palette field
- L245: `color: #111827; }` -> replace hex with palette field
- L247: `.totals { margin-top: 14px; border-top: 2px solid #111827;` -> replace hex with palette field
- L251: `.totals td.k { color: #4b5563; text-align: right; }` -> replace hex with palette field
- L254: `font-family: 'Consolas', monospace; color: #111827; }` -> replace hex with palette field
- L255: `.totals td.due { color: #b91c1c; }` -> replace hex with palette field
- L257: `.notes { margin-top: 12px; padding: 8px 12px; background: #f9fafb;` -> replace hex with palette field
- L258: `border-left: 3px solid #d1d5db; font-size: 9pt; color: #374151; }` -> replace hex with palette field
- L259: `.footer { margin-top: 24px; font-size: 8.5pt; color: #9ca3af;` -> replace hex with palette field
- L260: `text-align: center; border-top: 1px dashed #e5e7eb; padding-top: 8px; }` -> replace hex with palette field
- L263: `.stamp.draft { background: #fef3c7; color: #92400e; }` -> replace hex with palette field
- L264: `.stamp.filed { background: #dcfce7; color: #166534; }` -> replace hex with palette field
- L265: `.stamp.other { background: #e5e7eb; color: #374151; }` -> replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/company_tax_profile_dialog.py`

- L273: `header.setStyleSheet("font-weight: 600; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/company_tax_profile_page.py`

- L130: `self._exists_banner.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L131: `"QLabel { background: #FEF3C7; color: #92400E; padding: 8px 12px; "` -> replace hex with palette field
- L138: `self._title_label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L139: `"font-size: 18px; font-weight: 700; color: #111827;"` -> replace hex with palette field
- L145: `divider.setStyleSheet("color: #E5E7EB;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L205: `lbl.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L206: `"font-size: 11px; color: #9CA3AF; font-weight: 500;"` -> replace hex with palette field
- L215: `val.setStyleSheet("font-size: 12px; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/tax_compliance_dialogs.py`

- L104: `header.setStyleSheet("font-weight: 600; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L819: `self._readiness_summary.setStyleSheet("color: #6B7280;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L861: `self._readiness_summary.setStyleSheet("color: #047857;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L869: `self._readiness_summary.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L870: `"color: #B91C1C;" if errors else "color: #92400E;"` -> replace hex with palette field
- L1021: `lbl.setStyleSheet("font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens
- L1054: `self._issues_label.setStyleSheet("font-weight: 600; color: #b91c1c;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/tax_compliance_page.py`

- L349: `heading_label.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L350: `"font-size: 14px; font-weight: 600; color: #111827;"` -> replace hex with palette field
- L355: `desc_label.setStyleSheet("color: #6B7280; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/tax_dashboard_page.py`

- L209: `h.setStyleSheet("font-size: 14px; font-weight: 600; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L222: `h2.setStyleSheet("font-size: 14px; font-weight: 600; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L244: `heading.setStyleSheet("font-size: 14px; font-weight: 600; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L254: `tile.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L255: `"QFrame { background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; }"` -> replace hex with palette field
- L261: `cap.setStyleSheet("color: #6B7280; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L264: `value.setStyleSheet("color: #111827; font-size: 18px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/tax_return_detail_dialog.py`

- L79: `return ("#FEF3C7", "#92400E")  # amber-100 / amber-800` -> replace hex with palette field
- L81: `return ("#DCFCE7", "#166534")  # green-100 / green-800` -> replace hex with palette field
- L82: `return ("#E5E7EB", "#374151")      # gray-200 / gray-700` -> replace hex with palette field
- L177: `company.setStyleSheet("color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L183: `title.setStyleSheet("color: #6B7280; font-size: 11pt;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L190: `status_pill.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L238: `label.setStyleSheet("color: #6B7280; font-size: 10pt;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L240: `value.setStyleSheet("color: #111827; font-size: 11pt;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L256: `card.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L257: `"background-color: #FEF3C7; border-left: 3px solid #F59E0B;"` -> replace hex with palette field
- L268: `msg.setStyleSheet("color: #92400E; font-size: 10pt;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L288: `heading.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L289: `"font-weight: 600; color: #111827; font-size: 12pt;"` -> replace hex with palette field
- L380: `card.setStyleSheet("background-color: #F9FAFB;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L387: `("Total due", _money(layout.total_due), "#111827"),` -> replace hex with palette field
- L388: `("Total paid", _money(layout.total_paid), "#111827"),` -> replace hex with palette field
- L392: `"#B91C1C" if layout.outstanding > 0 else "#166534",` -> replace hex with palette field
- L398: `lab.setStyleSheet("color: #6B7280; font-size: 10pt;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L404: `val.setStyleSheet(f"color: {accent};")` -> move to QSS rule + objectName; reference palette/tokens
- L424: `heading.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L425: `"font-weight: 600; color: #111827; font-size: 12pt;"` -> replace hex with palette field
- L436: `info.setStyleSheet("color: #6B7280; font-size: 10pt;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L444: `amount.setStyleSheet("color: #111827; margin-top: 8px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L452: `card.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L453: `"background-color: #F9FAFB; border-left: 3px solid #D1D5DB;"` -> replace hex with palette field
- L459: `heading.setStyleSheet("font-weight: 600; color: #374151;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L464: `body.setStyleSheet("color: #4B5563; font-size: 10pt;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/withholding_certificates_dialogs.py`

- L78: `header.setStyleSheet("font-weight: 600; color: #111827;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L646: `current_label.setStyleSheet("color: #6B7280;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/taxation/ui/withholding_certificates_page.py`

- L273: `self._totals_label.setStyleSheet("color: #374151; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/asset_disposal/steps/confirm_step.py`

- L43: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/bank_cash_setup/steps/confirm_step.py`

- L41: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/bank_cash_setup/steps/type_step.py`

- L50: `self._desc.setStyleSheet("color: #555;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/bank_reconciliation/steps/finalize_step.py`

- L40: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L49: `warn.setStyleSheet("color: #6B5500; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/bank_reconciliation/steps/match_summary_step.py`

- L45: `self._tip.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L54: `w.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/bank_reconciliation/steps/statement_step.py`

- L58: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/coa_customization/steps/baseline_step.py`

- L50: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/coa_customization/steps/confirm_step.py`

- L58: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/company_setup/steps/account_role_mappings_step.py`

- L71: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L83: `label.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/company_setup/steps/chart_of_accounts_step.py`

- L50: `helper.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/company_setup/steps/company_info_step.py`

- L84: `self._helper.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/company_setup/steps/document_sequences_step.py`

- L56: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/company_setup/steps/fiscal_year_step.py`

- L79: `helper.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/company_setup/steps/review_step.py`

- L41: `title.setStyleSheet("font-size: 13px; font-weight: 600; color: #1A2230;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L50: `helper.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L54: `card.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L55: `"background: #F4F6FA; border: 1px solid #D4DAE3; border-radius: 2px;"` -> replace hex with palette field
- L84: `row.setStyleSheet("color: #1A2230; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L104: `empty.setStyleSheet("color: #7A8392; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L109: `label.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/company_setup/steps/tax_codes_step.py`

- L108: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/control_account_reconciliation/steps/review_step.py`

- L112: `card.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L113: `"#reconCard { border: 1px solid #d0d0d8; border-radius: 6px; padding: 10px; }"` -> replace hex with palette field
- L133: `status.setStyleSheet(f"color: {status_color}; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens
- L201: `lbl.setStyleSheet("color: #666;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/depreciation_run/steps/create_run_step.py`

- L55: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/depreciation_run/steps/post_step.py`

- L40: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/depreciation_run/steps/preview_step.py`

- L39: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/document_numbering/steps/commit_step.py`

- L42: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/document_numbering/steps/configure_step.py`

- L74: `self._preview_label.setStyleSheet("font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/fx_revaluation/steps/confirm_step.py`

- L44: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/journal_reversal/steps/confirm_step.py`

- L41: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/month_end_close/steps/close_step.py`

- L46: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L56: `warning.setStyleSheet("color: #6B5500; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/month_end_close/steps/drafts_check_step.py`

- L47: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/month_end_close/steps/period_selection_step.py`

- L44: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L56: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/month_end_close/steps/reconciliation_check_step.py`

- L49: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/opening_balances/steps/confirm_step.py`

- L45: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/opening_balances/steps/lines_step.py`

- L138: `self._totals.setStyleSheet("color: #2a7;" if diff == 0 and dr > 0 else "color: #c33;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/payroll_run/steps/approve_step.py`

- L40: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L49: `warning.setStyleSheet("color: #6B5500; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/payroll_run/steps/period_and_calculate_step.py`

- L72: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/payroll_run/steps/post_step.py`

- L49: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/payroll_run/steps/review_employees_step.py`

- L47: `intro.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L65: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/period_reopen/steps/pick_period_step.py`

- L46: `intro.setStyleSheet("color: #6B5500; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L56: `self._info.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/period_reopen/steps/reason_step.py`

- L46: `prompt.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/period_reopen/steps/reopen_step.py`

- L40: `self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/purchase_credit_note/steps/confirm_step.py`

- L56: `self._result_label.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/receipt_allocation/steps/allocate_step.py`

- L59: `self._amount_label.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L80: `self._allocated_label.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L84: `self._unallocated_label.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/receipt_allocation/steps/confirm_step.py`

- L55: `w.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/sales_credit_note/steps/confirm_step.py`

- L56: `self._result_label.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/stock_count/steps/confirm_step.py`

- L44: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/supplier_payment/steps/allocate_step.py`

- L53: `self._amount_label.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L74: `self._allocated_label.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/supplier_payment/steps/confirm_step.py`

- L55: `w.setStyleSheet("color: #2E3848; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field

## `src/seeker_accounting/modules/wizards/tax_regime/steps/dsf_flags_step.py`

- L82: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/user_provisioning/steps/confirm_step.py`

- L39: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/year_end_close/steps/confirm_step.py`

- L38: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/modules/wizards/year_end_close/steps/periods_review_step.py`

- L66: `self._result.setStyleSheet("color: #2a7;")` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/platform/printing/html_builder.py`

- L24: `_BRAND_PRIMARY = "#1e3a5f"` -> replace hex with palette field
- L25: `_BRAND_LIGHT = "#f0f3f7"` -> replace hex with palette field
- L26: `_BRAND_BORDER = "#d0d7de"` -> replace hex with palette field
- L27: `_BRAND_TEXT_MUTED = "#6b7280"` -> replace hex with palette field
- L63: `color: #1a1a1a;` -> replace hex with palette field
- L116: `color: #374151;` -> replace hex with palette field
- L174: `color: #1a1a1a;` -> replace hex with palette field
- L185: `.chip-draft {{ background: #f0f0f0; color: #555; }}` -> replace hex with palette field
- L186: `.chip-posted {{ background: #e6f4ea; color: #1e6b3a; }}` -> replace hex with palette field
- L187: `.chip-cancelled {{ background: #fde8e8; color: #9b1c1c; }}` -> replace hex with palette field
- L188: `.chip-paid {{ background: #e6f4ea; color: #1e6b3a; }}` -> replace hex with palette field
- L189: `.chip-partial {{ background: #fff3cd; color: #856404; }}` -> replace hex with palette field
- L190: `.chip-unpaid {{ background: #fff0f0; color: #9b1c1c; }}` -> replace hex with palette field
- L227: `border-bottom: 1px solid #e8edf3;` -> replace hex with palette field
- L240: `table.data-table tr.even {{ background: #ffffff; }}` -> replace hex with palette field
- L241: `table.data-table tr.odd {{ background: #fbfcfe; }}` -> replace hex with palette field
- L245: `background: #f7f9fc;` -> replace hex with palette field
- L274: `border-bottom: 1px solid #edf2f7;` -> replace hex with palette field
- L294: `background: #e8f5e9;` -> replace hex with palette field
- L295: `border-left: 4px solid #2e7d32;` -> replace hex with palette field
- L298: `.net-box .net-label {{ font-size: {fs - 1}pt; font-weight: 600; color: #1b5e20; }}` -> replace hex with palette field
- L299: `.net-box .net-amount {{ font-size: {fs + 3}pt; font-weight: 700; color: #1b5e20; }}` -> replace hex with palette field
- L303: `background: #fff8e1;` -> replace hex with palette field
- L304: `border-left: 3px solid #f9a825;` -> replace hex with palette field
- L306: `color: #6d4c00;` -> replace hex with palette field

## `src/seeker_accounting/platform/printing/word_builder.py`

- L40: `_RGB_BRAND_PRIMARY = (30, 58, 95)     # #1e3a5f` -> replace hex with palette field
- L41: `_RGB_BRAND_LIGHT = (240, 243, 247)    # #f0f3f7` -> replace hex with palette field
- L42: `_RGB_MUTED = (107, 114, 128)          # #6b7280` -> replace hex with palette field
- L44: `_RGB_TOTAL_BG = (238, 242, 247)       # #eef2f7` -> replace hex with palette field
- L45: `_RGB_STRIPE = (249, 250, 251)         # #f9fafb` -> replace hex with palette field

## `src/seeker_accounting/platform/wizards/host_dialog.py`

- L80: `intro_strip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L82: `"  background-color: #F4F6FA;"` -> replace hex with palette field
- L83: `"  border-bottom: 1px solid #D4DAE3;"` -> replace hex with palette field
- L90: `intro_label.setStyleSheet("color: #4E5866; font-size: 12px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L107: `self._rail.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L109: `"  background-color: #F4F6FA;"` -> replace hex with palette field
- L111: `"  border-right: 1px solid #D4DAE3;"` -> replace hex with palette field
- L114: `"#WizardStepRail::item { padding: 10px 16px; color: #4E5866; }"` -> replace hex with palette field
- L127: `self._step_title_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #1A2230;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L131: `self._step_subtitle_label.setStyleSheet("font-size: 12px; color: #4E5866;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L139: `self._error_strip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L141: `"  background: #FBE9E9; color: #8A1F1F;"` -> replace hex with palette field
- L142: `"  border: 1px solid #E5B4B4; border-radius: 2px;"` -> replace hex with palette field
- L159: `self._advisor_pane.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L161: `"  background: #FAFBFD;"` -> replace hex with palette field
- L162: `"  border-left: 1px solid #D4DAE3;"` -> replace hex with palette field
- L169: `advisor_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #1A2230;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L180: `status_strip.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L181: `"background: #F4F6FA; border-top: 1px solid #D4DAE3;"` -> replace hex with palette field
- L186: `self._status_label.setStyleSheet("font-size: 11px; color: #7A8392;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L193: `action_row.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L194: `"background: #FFFFFF; border-top: 1px solid #D4DAE3;"` -> replace hex with palette field
- L259: `item.setForeground(QColor("#B42E2E"))` -> replace hex with palette field
- L272: `empty.setStyleSheet("color: #7A8392; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L278: `AdvisorSeverity.BLOCKER: ("#B42E2E", "#FBE9E9", "#E5B4B4"),` -> replace hex with palette field
- L279: `AdvisorSeverity.WARNING: ("#9A6A17", "#FBF1DD", "#E5D2A2"),` -> replace hex with palette field
- L280: `AdvisorSeverity.SUGGESTION: ("#1F5BD8", "#E7EFFD", "#B7C9F0"),` -> replace hex with palette field
- L281: `AdvisorSeverity.INFO: ("#4E5866", "#F4F6FA", "#D4DAE3"),` -> replace hex with palette field
- L285: `fg, bg, border = color_by_severity.get(msg.severity, ("#4E5866", "#F4F6FA", "#D4DAE3"))` -> replace hex with palette field
- L287: `card.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L297: `t.setStyleSheet(f"color: {fg}; font-size: 11px; font-weight: 600;")` -> move to QSS rule + objectName; reference palette/tokens
- L302: `d.setStyleSheet("color: #4E5866; font-size: 11px;")` -> move to QSS rule + objectName; reference palette/tokens; replace hex with palette field
- L306: `btn.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
- L307: `"padding: 2px 8px; font-size: 11px; border: 1px solid #D4DAE3;"` -> replace hex with palette field
- L308: `"background: #FFFFFF; border-radius: 2px;"` -> replace hex with palette field

## `src/seeker_accounting/shared/ui/help_content.py`

- L3938: `<tr style="background:#f0f0f0;"><td><b>Situation</b></td><td><b>Recommended method</b></td></tr>` -> replace hex with palette field

## `src/seeker_accounting/shared/ui/styles/theme_manager.py`

- L22: `# subsequent toggle is a pure dict lookup + setStyleSheet — zero rebuild cost.` -> move to QSS rule + objectName; reference palette/tokens
- L53: `self._app.setStyleSheet(self._stylesheet_cache[normalized])` -> move to QSS rule + objectName; reference palette/tokens

## `src/seeker_accounting/shared/ui/table_delegates.py`

- L124: `editor.setStyleSheet(` -> move to QSS rule + objectName; reference palette/tokens
