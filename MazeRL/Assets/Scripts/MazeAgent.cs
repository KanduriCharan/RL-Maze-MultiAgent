using System;
using Unity.MLAgents;
using Unity.MLAgents.Actuators;
using UnityEngine;

[RequireComponent(typeof(PlayerController))]
public class MazeAgent : Agent
{
    [SerializeField, Min(0f)] private float yawSpeed = 90f;

    private PlayerController movement;
    private MouseLook look;
    private bool pythonControl;

    public override void Initialize()
    {
        movement = GetComponent<PlayerController>();
        look = GetComponentInChildren<MouseLook>(true);

        if (look == null)
            throw new InvalidOperationException("MazeAgent requires the player's MouseLook camera.");

        pythonControl = Academy.Instance.IsCommunicatorOn;
        movement.SetExternalControl(pythonControl);
        look.SetExternalControl(pythonControl);
    }

    public override void OnActionReceived(ActionBuffers actions)
    {
        if (!pythonControl)
            return;

        var discrete = actions.DiscreteActions;
        if (discrete.Length != 2)
            throw new InvalidOperationException("MazeAgent expects discrete branches [4, 3].");

        // Movement: 0=W, 1=A (strafe), 2=S, 3=D (strafe).
        // Yaw: 0=none, 1=left, 2=right.
        float yaw = DecodeDirection(discrete[1]);
        look.ApplyLook(yaw * yawSpeed * Time.fixedDeltaTime);
        movement.ApplyAgentAction(discrete[0], Time.fixedDeltaTime);
    }

    public override void Heuristic(in ActionBuffers actionsOut)
    {
        // Without Python, the existing keyboard/mouse scripts retain control.
        actionsOut.DiscreteActions.Clear();
    }

    private static float DecodeDirection(int action)
    {
        switch (action)
        {
            case 0: return 0f;
            case 1: return -1f;
            case 2: return 1f;
            default: throw new ArgumentOutOfRangeException(nameof(action));
        }
    }
}
