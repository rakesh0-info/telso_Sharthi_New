BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_question_set_id_class'
          AND conrelid = 'telso_sar.question_set'::regclass
    ) THEN
        ALTER TABLE telso_sar.question_set
            ADD CONSTRAINT uq_question_set_id_class UNIQUE (id, class_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_class_section_id_class'
          AND conrelid = 'telso_sar.class_section'::regclass
    ) THEN
        ALTER TABLE telso_sar.class_section
            ADD CONSTRAINT uq_class_section_id_class UNIQUE (id, class_id);
    END IF;
END;
$$;

ALTER TABLE telso_sar.teacher_quiz_publication
    ADD COLUMN IF NOT EXISTS class_id INTEGER;

UPDATE telso_sar.teacher_quiz_publication AS publication
SET class_id = question_set.class_id
FROM telso_sar.question_set AS question_set
WHERE publication.question_set_id = question_set.id
  AND publication.class_id IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM telso_sar.teacher_quiz_publication
        WHERE class_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'Cannot assign class_id to every quiz publication. Resolve orphaned publications before retrying.';
    END IF;
END;
$$;

ALTER TABLE telso_sar.teacher_quiz_publication
    ALTER COLUMN class_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_teacher_quiz_publication_class'
          AND conrelid = 'telso_sar.teacher_quiz_publication'::regclass
    ) THEN
        ALTER TABLE telso_sar.teacher_quiz_publication
            ADD CONSTRAINT fk_teacher_quiz_publication_class
            FOREIGN KEY (class_id)
            REFERENCES telso_sar.class (id)
            ON DELETE RESTRICT;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_teacher_quiz_publication_question_set_class'
          AND conrelid = 'telso_sar.teacher_quiz_publication'::regclass
    ) THEN
        ALTER TABLE telso_sar.teacher_quiz_publication
            ADD CONSTRAINT fk_teacher_quiz_publication_question_set_class
            FOREIGN KEY (question_set_id, class_id)
            REFERENCES telso_sar.question_set (id, class_id)
            ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_teacher_quiz_publication_section_class'
          AND conrelid = 'telso_sar.teacher_quiz_publication'::regclass
    ) THEN
        ALTER TABLE telso_sar.teacher_quiz_publication
            ADD CONSTRAINT fk_teacher_quiz_publication_section_class
            FOREIGN KEY (section_id, class_id)
            REFERENCES telso_sar.class_section (id, class_id)
            ON DELETE CASCADE;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS ix_teacher_quiz_publication_class
    ON telso_sar.teacher_quiz_publication (class_id);

COMMIT;
