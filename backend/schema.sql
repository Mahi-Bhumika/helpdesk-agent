create extension if not exists vector;

-- TENANTS
create table tenants (
    tenant_id uuid primary key default gen_random_uuid(),
    company_name text not null,
    type_of_business text,
    subscription_plan text,
    stripe_customer_id text,
    stripe_subscription_id text,
    subscription_status text,
    bot_name text,
    greeting_message text,
    theme_color text,
    invite_token text unique default encode(gen_random_bytes(16), 'hex'),
    created_at timestamptz default now()
);

-- USERS
create table users (
    user_id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(tenant_id) on delete cascade,
    name text,
    email text unique not null,
    password_hash text not null,
    role text not null default 'member', -- 'owner' | 'member'
    status text not null default 'active',
    invited_by_user_id uuid references users(user_id),
    invited_at timestamptz,
    accepted_at timestamptz,
    created_at timestamptz default now()
);

-- DOCUMENTS
create table documents (
    document_id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(tenant_id) on delete cascade,
    uploaded_by uuid references users(user_id),
    file_url text,
    format text,
    status text default 'uploaded', -- 'uploaded' | 'processing' | 'ready' | 'failed'
    theme text,
    created_at timestamptz default now()
);

-- DOCUMENT_CHUNKS
create table document_chunks (
    chunk_id uuid primary key default gen_random_uuid(),
    document_id uuid references documents(document_id) on delete cascade,
    tenant_id uuid references tenants(tenant_id) on delete cascade,
    chunk_text text not null,
    embedding vector(384), -- adjust dimension to match your embedding model in Week 2
    chunk_index int,
    created_at timestamptz default now()
);

-- END_USERS
create table end_users (
    end_user_id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(tenant_id) on delete cascade,
    name text,
    email text,
    created_at timestamptz default now()
);

-- CHAT_SESSIONS
create table chat_sessions (
    session_id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(tenant_id) on delete cascade,
    end_user_id uuid references end_users(end_user_id), -- nullable: anonymous by default
    start_datetime timestamptz default now(),
    end_datetime timestamptz,
    customer_satisfaction int,
    textual_feedback text,
    created_at timestamptz default now()
);

-- MESSAGES
create table messages (
    message_id uuid primary key default gen_random_uuid(),
    session_id uuid references chat_sessions(session_id) on delete cascade,
    tenant_id uuid references tenants(tenant_id) on delete cascade,
    sender text not null, -- 'user' | 'bot'
    content text not null,
    sentiment text,
    response_latency_ms int,
    created_at timestamptz default now()
);

-- MESSAGE_SOURCES
create table message_sources (
    message_id uuid references messages(message_id) on delete cascade,
    chunk_id uuid references document_chunks(chunk_id) on delete cascade,
    relevance_score float,
    primary key (message_id, chunk_id)
);