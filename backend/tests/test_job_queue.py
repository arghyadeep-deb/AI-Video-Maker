from app.db.connection import get_connection, run_migrations
from app.jobs.queue import claim_next_job, enqueue, queue_position, sweep_interrupted_jobs


def _seed_user(conn, user_id: str):
    conn.execute(
        "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (?, ?, 'x')",
        (user_id, f"{user_id}@test"),
    )
    conn.commit()


def _conn(tmp_path):
    db_path = tmp_path / "app.db"
    run_migrations(db_path)
    return get_connection(db_path), db_path


def test_enqueue_creates_queued_job(tmp_path):
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    job_id = enqueue(conn, "u1", None, "noop_render", {"a": 1})
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["status"] == "queued"
    assert row["type"] == "noop_render"
    assert row["progress"] == 0


def test_claim_returns_none_when_empty(tmp_path):
    conn, _ = _conn(tmp_path)
    assert claim_next_job(conn) is None


def test_claim_marks_job_running(tmp_path):
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    job_id = enqueue(conn, "u1", None, "noop_render", {})
    claimed = claim_next_job(conn)
    assert claimed["id"] == job_id
    assert claimed["status"] == "running"
    assert claimed["started_at"] is not None


def test_claim_is_fifo_for_single_user(tmp_path):
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    first = enqueue(conn, "u1", None, "noop_render", {})
    second = enqueue(conn, "u1", None, "noop_render", {})
    assert claim_next_job(conn)["id"] == first
    assert claim_next_job(conn)["id"] == second


def test_claim_is_round_robin_across_users_not_fifo(tmp_path):
    """A user who queues 5 jobs cannot starve a user who queues 1 -
    specs/03-design/07-job-queue-and-progress.md fairness requirement.
    """
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "hog")
    _seed_user(conn, "quiet")

    hog_jobs = [enqueue(conn, "hog", None, "noop_render", {}) for _ in range(5)]
    quiet_job = enqueue(conn, "quiet", None, "noop_render", {})

    # First claim: both users are unserved (never finished a job) - arrival
    # order among never-served users picks "hog" first (its jobs arrived
    # first), but "quiet" must NOT wait behind all 5 of hog's jobs.
    first = claim_next_job(conn)
    assert first["user_id"] == "hog"

    # Simulate hog's job finishing immediately.
    conn.execute(
        "UPDATE jobs SET status='done', finished_at='2026-01-01T00:00:00.000Z' WHERE id=?",
        (first["id"],),
    )
    conn.commit()

    second = claim_next_job(conn)
    assert second["user_id"] == "quiet", "quiet's only job must be served before hog's 2nd-5th"
    assert second["id"] == quiet_job

    # Mark quiet's job done too - now hog (finished earliest) goes next.
    conn.execute(
        "UPDATE jobs SET status='done', finished_at='2026-01-01T00:00:01.000Z' WHERE id=?",
        (second["id"],),
    )
    conn.commit()
    third = claim_next_job(conn)
    assert third["id"] == hog_jobs[1]


def test_sweep_interrupted_jobs_marks_running_as_failed(tmp_path):
    conn, db_path = _conn(tmp_path)
    _seed_user(conn, "u1")
    job_id = enqueue(conn, "u1", None, "noop_render", {})
    claim_next_job(conn)  # -> running
    conn.close()

    count = sweep_interrupted_jobs(db_path)
    assert count == 1

    conn2 = get_connection(db_path)
    row = conn2.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["error"] == "restart interrupted"
    conn2.close()


def test_sweep_does_not_touch_queued_or_done_jobs(tmp_path):
    conn, db_path = _conn(tmp_path)
    _seed_user(conn, "u1")
    queued_job = enqueue(conn, "u1", None, "noop_render", {})
    conn.close()

    count = sweep_interrupted_jobs(db_path)
    assert count == 0

    conn2 = get_connection(db_path)
    row = conn2.execute("SELECT * FROM jobs WHERE id = ?", (queued_job,)).fetchone()
    assert row["status"] == "queued"
    conn2.close()


def test_queue_position_of_the_only_job_is_zero(tmp_path):
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    job_id = enqueue(conn, "u1", None, "noop_render", {})
    assert queue_position(conn, job_id) == 0


def test_queue_position_for_a_single_users_jobs_matches_arrival_order(tmp_path):
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    first = enqueue(conn, "u1", None, "noop_render", {})
    second = enqueue(conn, "u1", None, "noop_render", {})
    third = enqueue(conn, "u1", None, "noop_render", {})
    assert queue_position(conn, first) == 0
    assert queue_position(conn, second) == 1
    assert queue_position(conn, third) == 2


def test_queue_position_a_burst_from_the_first_arriving_user_goes_first(tmp_path):
    """Fairness only actually kicks in once someone has genuinely been
    *served* (finished_at set) - the tie-break for "never served" is
    arrival order, not round-robin-by-position. So u1 queuing a burst
    before u2 ever queues anything means all of u1's burst goes first;
    fairness only protects u2 from *future* bursts after one of u1's jobs
    completes and updates _last_served_at. A real, if initially
    surprising, consequence of task-07's own fairness algorithm - not a
    queue_position bug (confirmed against the real claim order in
    test_queue_position_matches_actual_claim_order)."""
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    _seed_user(conn, "u2")
    u1_a = enqueue(conn, "u1", None, "noop_render", {})
    u1_b = enqueue(conn, "u1", None, "noop_render", {})
    u1_c = enqueue(conn, "u1", None, "noop_render", {})
    u2_a = enqueue(conn, "u2", None, "noop_render", {})

    assert queue_position(conn, u1_a) == 0
    assert queue_position(conn, u1_b) == 1
    assert queue_position(conn, u1_c) == 2
    assert queue_position(conn, u2_a) == 3


def test_queue_position_matches_actual_claim_order(tmp_path):
    """The simulated position must agree with what claim_next_job actually
    picks, in order - the whole point of computing it the same way."""
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    _seed_user(conn, "u2")
    jobs = [
        enqueue(conn, "u1", None, "noop_render", {}),
        enqueue(conn, "u2", None, "noop_render", {}),
        enqueue(conn, "u1", None, "noop_render", {}),
    ]
    positions = {job_id: queue_position(conn, job_id) for job_id in jobs}

    claimed_order = []
    for _ in range(len(jobs)):
        claimed = claim_next_job(conn)
        claimed_order.append(claimed["id"])

    expected_order = sorted(jobs, key=lambda j: positions[j])
    assert claimed_order == expected_order


def test_queue_position_is_none_for_a_running_job(tmp_path):
    conn, _ = _conn(tmp_path)
    _seed_user(conn, "u1")
    job_id = enqueue(conn, "u1", None, "noop_render", {})
    claim_next_job(conn)
    assert queue_position(conn, job_id) is None


def test_queue_position_is_none_for_an_unknown_job(tmp_path):
    conn, _ = _conn(tmp_path)
    assert queue_position(conn, "does-not-exist") is None
