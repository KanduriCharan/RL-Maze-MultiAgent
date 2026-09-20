"""Multi-agent Editor smoke test; Python owns all random action selection."""
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


def random_actions(agent_ids, rng):
    """Rows must follow DecisionSteps.agent_id order, not sorted IDs."""
    discrete = np.empty((len(agent_ids), 2), dtype=np.int32)
    discrete[:, 0] = rng.integers(4, size=len(agent_ids))
    discrete[:, 1] = rng.integers(3, size=len(agent_ids))
    labels = {int(agent_id): (('W', 'A', 'S', 'D')[int(row[0])], int(row[1]))
              for agent_id, row in zip(agent_ids, discrete)}
    return ActionTuple(discrete=discrete), labels


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
        print('Waiting on port 5004. Now press Play in Unity (configured arenas).', flush=True)
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
        if not len(decisions) or len(terminals):
            raise ValueError('Expected active agents and no terminal steps at reset.')
        expected_ids = set(map(int, decisions.agent_id))
        print(f'Connected agents: {sorted(expected_ids)}', flush=True)
        for agent_id in expected_ids:
            folder = output / f'agent_{agent_id}'
            folder.mkdir()
            save_frame(decisions[agent_id].obs[camera], folder / 'step_000_initial.png')
        for step in range(1, args.steps + 1):
            actions, labels = random_actions(decisions.agent_id, rng)
            previous = {int(i): decisions[int(i)].obs[camera].copy()
                        for i in decisions.agent_id}
            for agent_id, (label, yaw) in labels.items():
                print(f'Step {step:03d} agent {agent_id} -> {label}, yaw={yaw}', flush=True)
            env.set_actions(behavior, actions)
            env.step()
            decisions, terminals = env.get_steps(behavior)
            # All arenas use the same decision period. Match by ID, never returned row order.
            returned_ids = set(map(int, decisions.agent_id)) | set(map(int, terminals.agent_id))
            if returned_ids != expected_ids:
                raise ValueError('Agent set changed. This test expects fixed, synchronized arenas.')
            for agent_id, (label, yaw) in labels.items():
                result = terminals if agent_id in terminals else decisions
                frame = result[agent_id].obs[camera]
                suffix = '_terminal' if agent_id in terminals else ''
                save_frame(frame, output / f'agent_{agent_id}' /
                           f'step_{step:03d}_{label}_yaw{yaw}{suffix}.png')
                print(f'Agent {agent_id} mean image change: '
                      f'{np.abs(frame - previous[agent_id]).mean():.6f}', flush=True)
            if len(terminals):
                print('Terminal observations saved; stopping. Episode reset integration is not enabled.', flush=True)
                break
    finally:
        if env is not None:
            env.close()
            print('Unity connection closed.', flush=True)


if __name__ == '__main__':
    main()
