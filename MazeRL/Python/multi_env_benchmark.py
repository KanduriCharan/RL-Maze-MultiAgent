"""Benchmark multiple Unity processes using the existing random-action loop."""

import argparse
import math
import multiprocessing as mp
import os
import signal
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from mlagents_envs import env_utils

from random_action_pov_test import (
    SimulationTimingChannel,
    connect_environment,
    run_actions,
)
from run_results import RESULTS_ROOT, RunResults, append_csv, new_run_id, valid_label


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-path", type=Path, required=True)
    parser.add_argument("--num-envs", type=int, default=1)

    counts = parser.add_mutually_exclusive_group(required=True)
    counts.add_argument("--arenas-per-env", type=int)
    counts.add_argument("--total-agents", type=int)

    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--offscreen", action="store_true")
    parser.add_argument("--experiment", default="scaleout")
    parser.add_argument("--decision-period-label", type=int, default=20)
    parser.add_argument("--base-port", type=int, default=5004)
    parser.add_argument("--timeout-wait", type=int, default=60)
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--run-timeout", type=int, default=3600)
    args = parser.parse_args()

    args.build_path = args.build_path.expanduser().resolve()
    if not args.build_path.exists():
        parser.error(f"Build does not exist: {args.build_path}")
    if args.num_envs < 1 or args.steps < 1 or args.warmup < 0:
        parser.error("num-envs/steps must be positive; warmup must be nonnegative")
    if not math.isfinite(args.time_scale) or args.time_scale <= 0:
        parser.error("time-scale must be finite and positive")
    if args.seed < 0 or args.seed + args.num_envs - 1 > 2**31 - 1:
        parser.error("Worker seeds must fit a nonnegative signed 32-bit integer")
    if not 1 <= args.decision_period_label <= 20:
        parser.error("decision-period-label must be from 1 to 20")
    if not 1 <= args.base_port <= 65535 - args.num_envs + 1:
        parser.error("Requested worker ports must fit within 1–65535")
    if min(args.timeout_wait, args.startup_timeout, args.run_timeout) <= 0:
        parser.error("Timeouts must be positive")
    if not valid_label(args.experiment):
        parser.error("experiment must use letters, numbers, underscores or hyphens")

    if args.arenas_per_env is not None:
        if args.arenas_per_env < 1:
            parser.error("arenas-per-env must be positive")
        arena_counts = [args.arenas_per_env] * args.num_envs
    else:
        if args.total_agents < args.num_envs:
            parser.error("total-agents must provide at least one arena per worker")
        count, remainder = divmod(args.total_agents, args.num_envs)
        arena_counts = [
            count + (worker_id < remainder)
            for worker_id in range(args.num_envs)
        ]

    if sum(arena_counts) > 2**31 - 1:
        parser.error("Total arena count exceeds the supported ID range")

    return args, arena_counts


