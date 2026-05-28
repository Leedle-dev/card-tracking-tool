PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_catalog_id INTEGER,
    pokedex_id INTEGER,
    name TEXT NOT NULL,
    game TEXT NOT NULL DEFAULT 'Pokemon',
    set_name TEXT,
    set_code TEXT,
    card_number TEXT,
    pokemon_name TEXT,
    pokemon_index INTEGER,
    variant_code TEXT,
    rarity TEXT,
    holo_pattern TEXT,
    source_sequence INTEGER,
    tcgcollector_card_id INTEGER,
    card_detail_url TEXT,
    language TEXT NOT NULL DEFAULT 'Simplified Chinese',
    region TEXT,
    release_year INTEGER,
    is_chinese_exclusive INTEGER NOT NULL DEFAULT 0 CHECK (is_chinese_exclusive IN (0, 1)),
    condition TEXT,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    cost_basis_cents INTEGER NOT NULL DEFAULT 0 CHECK (cost_basis_cents >= 0),
    acquisition_date TEXT,
    sale_status TEXT NOT NULL DEFAULT 'inventory',
    notes TEXT,
    primary_image_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (set_catalog_id) REFERENCES set_catalog(id),
    FOREIGN KEY (pokedex_id) REFERENCES pokedex(id)
);

CREATE TABLE IF NOT EXISTS pokedex (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pokedex_number INTEGER NOT NULL UNIQUE,
    pokemon_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    source_url TEXT,
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
    grading_company TEXT NOT NULL,
    service_level TEXT,
    grading_fee_cents INTEGER NOT NULL DEFAULT 0 CHECK (grading_fee_cents >= 0),
    inbound_shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK (inbound_shipping_cents >= 0),
    return_shipping_cents INTEGER NOT NULL DEFAULT 0 CHECK (return_shipping_cents >= 0),
    marketplace_fee_rate REAL NOT NULL DEFAULT 0.13 CHECK (marketplace_fee_rate >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS grading_ev_assumptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    grading_profile_id INTEGER NOT NULL,
    grade TEXT NOT NULL,
    probability REAL NOT NULL CHECK (probability >= 0 AND probability <= 1),
    expected_sale_price_cents INTEGER NOT NULL CHECK (expected_sale_price_cents >= 0),
    notes TEXT,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE,
    FOREIGN KEY (grading_profile_id) REFERENCES grading_profiles(id) ON DELETE CASCADE,
    UNIQUE (card_id, grading_profile_id, grade)
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

CREATE INDEX IF NOT EXISTS idx_cards_search ON cards(name, set_name, card_number, language);
CREATE INDEX IF NOT EXISTS idx_cards_sale_status ON cards(sale_status);
CREATE INDEX IF NOT EXISTS idx_cards_set_catalog_id ON cards(set_catalog_id);
CREATE INDEX IF NOT EXISTS idx_cards_pokedex_id ON cards(pokedex_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_set_number_language
ON cards(set_code, card_number, language);
CREATE INDEX IF NOT EXISTS idx_set_catalog_lookup
ON set_catalog(source_region, set_name, set_code);
CREATE INDEX IF NOT EXISTS idx_set_catalog_language
ON set_catalog(language);
CREATE INDEX IF NOT EXISTS idx_pokedex_name
ON pokedex(pokemon_name);
CREATE INDEX IF NOT EXISTS idx_card_illustrators_card
ON card_illustrators(card_id);
CREATE INDEX IF NOT EXISTS idx_card_illustrators_illustrator
ON card_illustrators(illustrator_id);

CREATE INDEX IF NOT EXISTS idx_raw_price_card_checked ON raw_price_records(card_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_graded_price_card_grade ON graded_price_records(card_id, grading_company, grade);
CREATE INDEX IF NOT EXISTS idx_ev_runs_card ON grading_ev_runs(card_id, calculated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_card_images_card_path_role
ON card_images(card_id, image_path, image_role);

CREATE TRIGGER IF NOT EXISTS trg_cards_updated_at
AFTER UPDATE ON cards
FOR EACH ROW
BEGIN
    UPDATE cards SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
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
