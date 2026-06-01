PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_catalog_id INTEGER,
    pokedex_id INTEGER,
    name TEXT NOT NULL,
    game TEXT NOT NULL DEFAULT 'Pokemon',
    card_number TEXT,
    pokemon_name TEXT,
    rarity TEXT,
    holo_pattern TEXT,
    source_sequence INTEGER,
    tcgcollector_card_id INTEGER,
    card_detail_url TEXT,
    is_regional_exclusive INTEGER NOT NULL DEFAULT 0 CHECK (is_regional_exclusive IN (0, 1)),
    notes TEXT,
    primary_image_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (set_catalog_id) REFERENCES set_catalog(id),
    FOREIGN KEY (pokedex_id) REFERENCES pokedex(id)
);

CREATE TABLE IF NOT EXISTS card_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL UNIQUE,
    condition TEXT,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    cost_basis_cents INTEGER NOT NULL DEFAULT 0 CHECK (cost_basis_cents >= 0),
    acquisition_date TEXT,
    sale_status TEXT NOT NULL DEFAULT 'inventory',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pokedex (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pokedex_number INTEGER NOT NULL,
    pokemon_name TEXT NOT NULL,
    variant_name TEXT,
    form_name TEXT,
    source_slug TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_slug)
);

CREATE TABLE IF NOT EXISTS card_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    source_url TEXT,
    image_role TEXT NOT NULL DEFAULT 'reference',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS card_equivalents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    equivalent_card_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL DEFAULT 'same_card_other_language',
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY (equivalent_card_id) REFERENCES cards(id) ON DELETE CASCADE,
    CHECK (card_id <> equivalent_card_id),
    UNIQUE (card_id, equivalent_card_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS marketplace_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    website_url TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS grading_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    abbreviation TEXT NOT NULL UNIQUE,
    website_url TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS set_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL DEFAULT 'TCGcollector',
    source_region TEXT NOT NULL,
    language TEXT,
    tcgcollector_set_id INTEGER NOT NULL,
    set_name TEXT NOT NULL,
    set_code TEXT,
    release_date_text TEXT,
    release_year INTEGER,
    card_count INTEGER,
    set_url TEXT NOT NULL,
    slug TEXT,
    source_catalog_url TEXT,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, source_region, tcgcollector_set_id)
);

CREATE TABLE IF NOT EXISTS illustrators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    first_seen_year INTEGER,
    last_seen_year INTEGER,
    popularity_rating INTEGER CHECK (
        popularity_rating IS NULL
        OR (popularity_rating >= 1 AND popularity_rating <= 10)
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS card_illustrators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    illustrator_id INTEGER NOT NULL,
    source_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY (illustrator_id) REFERENCES illustrators(id) ON DELETE CASCADE,
    UNIQUE (card_id, illustrator_id)
);

CREATE TABLE IF NOT EXISTS raw_price_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    listing_type TEXT NOT NULL DEFAULT 'buy_it_now',
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'USD',
    condition TEXT,
    listing_url TEXT,
    seller_name TEXT,
    notes TEXT,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES marketplace_sources(id)
);

CREATE TABLE IF NOT EXISTS graded_price_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    grading_company TEXT NOT NULL,
    grade TEXT NOT NULL,
    listing_type TEXT NOT NULL DEFAULT 'buy_it_now',
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'USD',
    listing_url TEXT,
    seller_name TEXT,
    cert_number TEXT,
    notes TEXT,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES marketplace_sources(id)
);

CREATE TABLE IF NOT EXISTS grading_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    grading_company_id INTEGER,
    grading_company TEXT NOT NULL,
    service_level TEXT,
    grading_fee_cents INTEGER NOT NULL DEFAULT 0 CHECK (grading_fee_cents >= 0),
    inbound_shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK (inbound_shipping_cents >= 0),
    return_shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK (return_shipping_cents >= 0),
    marketplace_fee_rate REAL NOT NULL DEFAULT 0.13 CHECK (marketplace_fee_rate >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (grading_company_id) REFERENCES grading_companies(id)
);

