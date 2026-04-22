from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base


class DepreciationMethod(Base):
    """Seeded catalog of built-in depreciation methods.

    Global reference table — no company_id scoping.
    All methods are built-in; user-defined formula methods are not supported.

    asset_family_code values:
        PPE              — property, plant and equipment
        INTANGIBLE       — intangible assets (e.g. amortization)
        NATURAL_RESOURCE — depletion-based (oil, gas, minerals, timber)
        TAX              — tax-basis methods (MACRS)

    Capability flags guide the UI and service layer:
        requires_settings       — asset must have an asset_depreciation_settings row
        requires_components     — uses child asset_components table
        requires_usage_records  — period amounts driven by asset_usage_records
        requires_pool           — uses asset_depreciation_pools / pool_members
        requires_depletion_profile — uses asset_depletion_profiles
        has_switch_to_sl        — declining-balance family supports SL switch option
    """

    __tablename__ = "depreciation_methods"
    __table_args__ = (UniqueConstraint("code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_family_code: Mapped[str] = mapped_column(String(30), nullable=False)

    # Capability flags
    requires_settings: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    requires_components: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    requires_usage_records: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    requires_pool: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    requires_depletion_profile: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    has_switch_to_sl: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
