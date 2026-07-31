-- Healthcare Claims Extraction Platform Database Schema

-- Extraction results table
CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    form_type TEXT,  -- tier_a, tier_b, tier_c, tier_d, unknown
    status TEXT,  -- ok, failed, skipped
    mean_confidence REAL,
    cost REAL,
    processing_time REAL,  -- seconds
    llm_provider TEXT,
    result_json TEXT,  -- full JSON result
    image_path TEXT
);

-- Processing logs table
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_id INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level TEXT,  -- INFO, WARNING, ERROR
    stage TEXT,  -- preprocessing, classification, extraction, validation
    message TEXT,
    FOREIGN KEY (extraction_id) REFERENCES extractions(id)
);

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings
INSERT OR IGNORE INTO settings (key, value) VALUES 
    ('llm_provider', 'auto'),
    ('confidence_threshold', '50.0'),
    ('force_escalate_service_lines', 'true'),
    ('force_escalate_revenue_lines', 'true'),
    ('force_escalate_total_charge', 'true'),
    ('show_costs', 'true'),
    ('show_savings', 'true');

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_extractions_date ON extractions(upload_date);
CREATE INDEX IF NOT EXISTS idx_extractions_status ON extractions(status);
CREATE INDEX IF NOT EXISTS idx_extractions_form_type ON extractions(form_type);
CREATE INDEX IF NOT EXISTS idx_logs_extraction_id ON logs(extraction_id);
