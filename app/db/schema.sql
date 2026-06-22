CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),

    name TEXT NOT NULL,
    description TEXT,
    price_cents INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'czk',

    image_id TEXT,
    orig_file_id TEXT,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cart_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),

    session_id TEXT NOT NULL,
    customer_email TEXT,
    customer_bank_account TEXT,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,

    shipping_method TEXT,
    shipping_price_cents INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),

    cart_session_id BIGINT REFERENCES cart_sessions(id),

    customer_email TEXT,
    customer_bank_account TEXT,

    status TEXT NOT NULL DEFAULT 'pending',

    stripe_session_id TEXT UNIQUE,
    stripe_payment_intent_id TEXT,

    total_cents INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'czk',

    shipping_method TEXT,
    shipping_price_cents INTEGER NOT NULL DEFAULT 0,

    shipped BOOLEAN NOT NULL DEFAULT FALSE,
    shipped_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS order_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),

    order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES products(id),

    name TEXT NOT NULL,
    price_cents INTEGER NOT NULL DEFAULT 0,
    quantity INTEGER NOT NULL DEFAULT 1,
    image_id TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),

    order_id BIGINT NOT NULL REFERENCES orders(id),
    invoice_number TEXT NOT NULL,
    file_path TEXT NOT NULL,

    locked BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS packing_slips (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),

    order_id BIGINT NOT NULL REFERENCES orders(id),
    file_path TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);