"""Run random maze actions in the Editor or a build; record results and optional POV PNGs."""
import argparse
import math
import uuid
from pathlib import Path

import numpy as np
from PIL import Image
from mlagents_envs.base_env import ActionTuple
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel
from mlagents_envs.side_channel.side_channel import SideChannel

from run_results import RunResults, valid_label

# Receives the existing Unity simulation clock; no scene settings are modified here.
class SimulationTimingChannel(SideChannel):
    """Receive Unity's fixed simulation clock, independent of agent/episode counts."""
    def __init__(self):
        super().__init__(uuid.UUID('173f67d2-bc12-4e51-8524-1927df465930'))
        self.simulated_time = None
        self.fixed_delta_time = None
        self.time_scale = None
        self.samples = 0

    def on_message_received(self, msg):
        self.simulated_time = float(msg.read_string())
        self.fixed_delta_time = msg.read_float32()
        self.time_scale = msg.read_float32()
        self.samples += 1

    def require_sample(self):
        if self.simulated_time is None:
            raise RuntimeError('No Unity timing telemetry. Check MultiArenaManager and Unity compilation.')
        return self.simulated_time


def save_pngs(batch, camera_index, output, step, label, pending_actions, quiet=False):
    """Save each agent's RGB observation without changing image orientation."""
    for agent_id in batch.agent_id:
        frame = np.asarray(batch[agent_id].obs[camera_index])
        if frame.ndim == 3 and frame.shape[0] == 3:
            if frame.shape[-1] == 3:
                raise ValueError(f'Ambiguous RGB shape: {frame.shape}')
            frame = np.moveaxis(frame, 0, -1)
        if frame.ndim != 3 or frame.shape[-1] != 3 or not np.isfinite(frame).all():
            raise ValueError(f'Invalid RGB observation: {frame.shape}')
        if frame.min() < 0 or frame.max() > 1:
            raise ValueError('Expected image values in [0, 1].')
        folder = output / f'agent_{agent_id}'
        folder.mkdir(parents=True, exist_ok=True)
        action = pending_actions.pop(int(agent_id), 'initial')
        path = folder / f'step_{step:04d}_{action}_{label}.png'
        Image.fromarray(np.rint(frame * 255).astype(np.uint8)).save(path)
        if not quiet:
            print(f'Saved {path}', flush=True)


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=20, help='Number of environment exchanges')
    parser.add_argument('--seed', type=int, default=123, help='Random-action seed; separate from maze base seed')
    parser.add_argument('--save-pngs', action='store_true', help='Save per-agent POV images in the run folder')
    parser.add_argument('--build-path', type=Path, help='Path to the Unity build; omit for Editor mode')
    parser.add_argument('--offscreen', action='store_true', help='Run the build without a visible window')
    parser.add_argument('--time-scale', type=float, default=1.0)
    parser.add_argument('--arenas', type=int, help='Standalone arena count; Editor uses the Inspector')
    parser.add_argument('--experiment', default='baseline', help='Results folder label, not a Unity setting')
    parser.add_argument('--quiet', action='store_true', help='Skip per-action and per-image logging')
    parser.add_argument('--decision-period-label', type=int, default=10, help='Metadata only: enter the Inspector/build value; does NOT change Unity')

    args = parser.parse_args()
    if args.steps < 1 or args.seed < 0:
        parser.error('steps must be positive; seed must be nonnegative')
    if not math.isfinite(args.time_scale) or args.time_scale <= 0:
        parser.error('time-scale must be finite and positive')
    if not 1 <= args.decision_period_label <= 20:
        parser.error('decision-period-label must be from 1 to 20')
    if not valid_label(args.experiment):
        parser.error('experiment must use only letters, numbers, underscores or hyphens')
    if args.offscreen and args.build_path is None:
        parser.error('--offscreen requires --build-path')
    if args.arenas is not None and (args.arenas < 1 or args.build_path is None):
        parser.error('--arenas requires a positive count and --build-path')
    if args.build_path is not None:
        args.build_path = args.build_path.expanduser().resolve()
        if not args.build_path.exists():
            parser.error(f'Build does not exist: {args.build_path}')
    return args


def connect_environment(
    args, timing, results, *,
    worker_id=0, base_port=5004, timeout_wait=60,
    arena_id_offset=None,
):
    engine = EngineConfigurationChannel()
    engine.set_configuration_parameters(time_scale=args.time_scale)
    launch_args = []
    if args.build_path is None:
        print(f'Waiting on port {base_port}. Press Play in Unity Editor.', flush=True)
    else:
        launch_args = ['-logFile', str(results.folder / 'unity.log')]
        if args.arenas is not None:
            launch_args += ['--arenas', str(args.arenas)]
        if arena_id_offset is not None:
            launch_args += ['--arena-id-offset', str(arena_id_offset)]
        if args.offscreen:
            launch_args.append('-batchmode')
        else:
            launch_args += ['-screen-fullscreen', '0', '-screen-width', '640', '-screen-height', '360']
        print(f'Launching {args.build_path}', flush=True)
    return UnityEnvironment(
        file_name=str(args.build_path) if args.build_path else None,
        worker_id=worker_id, base_port=base_port,
        seed=args.seed, timeout_wait=timeout_wait,
        no_graphics=False, no_graphics_monitor=False,
        additional_args=launch_args, side_channels=[engine, timing],
    )


