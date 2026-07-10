"""Home GPU worker agent — task-20a, specs/03-design/11-gpu-worker.md.

Runs on the owner's Windows PC (RTX 5070 Ti). Pulls GPU jobs from the VM
over outbound HTTPS long-polls — no port forwarding, no public exposure —
runs them on the local GPU, uploads results, and deletes every local copy.
The owner's own GPU work always wins: auto-yield, instant reclaim (pause),
and a work-hours schedule are all enforced here, before any job is leased.
"""
__version__ = "1.0.0"
