using UnityEngine;
using Unity.MLAgents;
using Unity.MLAgents.Sensors;

public class MultiArenaManager : MonoBehaviour
{
    [Header("Spawning")]
    [SerializeField] private GameObject arenaPrefab;
    [SerializeField, Min(1)] private int environmentCount = 4;
    [SerializeField, Min(1)] private int columns = 2;
    [SerializeField, Min(1f)] private float safetyMargin = 10f;
    [SerializeField] private int baseSeed = 1000;

    [Header("Manual Testing")]
    [SerializeField, Min(0)] private int controlledArenaId = 0;

    private void Start()
    {
        if (arenaPrefab == null ||
            environmentCount < 1 ||
            columns < 1 ||
            controlledArenaId < 0 ||
            controlledArenaId >= environmentCount)
        {
            Debug.LogError(
                "Assign ArenaPrefab and valid count, columns, and controlled arena ID.",
                this
            );
            return;
        }

        EpisodeManager template =
            arenaPrefab.GetComponentInChildren<EpisodeManager>(true);

        if (template == null || template.mazeGenerator == null)
        {
            Debug.LogError(
                "ArenaPrefab needs an EpisodeManager with a MazeGenerator reference.",
                this
            );
            return;
        }

        MazeGenerator maze = template.mazeGenerator;

        if (maze.width < 1 || maze.height < 1 || maze.cellSize <= 0f)
        {
            Debug.LogError("Maze dimensions must be positive.", this);
            return;
        }

        float margin = Mathf.Max(1f, safetyMargin);
        float spacingX = maze.width * maze.cellSize + margin;
        float spacingZ = maze.height * maze.cellSize + margin;

        for (int id = 0; id < environmentCount; id++)
        {
            int column = id % columns;
            int row = id / columns;

            GameObject arena = Instantiate(arenaPrefab, transform);
            arena.name = $"Arena_{id}";

            arena.transform.localPosition =
                new Vector3(column * spacingX, 0f, row * spacingZ);
            arena.transform.localRotation = Quaternion.identity;

            EpisodeManager episode =
                arena.GetComponentInChildren<EpisodeManager>(true);

            bool manualControl = id == controlledArenaId;

            ConfigureControl(episode, manualControl);
            episode.Initialize(id, baseSeed);
        }
    }

    private void ConfigureControl(
        EpisodeManager episode,
        bool enabled)
    {
        Transform player = episode.player;

        bool pythonControl = Academy.Instance.IsCommunicatorOn;
        player.GetComponent<PlayerController>().enabled = pythonControl || enabled;
        player.GetComponentInChildren<MouseLook>(true).enabled = pythonControl || enabled;

        // Sensors still capture observations when automatic screen rendering is disabled.
        CameraSensorComponent sensor = player.GetComponent<CameraSensorComponent>();
        if (sensor != null)
            sensor.RuntimeCameraEnable = enabled;
        player.GetComponentInChildren<Camera>(true).enabled = enabled;

        foreach (GoalDetector detector in episode.goal.GetComponentsInChildren<GoalDetector>(true))
            detector.enabled = true;
        player.GetComponentInChildren<AudioListener>(true).enabled = enabled;
    }
}