-- ============================================================================
-- AVRY-Careers Schema Migration 001
-- Creates vacancies and applications tables with indexes
-- ============================================================================

-- Vacancies table
CREATE TABLE IF NOT EXISTS vacancies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    department VARCHAR(255),
    location VARCHAR(255),
    employment_type VARCHAR(50),
    description JSONB NOT NULL,
    requirements JSONB,
    screening_questions JSONB DEFAULT '[]',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    posted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Applications table
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vacancy_id UUID NOT NULL REFERENCES vacancies(id) ON DELETE RESTRICT,
    full_name_encrypted BYTEA NOT NULL,
    email_encrypted BYTEA NOT NULL,
    phone_encrypted BYTEA,
    cover_letter TEXT,
    github_url TEXT,
    linkedin_url TEXT,
    cv_file_path TEXT NOT NULL,
    cv_original_filename VARCHAR(500),
    screening_responses JSONB DEFAULT '[]',
    status VARCHAR(30) NOT NULL DEFAULT 'submitted',
    tags JSONB DEFAULT '[]',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_vacancies_status_posted ON vacancies(status, posted_at DESC)
    WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_applications_vacancy_id ON applications(vacancy_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
