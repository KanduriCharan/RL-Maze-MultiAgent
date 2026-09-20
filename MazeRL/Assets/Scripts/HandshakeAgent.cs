using Unity.MLAgents;
using Unity.MLAgents.Actuators;
using Unity.MLAgents.Sensors;
using UnityEngine;

public class HandshakeAgent : Agent
{
    public override void CollectObservations(VectorSensor sensor)
    {
        sensor.AddObservation(transform.position);
    }

    public override void OnActionReceived(ActionBuffers actions)
    {
        // No movement needed for handshake test.
    }

    public override void Heuristic(in ActionBuffers actionsOut)
    {
    }
}