def stop_unity(process):
    """Fallback for an owned Unity process if normal env.close() failed."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def worker_main(
    config, worker_id, arena_count, arena_offset, folder,
    messages, start_event, cancel_event, unity_pids, parent_pid,
):
    env = None
    unity_process = None
    payload = None
    error = None
    original_launch = env_utils.launch_executable

    # Parent handles terminal Ctrl+C. SIGTERM requests cooperative cancellation.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, lambda *_: cancel_event.set())

    def check_cancel():
        if cancel_event.is_set() or os.getppid() != parent_pid:
            raise RuntimeError("Benchmark cancelled or parent process exited")

    def tracked_launch(file_name, launch_args):
        nonlocal unity_process
        check_cancel()
        unity_process = original_launch(file_name, launch_args)
        unity_pids[worker_id] = unity_process.pid
        return unity_process

    def wait_for_start(spec):
        visual_shapes = [
            tuple(obs.shape)
            for obs in spec.observation_specs
            if len(obs.shape) == 3
        ]
        if visual_shapes != [(3, 84, 84)]:
            raise ValueError(
                f"Worker {worker_id}: expected one 84x84 RGB observation; "
                f"received {visual_shapes}"
            )

        messages.send(("ready", None))
        while not start_event.wait(timeout=0.1):
            check_cancel()
        check_cancel()

    try:
        args = SimpleNamespace(**config)
        args.arenas = arena_count
        args.seed = config["seed"] + worker_id
        args.save_pngs = False
        args.quiet = True

        results = RunResults(args, folder=folder)
        timing = SimulationTimingChannel()

        # This wrapper exists only in this Python worker. It records Unity's PID
        # even if connection setup fails before UnityEnvironment returns.
        env_utils.launch_executable = tracked_launch

        env = connect_environment(
            args, timing, results,
            worker_id=worker_id,
            base_port=args.base_port,
            timeout_wait=args.timeout_wait,
            arena_id_offset=arena_offset,
        )

        run_actions(
            env, args, timing, results,
            warmup=args.warmup,
            on_ready=wait_for_start,
            check_cancel=check_cancel,
        )

        payload = {
            "row": results.row,
            "finished": results.finished,
            "observations": results.observations,
            "pending_actions": len(results.pending),
        }

    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"

    finally:
        env_utils.launch_executable = original_launch

        try:
            if env is not None:
                env.close()
        except BaseException as exc:
            error = error or f"Unity close failed: {exc}"

        try:
            stop_unity(unity_process)
        except BaseException as exc:
            error = error or f"Unity cleanup failed: {exc}"

        if unity_process is None or unity_process.poll() is not None:
            unity_pids[worker_id] = 0

        try:
            messages.send(("error", error) if error else ("done", payload))
        except (BrokenPipeError, EOFError, OSError):
            pass
        messages.close()


def signal_owned_unity(unity_pids, sig):
    for pid in list(unity_pids):
        if pid:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass


def cleanup_workers(workers, cancel_event, start_event, unity_pids, timeout):
    cancel_event.set()
    start_event.set()

    # Allow blocked ML-Agents exchanges and normal env.close() to finish.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(worker.is_alive() for worker in workers):
            break
        time.sleep(0.1)

    # Unity starts in its own session, so stopping Python alone is insufficient.
    signal_owned_unity(unity_pids, signal.SIGTERM)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not any(worker.is_alive() for worker in workers):
            break
        time.sleep(0.1)

    signal_owned_unity(unity_pids, signal.SIGKILL)

    for worker in workers:
        if worker.is_alive():
            worker.kill()
        worker.join(timeout=5)


def collect_results(
    args, workers, receivers, start_event, cancel_event,
):
    ready = set()
    completed = {}
    closed = set()
    released_at = None
    startup_deadline = time.monotonic() + args.startup_timeout
    run_deadline = None

    while len(completed) < len(workers):
        for worker_id, receiver in enumerate(receivers):
            if worker_id in closed:
                continue

            while receiver.poll():
                try:
                    kind, payload = receiver.recv()
                except EOFError:
                    closed.add(worker_id)
                    if worker_id not in completed:
                        raise RuntimeError(
                            f"Worker {worker_id} exited without a result"
                        )
                    break

                if kind == "ready":
                    ready.add(worker_id)
                    print(
                        f"Worker {worker_id} ready "
                        f"on port {args.base_port + worker_id}",
                        flush=True,
                    )
                elif kind == "error":
                    raise RuntimeError(f"Worker {worker_id}: {payload}")
                elif kind == "done":
                    completed[worker_id] = payload

        for worker_id, worker in enumerate(workers):
            if worker.exitcode not in (None, 0):
                raise RuntimeError(
                    f"Worker {worker_id} exited with code {worker.exitcode}"
                )

        if released_at is None:
            if len(ready) == len(workers):
                released_at = time.perf_counter()
                start_event.set()
                run_deadline = time.monotonic() + args.run_timeout
                print("All workers ready. Measurement started.", flush=True)
            elif time.monotonic() >= startup_deadline:
                raise TimeoutError("Startup/warmup readiness deadline exceeded")
        elif time.monotonic() >= run_deadline:
            raise TimeoutError("Benchmark completion deadline exceeded")

        if cancel_event.is_set():
            raise RuntimeError("A worker requested cancellation")

        time.sleep(0.02)

    return released_at, completed


def write_results(args, arena_counts, run_folder, released_at, completed):
    worker_rows = []
    for worker_id in range(args.num_envs):
        result = completed[worker_id]
        row = dict(
            worker_id=worker_id,
            port=args.base_port + worker_id,
            **result["row"],
        )
        row["warmup_exchanges"] = args.warmup
        row["pending_actions_at_end"] = result["pending_actions"]
        row["environment_exchanges_per_second"] = (
            row["environment_exchanges"] / row["real_seconds"]
        )
        row["mean_exchange_seconds"] = (
            row["real_seconds"] / row["environment_exchanges"]
        )
        worker_rows.append(row)

    # macOS perf_counter uses a clock shared across processes.
    # Completion timestamps exclude worker shutdown and result-message delay.
    wall_seconds = max(
        result["finished"] for result in completed.values()
    ) - released_at
    if wall_seconds <= 0:
        raise RuntimeError("Invalid aggregate measurement duration")

    actions = sum(row["completed_agent_actions"] for row in worker_rows)
    observations = sum(
        result["observations"] for result in completed.values()
    )
    exchanges = sum(row["environment_exchanges"] for row in worker_rows)

    summary = {
        "mode": worker_rows[0]["mode"],
        "unity_processes": args.num_envs,
        "total_arenas": sum(arena_counts),
        "arena_distribution": "+".join(map(str, arena_counts)),
        "image_shape": worker_rows[0]["image_shape"],
        "decision_period_declared": args.decision_period_label,
        "time_scale": worker_rows[0]["time_scale"],
        "physics_timestep_seconds": worker_rows[0]["physics_timestep_seconds"],
        "base_action_seed": args.seed,
        "warmup_exchanges_per_worker": args.warmup,
        "measured_exchanges_per_worker": args.steps,
        "real_seconds": wall_seconds,
        "completed_agent_actions": actions,
        "agent_actions_per_second": actions / wall_seconds,
        "observations_per_second": observations / wall_seconds,
        "environment_exchanges_per_second": exchanges / wall_seconds,
        "successes": sum(row["successes"] for row in worker_rows),
        "timeouts": sum(row["timeouts"] for row in worker_rows),
    }

    for field in ("image_shape", "time_scale", "physics_timestep_seconds"):
        if len({row[field] for row in worker_rows}) != 1:
            raise RuntimeError(f"Workers disagree on {field}; results not saved")

    for row in worker_rows:
        append_csv(run_folder / "workers.csv", row)
        print(
            f"Worker {row['worker_id']}: "
            f"{row['agent_actions_per_second']:.2f} actions/sec",
            flush=True,
        )

    append_csv(run_folder / "summary.csv", summary)
    append_csv(RESULTS_ROOT / args.experiment / "scaleout_results.csv", summary)

    print(
        f"Aggregate: {summary['agent_actions_per_second']:.2f} actions/sec "
        f"over {wall_seconds:.2f} real seconds\n"
        f"Saved {run_folder}",
        flush=True,
    )


def main():
    args, arena_counts = parse_arguments()
    ctx = mp.get_context("spawn")
    start_event = ctx.Event()
    cancel_event = ctx.Event()
    unity_pids = ctx.Array("q", args.num_envs)
    workers = []
    receivers = []

    run_folder = RESULTS_ROOT / args.experiment / "runs" / new_run_id()
    run_folder.mkdir(parents=True, exist_ok=False)

    def handle_termination(*_):
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, handle_termination)

    try:
        offset = 0
        for worker_id, arena_count in enumerate(arena_counts):
            receiver, sender = ctx.Pipe(duplex=False)
            worker = ctx.Process(
                target=worker_main,
                args=(
                    vars(args), worker_id, arena_count, offset,
                    run_folder / f"worker_{worker_id}",
                    sender, start_event, cancel_event, unity_pids, os.getpid(),
                ),
                name=f"maze-worker-{worker_id}",
            )
            worker.start()
            sender.close()
            workers.append(worker)
            receivers.append(receiver)
            offset += arena_count

        released_at, completed = collect_results(
            args, workers, receivers, start_event, cancel_event,
        )

    except KeyboardInterrupt:
        print("Cancelled; no aggregate benchmark result saved.", flush=True)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Benchmark failed: {exc}", flush=True)
        raise SystemExit(1)
    finally:
        # Let the first cancellation finish cleanup without repeated interruption.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        cleanup_workers(
            workers, cancel_event, start_event, unity_pids,
            timeout=args.timeout_wait + 5,
        )
        for receiver in receivers:
            receiver.close()
        signal.signal(signal.SIGTERM, previous_handler)
        signal.signal(signal.SIGINT, signal.default_int_handler)

    write_results(args, arena_counts, run_folder, released_at, completed)


if __name__ == "__main__":
    main()