CREATE TABLE IF NOT EXISTS grading_ev_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    grading_profile_id INTEGER NOT NULL,
    raw_sale_price_cents INTEGER NOT NULL CHECK (raw_sale_price_cents >= 0),
    raw_marketplace_fee_rate REAL NOT NULL DEFAULT 0.13 CHECK (raw_marketplace_fee_rate >= 0),
    expected_graded_gross_cents INTEGER NOT NULL,
    expected_graded_net_cents INTEGER NOT NULL,
    expected_raw_net_cents INTEGER NOT NULL,
    grading_ev_delta_cents INTEGER NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY (grading_profile_id) REFERENCES grading_profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS grade_population_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    grading_company TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    snapshot_label TEXT,
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    population_total INTEGER NOT NULL CHECK (population_total >= 0),
    gem_threshold_grade TEXT,
    gem_count INTEGER CHECK (gem_count IS NULL OR gem_count >= 0),
    gem_rate REAL CHECK (gem_rate IS NULL OR (gem_rate >= 0 AND gem_rate <= 1)),
    ten_plus_count INTEGER CHECK (ten_plus_count IS NULL OR ten_plus_count >= 0),
    ten_plus_rate REAL CHECK (ten_plus_rate IS NULL OR (ten_plus_rate >= 0 AND ten_plus_rate <= 1)),
    exact_card_data INTEGER NOT NULL DEFAULT 1 CHECK (exact_card_data IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
    UNIQUE (card_id, grading_company, source_name, snapshot_label, checked_at)
);

CREATE TABLE IF NOT EXISTS grade_population_snapshot_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    grade_label TEXT NOT NULL,
    population_count INTEGER NOT NULL CHECK (population_count >= 0),
    rate REAL CHECK (rate IS NULL OR (rate >= 0 AND rate <= 1)),
    higher_count INTEGER CHECK (higher_count IS NULL OR higher_count >= 0),
    higher_rate REAL CHECK (higher_rate IS NULL OR (higher_rate >= 0 AND higher_rate <= 1)),
    notes TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES grade_population_snapshots(id) ON DELETE CASCADE,
    UNIQUE (snapshot_id, grade_label)
);

CREATE TABLE IF NOT EXISTS grade_rate_reference_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grading_company_id INTEGER NOT NULL,
    source_name TEXT,
    source_url TEXT,
    source_card_id INTEGER,
    source_snapshot_id INTEGER,
    source_card_name TEXT,
    source_set_name TEXT,
    source_set_code TEXT,
    release_year INTEGER,
    region TEXT,
    language TEXT,
    print_family TEXT,
    card_category TEXT,
    rarity TEXT,
    grade_label TEXT NOT NULL,
    population_count INTEGER CHECK (population_count IS NULL OR population_count >= 0),
    population_total INTEGER CHECK (population_total IS NULL OR population_total >= 0),
    probability REAL NOT NULL CHECK (probability >= 0 AND probability <= 1),
    exact_card_data INTEGER NOT NULL DEFAULT 0 CHECK (exact_card_data IN (0, 1)),
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    checked_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (grading_company_id) REFERENCES grading_companies(id),
    FOREIGN KEY (source_card_id) REFERENCES cards(id) ON DELETE SET NULL,
    FOREIGN KEY (source_snapshot_id) REFERENCES grade_population_snapshots(id) ON DELETE SET NULL,
    UNIQUE (
        grading_company_id,
        source_name,
        source_card_name,
        source_set_name,
        source_set_code,
        grade_label,
        checked_at
    )
);

CREATE TABLE IF NOT EXISTS grade_rate_reference_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    grading_company_id INTEGER NOT NULL,
    min_release_year INTEGER,
    max_release_year INTEGER,
    region_filter TEXT,
    language_filter TEXT,
    print_family_filter TEXT,
    card_category_filter TEXT,
    rarity_filter TEXT,
    min_population_total INTEGER NOT NULL DEFAULT 0 CHECK (min_population_total >= 0),
    min_confidence REAL NOT NULL DEFAULT 0 CHECK (min_confidence >= 0 AND min_confidence <= 1),
    include_exact_card_data INTEGER NOT NULL DEFAULT 1 CHECK (include_exact_card_data IN (0, 1)),
    include_benchmark_data INTEGER NOT NULL DEFAULT 1 CHECK (include_benchmark_data IN (0, 1)),
    aggregation_method TEXT NOT NULL DEFAULT 'population_weighted_average',
    sample_limit INTEGER CHECK (sample_limit IS NULL OR sample_limit > 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (grading_company_id) REFERENCES grading_companies(id)
);

