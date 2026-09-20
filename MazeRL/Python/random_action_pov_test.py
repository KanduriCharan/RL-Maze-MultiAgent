"""Single-agent Editor smoke test; Python owns all random action selection."""
import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from mlagents_envs.base_env import ActionTuple
from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.side_channel.engine_configuration_channel import EngineConfigurationChannel


def visual_index(spec):
    candidates = []
    for index, observation in enumerate(spec.observation_specs):
        shape = tuple(observation.shape)
        print(f"Observation {index}: {observation.name}, shape={shape}", flush=True)
        if len(shape) == 3 and (shape[0] == 3 or shape[-1] == 3):
            candidates.append(index)
    if len(candidates) != 1:
        raise ValueError(f"Expected one RGB camera observation; found {candidates}.")
    index = candidates[0]
    shape = tuple(spec.observation_specs[index].shape)
    if shape[0] == 3 and shape[-1] == 3:
        raise ValueError(f"Ambiguous RGB channel axis: {shape}")
    layout = 'CHW -> HWC for PNG' if shape[0] == 3 else 'HWC'
    print(f"Using visual observation {index}: {layout}", flush=True)
    return index


def save_frame(frame, path):
    frame = np.asarray(frame)
    if frame.ndim == 3 and frame.shape[0] == 3:
        if frame.shape[-1] == 3:
            raise ValueError(f"Ambiguous RGB channel axis: {frame.shape}")
        # Reorder channels only; do not flip or rotate the camera image.
        frame = np.moveaxis(frame, 0, -1)
    if frame.ndim != 3 or frame.shape[-1] != 3 or not np.isfinite(frame).all():
        raise ValueError(f"Invalid RGB frame: {frame.shape}")
    if frame.min() < 0 or frame.max() > 1:
        raise ValueError("Expected normalized visual observations in [0, 1].")
    pixels = np.rint(frame * 255).astype(np.uint8)
    Image.fromarray(pixels).save(path)
    print(f"Saved {path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--seed', type=int, default=123)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'pov_snapshots')
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('--steps must be positive')
    output = args.output / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(args.seed)
    channel = EngineConfigurationChannel()
    channel.set_configuration_parameters(time_scale=1.0)
    env = None
    try:
        print('Waiting on port 5004. Now press Play in Unity (one arena).', flush=True)
        env = UnityEnvironment(file_name=None, seed=args.seed, base_port=5004,
                               timeout_wait=60, no_graphics=False, side_channels=[channel])
        env.reset()
        names = list(env.behavior_specs)
        if len(names) != 1 or names[0].split('?')[0] != 'MazeAgent':
            raise ValueError(f"Expected only MazeAgent; found {names}. Disable handshake agents.")
        behavior = names[0]
        spec = env.behavior_specs[behavior]
        print(f'Connected to behavior: {behavior}', flush=True)
        if spec.action_spec.continuous_size != 0 or tuple(spec.action_spec.discrete_branches) != (4, 3):
            raise ValueError(f'Expected discrete [4, 3]; got {spec.action_spec}')
        camera = visual_index(spec)
        decisions, terminals = env.get_steps(behavior)
        if len(decisions) != 1 or len(terminals):
            raise ValueError('Expected exactly one active agent at reset.')
        agent_id = int(decisions.agent_id[0])
        previous = decisions[agent_id].obs[camera].copy()
        save_frame(previous, output / 'step_000_initial.png')
        for step in range(1, args.steps + 1):
            movement = int(rng.integers(4))
            yaw = int(rng.integers(3))
            label = ('W', 'A', 'S', 'D')[movement]
            print(f'Step {step:03d} -> {label}, yaw={yaw}', flush=True)
            env.set_actions(behavior, ActionTuple(discrete=np.array([[movement, yaw]], dtype=np.int32)))
            env.step()
            decisions, terminals = env.get_steps(behavior)
            if len(terminals):
                if len(terminals) != 1 or agent_id not in terminals:
                    raise ValueError('Unexpected terminal agent identity.')
                frame = terminals[agent_id].obs[camera]
            else:
                if len(decisions) != 1 or agent_id not in decisions:
                    raise ValueError('Expected the same single agent after each step.')
                frame = decisions[agent_id].obs[camera]
            save_frame(frame, output / f'step_{step:03d}_{label}_yaw{yaw}.png')
            print(f'Mean image change: {np.abs(frame - previous).mean():.6f}', flush=True)
            previous = frame.copy()
            if len(terminals):
                print('Agent terminated; stopping after saving its final observation.', flush=True)
                break
    finally:
        if env is not None:
            env.close()
            print('Unity connection closed.', flush=True)


if __name__ == '__main__':
    main()
