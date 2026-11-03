BEGIN;

ALTER TABLE telso_sar.question_set
    ADD COLUMN school_id INTEGER;

UPDATE telso_sar.question_set AS question_set
SET school_id = teacher.school_id
FROM telso_sar.teacher AS teacher
WHERE teacher.user_id = question_set.created_by
  AND EXISTS (
      SELECT 1
      FROM telso_sar.school_classes AS school_classes
      WHERE school_classes.school_id = teacher.school_id
        AND school_classes.class_id = question_set.class_id
  );

WITH school_admin_candidates AS (
    SELECT question_set.id AS question_set_id, school_classes.school_id
    FROM telso_sar.question_set AS question_set
    JOIN telso_sar.school_admin_assignments AS assignments
        ON assignments.admin_id = question_set.created_by
    JOIN telso_sar.school_classes AS school_classes
        ON school_classes.school_id = assignments.school_id
        AND school_classes.class_id = question_set.class_id
    WHERE question_set.school_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM telso_sar.teacher AS teacher
          WHERE teacher.user_id = question_set.created_by
      )
),
unique_class_candidates AS (
    SELECT question_set.id AS question_set_id, MIN(school_classes.school_id) AS school_id
    FROM telso_sar.question_set AS question_set
    JOIN telso_sar.school_classes AS school_classes
        ON school_classes.class_id = question_set.class_id
    WHERE question_set.school_id IS NULL
      AND NOT EXISTS (
          SELECT 1
          FROM telso_sar.school_admin_assignments AS assignments
          WHERE assignments.admin_id = question_set.created_by
      )
    GROUP BY question_set.id
    HAVING COUNT(*) = 1
),
all_candidates AS (
    SELECT question_set_id, school_id FROM school_admin_candidates
    UNION
    SELECT question_set_id, school_id FROM unique_class_candidates
),
unique_candidates AS (
    SELECT question_set_id, MIN(school_id) AS school_id
    FROM all_candidates
    GROUP BY question_set_id
    HAVING COUNT(DISTINCT school_id) = 1
)
UPDATE telso_sar.question_set AS question_set
SET school_id = unique_candidates.school_id
FROM unique_candidates
WHERE question_set.id = unique_candidates.question_set_id
  AND question_set.school_id IS NULL;

DO $$
DECLARE
    unresolved_count INTEGER;
    invalid_mapping_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unresolved_count
    FROM telso_sar.question_set
    WHERE school_id IS NULL;

    IF unresolved_count > 0 THEN
        RAISE EXCEPTION
            'Cannot assign school ownership to % existing question set(s). Resolve their school_id manually, then rerun this migration.',
            unresolved_count;
    END IF;

    SELECT COUNT(*) INTO invalid_mapping_count
    FROM telso_sar.question_set AS question_set
    WHERE NOT EXISTS (
        SELECT 1
        FROM telso_sar.school_classes AS school_classes
        WHERE school_classes.school_id = question_set.school_id
          AND school_classes.class_id = question_set.class_id
    )
    OR NOT EXISTS (
        SELECT 1
        FROM telso_sar.class_subjects AS class_subjects
        WHERE class_subjects.class_id = question_set.class_id
          AND class_subjects.subject_id = question_set.subject_id
    )
    OR NOT EXISTS (
        SELECT 1
        FROM telso_sar.chapter AS chapter
        WHERE chapter.id = question_set.chapter_id
          AND chapter.subject_id = question_set.subject_id
    )
    OR EXISTS (
        SELECT 1
        FROM telso_sar.teacher AS teacher
        WHERE teacher.user_id = question_set.created_by
          AND teacher.school_id <> question_set.school_id
    )
    OR (
        EXISTS (
            SELECT 1
            FROM telso_sar.school_admin_assignments AS assignments
            WHERE assignments.admin_id = question_set.created_by
        )
        AND NOT EXISTS (
            SELECT 1
            FROM telso_sar.school_admin_assignments AS assignments
            WHERE assignments.admin_id = question_set.created_by
              AND assignments.school_id = question_set.school_id
        )
    )
    OR (
        question_set.topic_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1
            FROM telso_sar.topic AS topic
            WHERE topic.id = question_set.topic_id
              AND topic.chapter_id = question_set.chapter_id
        )
    );

    IF invalid_mapping_count > 0 THEN
        RAISE EXCEPTION
            '% existing question set(s) have invalid school/class/subject/chapter/topic mappings. Correct them before rerunning this migration.',
            invalid_mapping_count;
    END IF;
END;
$$;

ALTER TABLE telso_sar.question_set
    ALTER COLUMN school_id SET NOT NULL;

ALTER TABLE telso_sar.question_set
    ADD CONSTRAINT fk_question_set_school
    FOREIGN KEY (school_id)
    REFERENCES telso_sar.school (id)
    ON DELETE RESTRICT;

CREATE INDEX ix_question_set_school_id
    ON telso_sar.question_set (school_id);

COMMIT;
