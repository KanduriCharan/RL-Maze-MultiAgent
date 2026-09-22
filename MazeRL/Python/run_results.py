"""Measure CLI runs and append completed results to an experiment CSV."""
import csv
import fcntl
import math
import time
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / 'benchmark_results'


def valid_label(value):
    return bool(value) and all(c.isascii() and (c.isalnum() or c in '_-') for c in value)


def new_run_id():
    return datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8]


def append_csv(path, row):
    with path.open('a+', newline='') as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        file.seek(0)
        header = next(csv.reader(file), None)
        if header is not None and header != list(row):
            raise ValueError(f'CSV schema differs in {path}. Choose a new experiment name.')
        file.seek(0, 2)
        writer = csv.DictWriter(file, fieldnames=list(row))
        if header is None:
            writer.writeheader()
        writer.writerow(row)


class RunResults:
    def __init__(self, args, folder=None):
        self.run_id = new_run_id()
        self.folder = (
            Path(folder) if folder is not None
            else RESULTS_ROOT / args.experiment / 'runs' / self.run_id
        )
        self.folder.mkdir(parents=True, exist_ok=False)
        self.config = {key: str(value) if isinstance(value, Path) else value
                       for key, value in vars(args).items()}
        self.config['run_id'] = self.run_id
        self.pending = set()
        self.completed = self.observations = self.successes = self.timeouts = 0
        self.batch = 0

    def start(self, timing, behavior, spec, agent_count):
        self.simulation_start = timing.require_sample()
        if not math.isfinite(self.simulation_start):
            raise ValueError('Invalid Unity simulation clock.')
        if not math.isclose(timing.time_scale, self.config['time_scale'], rel_tol=1e-5):
            raise ValueError('Unity did not apply the requested time scale.')
        if not timing.fixed_delta_time or timing.fixed_delta_time <= 0:
            raise ValueError('Invalid Unity physics timestep.')
        self.fixed_delta = timing.fixed_delta_time
        self.actual_time_scale = timing.time_scale
        self.samples = timing.samples
        self.metadata = {
            'mode': ('offscreen_standalone' if self.config['offscreen'] else 'headed_standalone')
                    if self.config['build_path'] else 'headed_editor',
            'arena_count': agent_count,
            'image_shape': '|'.join('x'.join(map(str, obs.shape)) for obs in spec.observation_specs),
            'decision_period_declared': self.config['decision_period_label'],
            'time_scale': timing.time_scale,
            'physics_timestep_seconds': timing.fixed_delta_time,
            'action_seed': self.config['seed'],
            'environment_exchanges': self.config['steps'],
        }
        self.started = time.perf_counter()

    def actions_sent(self, agent_ids):
        self.pending.update(map(int, agent_ids))

    def received(self, batch, decisions, terminals, timing):
        if timing.samples <= self.samples:
            raise RuntimeError('Unity timing telemetry stopped updating.')
        if timing.fixed_delta_time != self.fixed_delta or timing.time_scale != self.actual_time_scale:
            raise RuntimeError('Unity timing settings changed during the run.')
        self.samples = timing.samples
        self.batch = batch
        self.observations += len(decisions) + len(terminals)
        # Fresh episode observations are not responses to an action in that episode.
        for steps in (terminals, decisions):
            for agent_id in steps.agent_id:
                if int(agent_id) in self.pending:
                    self.pending.remove(int(agent_id))
                    self.completed += 1
        timeouts = sum(bool(value) for value in terminals.interrupted)
        self.timeouts += timeouts
        self.successes += len(terminals) - timeouts

    def finish_measurement(self, timing):
        self.finished = time.perf_counter()
        elapsed = self.finished - self.started
        simulated = timing.require_sample() - self.simulation_start
        if not math.isfinite(simulated) or simulated <= 0 or elapsed <= 0:
            raise RuntimeError('Simulation or wall clock did not advance.')
        self.row = dict(self.metadata, **{
            'real_seconds': elapsed,
            'simulated_seconds': simulated,
            'simulation_speed_x': simulated / elapsed,
            'completed_agent_actions': self.completed,
            'successes': self.successes,
            'timeouts': self.timeouts,
            'agent_actions_per_second': self.completed / elapsed,
            'observations_per_second': self.observations / elapsed,
        })

    def complete(self):
        # Call only after Unity closes cleanly; interrupted/failed runs are not benchmarks.
        path = self.folder.parent.parent / 'results.csv'
        append_csv(path, self.row)
        print(f"Simulation speed: {self.row['simulation_speed_x']:.3f}x; "
              f"agent actions/s: {self.row['agent_actions_per_second']:.2f}\nSaved {path}", flush=True)
