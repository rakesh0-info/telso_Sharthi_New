BEGIN;

ALTER TABLE telso_sar.internal_exam
    ADD COLUMN IF NOT EXISTS end_at TIMESTAMP WITH TIME ZONE;

UPDATE telso_sar.internal_exam
SET end_at = start_at + (duration_minutes * INTERVAL '1 minute')
WHERE end_at IS NULL;

ALTER TABLE telso_sar.internal_exam
    ALTER COLUMN end_at SET NOT NULL;

ALTER TABLE telso_sar.internal_exam
    DROP CONSTRAINT IF EXISTS ck_internal_exam_status;

UPDATE telso_sar.internal_exam
SET status = CASE
    WHEN status = 'cancelled' THEN 'cancelled'
    WHEN CURRENT_TIMESTAMP >= end_at THEN 'completed'
    WHEN CURRENT_TIMESTAMP >= start_at THEN 'active'
    ELSE 'scheduled'
END;

ALTER TABLE telso_sar.internal_exam
    ADD CONSTRAINT ck_internal_exam_status
    CHECK (status IN ('scheduled', 'active', 'completed', 'cancelled'));

CREATE INDEX IF NOT EXISTS ix_internal_exam_pending_section_start
    ON telso_sar.internal_exam (school_id, class_id, section_id, start_at)
    WHERE status = 'scheduled';

CREATE INDEX IF NOT EXISTS ix_internal_exam_active_section_end
    ON telso_sar.internal_exam (school_id, class_id, section_id, end_at)
    WHERE status = 'active';

COMMIT;
