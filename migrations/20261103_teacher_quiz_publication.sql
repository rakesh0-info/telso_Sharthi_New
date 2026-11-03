BEGIN;

ALTER TABLE telso_sar.question_set
    ADD COLUMN section_id INTEGER
        CONSTRAINT fk_question_set_section
        REFERENCES telso_sar.class_section (id) ON DELETE RESTRICT;

CREATE INDEX ix_question_set_section_id
    ON telso_sar.question_set (section_id);

CREATE TABLE telso_sar.teacher_quiz_publication (
    id SERIAL PRIMARY KEY,
    question_set_id INTEGER NOT NULL
        REFERENCES telso_sar.question_set (id) ON DELETE CASCADE,
    section_id INTEGER NOT NULL
        REFERENCES telso_sar.class_section (id) ON DELETE CASCADE,
    published_by INTEGER NOT NULL
        REFERENCES telso_sar.users (id) ON DELETE RESTRICT,
    published_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_teacher_quiz_publication_section
        UNIQUE (question_set_id, section_id),
    CONSTRAINT ck_teacher_quiz_publication_published_by_positive
        CHECK (published_by > 0)
);

CREATE INDEX ix_teacher_quiz_publication_section
    ON telso_sar.teacher_quiz_publication (section_id);

COMMIT;
