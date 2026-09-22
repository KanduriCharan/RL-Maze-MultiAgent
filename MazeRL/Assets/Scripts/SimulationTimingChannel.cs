using System;
using System.Globalization;
using UnityEngine;
using Unity.MLAgents.SideChannels;

// Host-level telemetry; simulation time is shared by all arenas, not summed per agent.
public sealed class SimulationTimingChannel : SideChannel
{
    public SimulationTimingChannel()
    {
        ChannelId = new Guid("173f67d2-bc12-4e51-8524-1927df465930");
    }

    public void RecordStep(int step)
    {
        using (var message = new OutgoingMessage())
        {
            // Preserve the double-precision clock across the side channel.
            message.WriteString(Time.fixedTimeAsDouble.ToString("R", CultureInfo.InvariantCulture));
            message.WriteFloat32(Time.fixedDeltaTime);
            message.WriteFloat32(Time.timeScale);
            QueueMessageToSend(message);
        }
    }

    protected override void OnMessageReceived(IncomingMessage message) { }
}
