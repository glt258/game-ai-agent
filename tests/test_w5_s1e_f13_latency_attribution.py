from agents.reliability import LiveExecutionProgress, OperationDeadline


def test_f13_progress_attributes_budget_with_monotonic_clock() -> None:
    now = [100.0]

    def clock() -> float:
        return now[0]

    deadline = OperationDeadline(90.0, monotonic=clock)
    progress = LiveExecutionProgress(deadline=deadline)

    progress.set_queue_wait_ms(125.0)
    progress.mark_action_round(round_index=3, tool_invocation="optional", tool_count=2)
    progress.logical_invocation_started()
    now[0] += 12.5
    progress.mark_phase("FINALIZATION_CONTEXT")
    now[0] += 2.0
    progress.mark_phase("FINAL_PROVIDER")
    progress.provider_attempt_started(effective_attempt_timeout_ms=30_000.0)

    snapshot = progress.freeze(timeout_source="LIVE_EXECUTION_BUDGET")
    data = snapshot.to_dict()
    assert data["queue_wait_ms"] == 125.0
    assert data["logical_invocations_started"] == 1
    assert data["logical_invocation_started_offset_ms"] == 0.0
    assert data["logical_invocation_remaining_budget_ms"] == 90_000.0
    assert data["provider_attempts_started"] == 1
    assert data["current_provider_attempt_index"] == 1
    assert data["final_provider_start_offset_ms"] == 14_500.0
    assert data["final_provider_remaining_budget_ms"] == 75_500.0
    assert data["provider_call_in_flight"] is True
    assert "F13_SUPER_SECRET_VALUE" not in repr(data)


def test_f13_deadline_remaining_is_bounded_and_monotonic() -> None:
    now = [0.0]

    def clock() -> float:
        return now[0]

    deadline = OperationDeadline(1.0, monotonic=clock)
    assert deadline.elapsed_ms() == 0.0
    assert deadline.remaining_ms() == 1000.0
    now[0] = 0.25
    assert deadline.elapsed_ms() == 250.0
    assert deadline.remaining_ms() == 750.0
    now[0] = 2.0
    assert deadline.remaining_ms() == 0.0
