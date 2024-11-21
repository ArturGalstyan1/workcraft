CREATE INDEX idx_task_status_created
ON bountyboard (status, retry_on_failure, retry_count, task_name, created_at);
