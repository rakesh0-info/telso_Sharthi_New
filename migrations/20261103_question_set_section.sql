BEGIN;

ALTER TABLE telso_sar.question_set
    ADD COLUMN IF NOT EXISTS section_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_question_set_section'
          AND conrelid = 'telso_sar.question_set'::regclass
    ) THEN
        ALTER TABLE telso_sar.question_set
            ADD CONSTRAINT fk_question_set_section
            FOREIGN KEY (section_id)
            REFERENCES telso_sar.class_section (id)
            ON DELETE RESTRICT;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS ix_question_set_section_id
    ON telso_sar.question_set (section_id);

COMMIT;
