# Phase 2 — Iceberg Experiments

## idempotent_rerun

- rows_after_run_1: 3
- snapshots_after_run_1: 1
- rows_after_run_2: 3
- snapshots_after_run_2: 2
- idempotent: True

## time_travel

- snapshot_before_update: 4685380735047462271
- current_value_after_update: changed
- value_read_via_time_travel: original
- time_travel_recovers_old_value: True

## schema_evolution

- files_before_add_column: 2
- files_after_add_column: 2
- snapshots_before_add_column: 2
- snapshots_after_add_column: 2
- existing_row_new_column_value: None
- add_column_rewrote_no_data: True

## partition_evolution

- file_count_by_spec_id_after_batch_1: {0: 2}
- file_count_by_spec_id_after_batch_2: {1: 2, 0: 2}
- old_files_kept_old_spec: True
- new_files_use_new_spec: True

## small_file_compaction

- files_before: 20
- rewritten_data_files_count: 20
- added_data_files_count: 1
- files_after: 1