def run_actions(
    env, args, timing, results, *,
    warmup=0, on_ready=None, check_cancel=None,
):
    if warmup < 0:
        raise ValueError('warmup must be nonnegative')
    if warmup and args.save_pngs:
        raise ValueError('Warmup benchmarking does not support PNG saving.')

    env.reset()
    behaviors = list(env.behavior_specs)
    if len(behaviors) != 1 or behaviors[0].split('?')[0] != 'MazeAgent':
        raise ValueError(f'Expected only MazeAgent; found {behaviors}')
    behavior = behaviors[0]
    spec = env.behavior_specs[behavior]
    if spec.action_spec.continuous_size != 0 or tuple(spec.action_spec.discrete_branches) != (4, 3):
        raise ValueError('MazeAgent must have discrete action branches [4, 3].')
    decisions, terminals = env.get_steps(behavior)
    if not len(decisions) or len(terminals):
        raise ValueError('Expected active agents and no terminal steps after reset.')
    if args.arenas is not None and len(decisions) != args.arenas:
        raise ValueError(f'Requested {args.arenas} arenas but received {len(decisions)}. Check the build.')
    initial_agent_count = len(decisions)
    print(f'Connected to {behavior}: {len(decisions)} agents.', flush=True)
    for obs in spec.observation_specs:
        print(f'Observation {obs.name}: {obs.shape}', flush=True)

    pending_actions = {}
    if args.save_pngs:
        cameras = [i for i, obs in enumerate(spec.observation_specs)
                   if len(obs.shape) == 3 and (obs.shape[0] == 3 or obs.shape[-1] == 3)]
        if len(cameras) != 1:
            raise ValueError(f'Expected one RGB camera observation; found {cameras}')
        camera_index = cameras[0]
        output = results.folder / 'snapshots'
        save_pngs(decisions, camera_index, output, 0, 'decision', pending_actions, args.quiet)

    rng = np.random.default_rng(args.seed)
    for step in range(1 - warmup, args.steps + 1):
        if check_cancel is not None:
            check_cancel()

        if step == 1:
            if on_ready is not None:
                on_ready(spec)
            results.start(timing, behavior, spec, initial_agent_count)

        if len(decisions):
            # Action rows follow requesting agent IDs, including after episode resets.
            actions = np.empty((len(decisions), 2), dtype=np.int32)
            actions[:, 0] = rng.integers(4, size=len(decisions))  # W, A, S, D
            actions[:, 1] = rng.integers(3, size=len(decisions))  # No turn, left, right
            env.set_actions(behavior, ActionTuple(discrete=actions))
            if step > 0:
                results.actions_sent(decisions.agent_id)
            for agent_id, (move, turn) in zip(decisions.agent_id, actions):
                if args.save_pngs:
                    movement = ('W_forward', 'A_left', 'S_backward', 'D_right')[move]
                    turning = ('no_turn', 'turn_left', 'turn_right')[turn]
                    pending_actions[int(agent_id)] = f'{movement}_{turning}'
                if not args.quiet:
                    print(f'Step {step:03d} | Agent {agent_id}: '
                          f'{("W", "A", "S", "D")[move]}, '
                          f'{("no turn", "turn left", "turn right")[turn]}', flush=True)
        env.step()
        decisions, terminals = env.get_steps(behavior)
        if step > 0:
            results.received(step, decisions, terminals, timing)
        if args.save_pngs:
            save_pngs(terminals, camera_index, output, step, 'terminal', pending_actions, args.quiet)
            save_pngs(decisions, camera_index, output, step, 'decision', pending_actions, args.quiet)
        if not args.quiet:
            for agent_id, interrupted in zip(terminals.agent_id, terminals.interrupted):
                print(f'Agent {agent_id}: {"timeout" if interrupted else "success"}', flush=True)
    results.finish_measurement(timing)


def main():
    args = parse_arguments()
    results = RunResults(args)
    timing = SimulationTimingChannel()
    env = None
    try:
        try:
            env = connect_environment(args, timing, results)
            run_actions(env, args, timing, results)
        finally:
            if env is not None:
                env.close()
                print('Unity connection closed.', flush=True)
        results.complete()
    except KeyboardInterrupt:
        print('Run interrupted; no completed CSV result was saved.', flush=True)
        raise SystemExit(130)


if __name__ == '__main__':
    main()
