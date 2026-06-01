"""SQLAlchemy ORM models for the existing SQLite schema.

The canonical schema is still db/schema.sql. These models are a forward path for
new scripts and for existing scripts as they are touched in future development.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("is_regional_exclusive IN (0, 1)", name="ck_cards_is_regional_exclusive_bool"),
        Index("idx_cards_search", "name", "card_number"),
        Index("idx_cards_set_catalog_id", "set_catalog_id"),
        Index("idx_cards_pokedex_id", "pokedex_id"),
        Index("idx_cards_set_catalog_number_tcgcollector", "set_catalog_id", "card_number", "tcgcollector_card_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    set_catalog_id: Mapped[int | None] = mapped_column(ForeignKey("set_catalog.id"))
    pokedex_id: Mapped[int | None] = mapped_column(ForeignKey("pokedex.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    game: Mapped[str] = mapped_column(Text, nullable=False, default="Pokemon")
    card_number: Mapped[str | None] = mapped_column(Text)
    pokemon_name: Mapped[str | None] = mapped_column(Text)
    rarity: Mapped[str | None] = mapped_column(Text)
    holo_pattern: Mapped[str | None] = mapped_column(Text)
    source_sequence: Mapped[int | None] = mapped_column(Integer)
    tcgcollector_card_id: Mapped[int | None] = mapped_column(Integer)
    card_detail_url: Mapped[str | None] = mapped_column(Text)
    is_regional_exclusive: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    primary_image_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    set_catalog: Mapped[SetCatalog | None] = relationship(back_populates="cards")
    pokedex: Mapped[Pokedex | None] = relationship(back_populates="cards")
    inventory: Mapped[CardInventory | None] = relationship(back_populates="card", uselist=False, cascade="all, delete-orphan")
    images: Mapped[list[CardImage]] = relationship(back_populates="card", cascade="all, delete-orphan")
    illustrator_links: Mapped[list[CardIllustrator]] = relationship(back_populates="card", cascade="all, delete-orphan")
    raw_price_records: Mapped[list[RawPriceRecord]] = relationship(back_populates="card", cascade="all, delete-orphan")
    graded_price_records: Mapped[list[GradedPriceRecord]] = relationship(back_populates="card", cascade="all, delete-orphan")
    grading_ev_runs: Mapped[list[GradingEvRun]] = relationship(back_populates="card", cascade="all, delete-orphan")
    population_snapshots: Mapped[list[GradePopulationSnapshot]] = relationship(back_populates="card", cascade="all, delete-orphan")
    equivalent_links: Mapped[list[CardEquivalent]] = relationship(
        back_populates="card",
        cascade="all, delete-orphan",
        foreign_keys="CardEquivalent.card_id",
    )
    equivalent_of_links: Mapped[list[CardEquivalent]] = relationship(
        back_populates="equivalent_card",
        cascade="all, delete-orphan",
        foreign_keys="CardEquivalent.equivalent_card_id",
    )
    grade_rate_reference_rows: Mapped[list[GradeRateReferenceData]] = relationship(back_populates="source_card")


class CardInventory(Base):
    __tablename__ = "card_inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_card_inventory_quantity_nonnegative"),
        CheckConstraint("cost_basis_cents >= 0", name="ck_card_inventory_cost_basis_nonnegative"),
        Index("idx_card_inventory_sale_status", "sale_status"),
        Index("idx_card_inventory_card_id", "card_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, unique=True)
    condition: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cost_basis_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acquisition_date: Mapped[str | None] = mapped_column(Text)
    sale_status: Mapped[str] = mapped_column(Text, nullable=False, default="inventory")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    card: Mapped[Card] = relationship(back_populates="inventory")


class Pokedex(Base):
    __tablename__ = "pokedex"
    __table_args__ = (
        UniqueConstraint("source_slug"),
        Index("idx_pokedex_name", "pokemon_name", "variant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pokedex_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pokemon_name: Mapped[str] = mapped_column(Text, nullable=False)
    variant_name: Mapped[str | None] = mapped_column(Text)
    form_name: Mapped[str | None] = mapped_column(Text)
    source_slug: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    cards: Mapped[list[Card]] = relationship(back_populates="pokedex")


class SetCatalog(Base):
    __tablename__ = "set_catalog"
    __table_args__ = (
        UniqueConstraint("source_name", "source_region", "tcgcollector_set_id"),
        Index("idx_set_catalog_lookup", "source_region", "set_name", "set_code"),
        Index("idx_set_catalog_language", "language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False, default="TCGcollector")
    source_region: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text)
    tcgcollector_set_id: Mapped[int] = mapped_column(Integer, nullable=False)
    set_name: Mapped[str] = mapped_column(Text, nullable=False)
    set_code: Mapped[str | None] = mapped_column(Text)
    release_date_text: Mapped[str | None] = mapped_column(Text)
    release_year: Mapped[int | None] = mapped_column(Integer)
    card_count: Mapped[int | None] = mapped_column(Integer)
    set_url: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str | None] = mapped_column(Text)
    source_catalog_url: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    cards: Mapped[list[Card]] = relationship(back_populates="set_catalog")


class CardImage(Base):
    __tablename__ = "card_images"
    __table_args__ = (Index("idx_card_images_card_path_role", "card_id", "image_path", "image_role", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    image_role: Mapped[str] = mapped_column(Text, nullable=False, default="reference")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    card: Mapped[Card] = relationship(back_populates="images")


class CardEquivalent(Base):
    __tablename__ = "card_equivalents"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_card_equivalents_confidence_range"),
        CheckConstraint("card_id <> equivalent_card_id", name="ck_card_equivalents_not_self"),
        UniqueConstraint("card_id", "equivalent_card_id", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    equivalent_card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False, default="same_card_other_language")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    card: Mapped[Card] = relationship(back_populates="equivalent_links", foreign_keys=[card_id])
    equivalent_card: Mapped[Card] = relationship(back_populates="equivalent_of_links", foreign_keys=[equivalent_card_id])


class MarketplaceSource(Base):
    __tablename__ = "marketplace_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    website_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    raw_price_records: Mapped[list[RawPriceRecord]] = relationship(back_populates="source")
    graded_price_records: Mapped[list[GradedPriceRecord]] = relationship(back_populates="source")


class GradingCompany(Base):
    __tablename__ = "grading_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    abbreviation: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    website_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    profiles: Mapped[list[GradingProfile]] = relationship(back_populates="grading_company_record")
    grade_rate_reference_rows: Mapped[list[GradeRateReferenceData]] = relationship(back_populates="grading_company")
    grade_rate_reference_groups: Mapped[list[GradeRateReferenceGroup]] = relationship(back_populates="grading_company")


class Illustrator(Base):
    __tablename__ = "illustrators"
    __table_args__ = (
        CheckConstraint(
            "popularity_rating IS NULL OR (popularity_rating >= 1 AND popularity_rating <= 10)",
            name="ck_illustrators_popularity_rating_range",
        ),
        Index("idx_illustrators_name_nocase", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    first_seen_year: Mapped[int | None] = mapped_column(Integer)
    last_seen_year: Mapped[int | None] = mapped_column(Integer)
    popularity_rating: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    card_links: Mapped[list[CardIllustrator]] = relationship(back_populates="illustrator", cascade="all, delete-orphan")


class CardIllustrator(Base):
    __tablename__ = "card_illustrators"
    __table_args__ = (
        UniqueConstraint("card_id", "illustrator_id"),
        Index("idx_card_illustrators_card", "card_id"),
        Index("idx_card_illustrators_illustrator", "illustrator_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    illustrator_id: Mapped[int] = mapped_column(ForeignKey("illustrators.id", ondelete="CASCADE"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    card: Mapped[Card] = relationship(back_populates="illustrator_links")
    illustrator: Mapped[Illustrator] = relationship(back_populates="card_links")


class RawPriceRecord(Base):
    __tablename__ = "raw_price_records"
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_raw_price_records_price_nonnegative"),
        CheckConstraint("shipping_cents >= 0", name="ck_raw_price_records_shipping_nonnegative"),
        Index("idx_raw_price_card_checked", "card_id", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("marketplace_sources.id"), nullable=False)
    checked_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    listing_type: Mapped[str] = mapped_column(Text, nullable=False, default="buy_it_now")
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    shipping_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="USD")
    condition: Mapped[str | None] = mapped_column(Text)
    listing_url: Mapped[str | None] = mapped_column(Text)
    seller_name: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    card: Mapped[Card] = relationship(back_populates="raw_price_records")
    source: Mapped[MarketplaceSource] = relationship(back_populates="raw_price_records")


class GradedPriceRecord(Base):
    __tablename__ = "graded_price_records"
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_graded_price_records_price_nonnegative"),
        CheckConstraint("shipping_cents >= 0", name="ck_graded_price_records_shipping_nonnegative"),
        Index("idx_graded_price_card_grade", "card_id", "grading_company", "grade"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("marketplace_sources.id"), nullable=False)
    checked_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    grading_company: Mapped[str] = mapped_column(Text, nullable=False)
    grade: Mapped[str] = mapped_column(Text, nullable=False)
    listing_type: Mapped[str] = mapped_column(Text, nullable=False, default="buy_it_now")
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    shipping_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="USD")
    listing_url: Mapped[str | None] = mapped_column(Text)
    seller_name: Mapped[str | None] = mapped_column(Text)
    cert_number: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    card: Mapped[Card] = relationship(back_populates="graded_price_records")
    source: Mapped[MarketplaceSource] = relationship(back_populates="graded_price_records")


class GradingProfile(Base):
    __tablename__ = "grading_profiles"
    __table_args__ = (
        CheckConstraint("grading_fee_cents >= 0", name="ck_grading_profiles_fee_nonnegative"),
        CheckConstraint("inbound_shipping_cents >= 0", name="ck_grading_profiles_inbound_shipping_nonnegative"),
        CheckConstraint("return_shipping_cents >= 0", name="ck_grading_profiles_return_shipping_nonnegative"),
        CheckConstraint("marketplace_fee_rate >= 0", name="ck_grading_profiles_marketplace_fee_nonnegative"),
        Index("idx_grading_profiles_company", "grading_company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    grading_company_id: Mapped[int | None] = mapped_column(ForeignKey("grading_companies.id"))
    grading_company: Mapped[str] = mapped_column(Text, nullable=False)
    service_level: Mapped[str | None] = mapped_column(Text)
    grading_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inbound_shipping_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    return_shipping_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marketplace_fee_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.13)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    grading_company_record: Mapped[GradingCompany | None] = relationship(back_populates="profiles")
    grading_ev_runs: Mapped[list[GradingEvRun]] = relationship(back_populates="grading_profile")


class GradingEvRun(Base):
    __tablename__ = "grading_ev_runs"
    __table_args__ = (
        CheckConstraint("raw_sale_price_cents >= 0", name="ck_grading_ev_runs_raw_sale_nonnegative"),
        CheckConstraint("raw_marketplace_fee_rate >= 0", name="ck_grading_ev_runs_raw_fee_nonnegative"),
        Index("idx_ev_runs_card", "card_id", "calculated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    grading_profile_id: Mapped[int] = mapped_column(ForeignKey("grading_profiles.id", ondelete="CASCADE"), nullable=False)
    raw_sale_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_marketplace_fee_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.13)
    expected_graded_gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_graded_net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_raw_net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    grading_ev_delta_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    calculated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    notes: Mapped[str | None] = mapped_column(Text)

    card: Mapped[Card] = relationship(back_populates="grading_ev_runs")
    grading_profile: Mapped[GradingProfile] = relationship(back_populates="grading_ev_runs")


class GradePopulationSnapshot(Base):
    __tablename__ = "grade_population_snapshots"
    __table_args__ = (
        CheckConstraint("population_total >= 0", name="ck_grade_population_snapshots_total_nonnegative"),
        CheckConstraint("gem_count IS NULL OR gem_count >= 0", name="ck_grade_population_snapshots_gem_count_nonnegative"),
        CheckConstraint("gem_rate IS NULL OR (gem_rate >= 0 AND gem_rate <= 1)", name="ck_grade_population_snapshots_gem_rate_range"),
        CheckConstraint("ten_plus_count IS NULL OR ten_plus_count >= 0", name="ck_grade_population_snapshots_ten_plus_count_nonnegative"),
        CheckConstraint("ten_plus_rate IS NULL OR (ten_plus_rate >= 0 AND ten_plus_rate <= 1)", name="ck_grade_population_snapshots_ten_plus_rate_range"),
        CheckConstraint("exact_card_data IN (0, 1)", name="ck_grade_population_snapshots_exact_card_data_bool"),
        UniqueConstraint("card_id", "grading_company", "source_name", "snapshot_label", "checked_at"),
        Index("idx_grade_population_snapshots_card", "card_id", "grading_company", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    grading_company: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    snapshot_label: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    population_total: Mapped[int] = mapped_column(Integer, nullable=False)
    gem_threshold_grade: Mapped[str | None] = mapped_column(Text)
    gem_count: Mapped[int | None] = mapped_column(Integer)
    gem_rate: Mapped[float | None] = mapped_column(Float)
    ten_plus_count: Mapped[int | None] = mapped_column(Integer)
    ten_plus_rate: Mapped[float | None] = mapped_column(Float)
    exact_card_data: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    card: Mapped[Card] = relationship(back_populates="population_snapshots")
    rows: Mapped[list[GradePopulationSnapshotRow]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")
    grade_rate_reference_rows: Mapped[list[GradeRateReferenceData]] = relationship(back_populates="source_snapshot")


class GradePopulationSnapshotRow(Base):
    __tablename__ = "grade_population_snapshot_rows"
    __table_args__ = (
        CheckConstraint("population_count >= 0", name="ck_grade_population_rows_population_nonnegative"),
        CheckConstraint("rate IS NULL OR (rate >= 0 AND rate <= 1)", name="ck_grade_population_rows_rate_range"),
        CheckConstraint("higher_count IS NULL OR higher_count >= 0", name="ck_grade_population_rows_higher_count_nonnegative"),
        CheckConstraint("higher_rate IS NULL OR (higher_rate >= 0 AND higher_rate <= 1)", name="ck_grade_population_rows_higher_rate_range"),
        UniqueConstraint("snapshot_id", "grade_label"),
        Index("idx_grade_population_rows_snapshot", "snapshot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("grade_population_snapshots.id", ondelete="CASCADE"), nullable=False)
    grade_label: Mapped[str] = mapped_column(Text, nullable=False)
    population_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[float | None] = mapped_column(Float)
    higher_count: Mapped[int | None] = mapped_column(Integer)
    higher_rate: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    snapshot: Mapped[GradePopulationSnapshot] = relationship(back_populates="rows")


class GradeRateReferenceData(Base):
    __tablename__ = "grade_rate_reference_data"
    __table_args__ = (
        CheckConstraint("population_count IS NULL OR population_count >= 0", name="ck_grade_rate_reference_population_count_nonnegative"),
        CheckConstraint("population_total IS NULL OR population_total >= 0", name="ck_grade_rate_reference_population_total_nonnegative"),
        CheckConstraint("probability >= 0 AND probability <= 1", name="ck_grade_rate_reference_probability_range"),
        CheckConstraint("exact_card_data IN (0, 1)", name="ck_grade_rate_reference_exact_card_data_bool"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_grade_rate_reference_confidence_range"),
        UniqueConstraint(
            "grading_company_id",
            "source_name",
            "source_card_name",
            "source_set_name",
            "source_set_code",
            "grade_label",
            "checked_at",
        ),
        Index("idx_grade_rate_reference_company", "grading_company_id", "grade_label"),
        Index("idx_grade_rate_reference_filters", "release_year", "region", "language", "print_family", "card_category", "rarity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grading_company_id: Mapped[int] = mapped_column(ForeignKey("grading_companies.id"), nullable=False)
    source_name: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id", ondelete="SET NULL"))
    source_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("grade_population_snapshots.id", ondelete="SET NULL"))
    source_card_name: Mapped[str | None] = mapped_column(Text)
    source_set_name: Mapped[str | None] = mapped_column(Text)
    source_set_code: Mapped[str | None] = mapped_column(Text)
    release_year: Mapped[int | None] = mapped_column(Integer)
    region: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    print_family: Mapped[str | None] = mapped_column(Text)
    card_category: Mapped[str | None] = mapped_column(Text)
    rarity: Mapped[str | None] = mapped_column(Text)
    grade_label: Mapped[str] = mapped_column(Text, nullable=False)
    population_count: Mapped[int | None] = mapped_column(Integer)
    population_total: Mapped[int | None] = mapped_column(Integer)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    exact_card_data: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    checked_at: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    grading_company: Mapped[GradingCompany] = relationship(back_populates="grade_rate_reference_rows")
    source_card: Mapped[Card | None] = relationship(back_populates="grade_rate_reference_rows")
    source_snapshot: Mapped[GradePopulationSnapshot | None] = relationship(back_populates="grade_rate_reference_rows")


class GradeRateReferenceGroup(Base):
    __tablename__ = "grade_rate_reference_groups"
    __table_args__ = (
        CheckConstraint("min_population_total >= 0", name="ck_grade_rate_reference_groups_min_population_nonnegative"),
        CheckConstraint("min_confidence >= 0 AND min_confidence <= 1", name="ck_grade_rate_reference_groups_min_confidence_range"),
        CheckConstraint("include_exact_card_data IN (0, 1)", name="ck_grade_rate_reference_groups_include_exact_bool"),
        CheckConstraint("include_benchmark_data IN (0, 1)", name="ck_grade_rate_reference_groups_include_benchmark_bool"),
        CheckConstraint("sample_limit IS NULL OR sample_limit > 0", name="ck_grade_rate_reference_groups_sample_limit_positive"),
        Index("idx_grade_rate_reference_groups_company", "grading_company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    grading_company_id: Mapped[int] = mapped_column(ForeignKey("grading_companies.id"), nullable=False)
    min_release_year: Mapped[int | None] = mapped_column(Integer)
    max_release_year: Mapped[int | None] = mapped_column(Integer)
    region_filter: Mapped[str | None] = mapped_column(Text)
    language_filter: Mapped[str | None] = mapped_column(Text)
    print_family_filter: Mapped[str | None] = mapped_column(Text)
    card_category_filter: Mapped[str | None] = mapped_column(Text)
    rarity_filter: Mapped[str | None] = mapped_column(Text)
    min_population_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    include_exact_card_data: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    include_benchmark_data: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    aggregation_method: Mapped[str] = mapped_column(Text, nullable=False, default="population_weighted_average")
    sample_limit: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    grading_company: Mapped[GradingCompany] = relationship(back_populates="grade_rate_reference_groups")
