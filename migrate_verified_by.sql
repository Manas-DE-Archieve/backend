ALTER TABLE persons ADD COLUMN verified_by VARCHAR(10) DEFAULT NULL;

UPDATE persons SET verified_by = 'ai' WHERE status = 'verified' AND document_id IS NOT NULL;

UPDATE persons SET verified_by = 'human' WHERE status = 'verified' AND document_id IS NULL;