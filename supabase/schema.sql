-- Transactions table
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    time VARCHAR(20) NOT NULL,
    total INTEGER NOT NULL,
    method VARCHAR(10) CHECK (method IN ('cash', 'mpesa', 'partial')),
    cash_amount INTEGER DEFAULT 0,
    mpesa_amount INTEGER DEFAULT 0,
    items JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Expenses table
CREATE TABLE expenses (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    time VARCHAR(20) NOT NULL,
    name VARCHAR(200) NOT NULL,
    amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trash table
CREATE TABLE trash (
    id BIGSERIAL PRIMARY KEY,
    item_type VARCHAR(10) CHECK (item_type IN ('sale', 'expense')),
    description TEXT,
    data JSONB,
    trashed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_transactions_date ON transactions(date DESC);
CREATE INDEX idx_expenses_date ON expenses(date DESC);
CREATE INDEX idx_trash_type ON trash(item_type);