CREATE INDEX IF NOT EXISTS idx_cards_search ON cards(name, card_number);
DROP INDEX IF EXISTS idx_cards_sale_status;
CREATE INDEX IF NOT EXISTS idx_cards_set_catalog_id ON cards(set_catalog_id);
CREATE INDEX IF NOT EXISTS idx_cards_pokedex_id ON cards(pokedex_id);
CREATE INDEX IF NOT EXISTS idx_card_inventory_sale_status ON card_inventory(sale_status);
CREATE INDEX IF NOT EXISTS idx_card_inventory_card_id ON card_inventory(card_id);
DROP INDEX IF EXISTS idx_cards_set_number_language;
DROP INDEX IF EXISTS idx_cards_set_number_language_tcgcollector;
CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_set_catalog_number_tcgcollector
ON cards(set_catalog_id, card_number, tcgcollector_card_id);
CREATE INDEX IF NOT EXISTS idx_set_catalog_lookup
ON set_catalog(source_region, set_name, set_code);
CREATE INDEX IF NOT EXISTS idx_set_catalog_language
ON set_catalog(language);
CREATE INDEX IF NOT EXISTS idx_pokedex_name
ON pokedex(pokemon_name, variant_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_illustrators_name_nocase
ON illustrators(lower(name));
CREATE INDEX IF NOT EXISTS idx_card_illustrators_card
ON card_illustrators(card_id);
CREATE INDEX IF NOT EXISTS idx_card_illustrators_illustrator
ON card_illustrators(illustrator_id);

CREATE INDEX IF NOT EXISTS idx_raw_price_card_checked ON raw_price_records(card_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_graded_price_card_grade ON graded_price_records(card_id, grading_company, grade);
CREATE INDEX IF NOT EXISTS idx_ev_runs_card ON grading_ev_runs(card_id, calculated_at);
CREATE INDEX IF NOT EXISTS idx_grading_profiles_company
ON grading_profiles(grading_company_id);
CREATE INDEX IF NOT EXISTS idx_grade_population_snapshots_card
ON grade_population_snapshots(card_id, grading_company, checked_at);
CREATE INDEX IF NOT EXISTS idx_grade_population_rows_snapshot
ON grade_population_snapshot_rows(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_grade_rate_reference_company
ON grade_rate_reference_data(grading_company_id, grade_label);
CREATE INDEX IF NOT EXISTS idx_grade_rate_reference_filters
ON grade_rate_reference_data(release_year, region, language, print_family, card_category, rarity);
CREATE INDEX IF NOT EXISTS idx_grade_rate_reference_groups_company
ON grade_rate_reference_groups(grading_company_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_card_images_card_path_role
ON card_images(card_id, image_path, image_role);

CREATE TRIGGER IF NOT EXISTS trg_cards_updated_at
AFTER UPDATE ON cards
FOR EACH ROW
BEGIN
    UPDATE cards SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_card_inventory_updated_at
AFTER UPDATE ON card_inventory
FOR EACH ROW
BEGIN
    UPDATE card_inventory SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_set_catalog_updated_at
AFTER UPDATE ON set_catalog
FOR EACH ROW
BEGIN
    UPDATE set_catalog SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_pokedex_updated_at
AFTER UPDATE ON pokedex
FOR EACH ROW
BEGIN
    UPDATE pokedex SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_illustrators_updated_at
AFTER UPDATE ON illustrators
FOR EACH ROW
BEGIN
    UPDATE illustrators SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_illustrators_popularity_rating_insert
BEFORE INSERT ON illustrators
FOR EACH ROW
WHEN NEW.popularity_rating IS NOT NULL
    AND (NEW.popularity_rating < 1 OR NEW.popularity_rating > 10)
BEGIN
    SELECT RAISE(ABORT, 'illustrators.popularity_rating must be between 1 and 10');
END;

CREATE TRIGGER IF NOT EXISTS trg_illustrators_popularity_rating_update
BEFORE UPDATE OF popularity_rating ON illustrators
FOR EACH ROW
WHEN NEW.popularity_rating IS NOT NULL
    AND (NEW.popularity_rating < 1 OR NEW.popularity_rating > 10)
BEGIN
    SELECT RAISE(ABORT, 'illustrators.popularity_rating must be between 1 and 10');
END;

CREATE TRIGGER IF NOT EXISTS trg_grading_companies_updated_at
AFTER UPDATE ON grading_companies
FOR EACH ROW
BEGIN
    UPDATE grading_companies SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_grade_rate_reference_groups_updated_at
AFTER UPDATE ON grade_rate_reference_groups
FOR EACH ROW
BEGIN
    UPDATE grade_rate_reference_groups SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
