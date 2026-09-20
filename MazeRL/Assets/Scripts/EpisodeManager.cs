using System.Collections;
using UnityEngine;

public class EpisodeManager : MonoBehaviour
{
    [Header("Scene References")]
    public MazeGenerator mazeGenerator;
    public Transform player;
    public Transform goal;

    [Header("Episode Settings")]
    public int maxSteps = 500;

    [Header("Arena Seed Settings")]
    [SerializeField, Min(0)] private int arenaId = 0;
    [SerializeField] private int baseSeed = 1000;

    [Header("Episode Debug State")]
    [SerializeField] private int episodeIndex = 0;
    [SerializeField] private int currentSeed;

    private int stepCount = 0;
    private bool isResetting = false;

    private void Start()
    {
        episodeIndex = 0;
        GenerateCurrentEpisode();
        PlacePlayerAndGoal();
    }
    private void PlacePlayerAndGoal()
    {
        CharacterController controller =
            player.GetComponent<CharacterController>();

        if (controller != null)
            controller.enabled = false;

        player.position =
            mazeGenerator.GetCellWorldPosition(0, 0, 1f);

        player.rotation = mazeGenerator.transform.rotation;
        player.GetComponent<PlayerController>().ResetMotion();
        player.GetComponentInChildren<MouseLook>().ResetLook();

        if (controller != null)
            controller.enabled = true;

        goal.position = mazeGenerator.GetCellWorldPosition(
            mazeGenerator.width - 1,
            mazeGenerator.height - 1,
            0.25f
        );
    }
    public void RegisterStep()
    {
        if (isResetting)
            return;

        stepCount++;

        if (stepCount >= maxSteps)
        {
            Debug.Log($"[Arena {arenaId}] Goal reached in episode {episodeIndex}. Resetting.",this);
            StartCoroutine(ResetEpisode());
        }
    }

    // Call this when the player reaches the goal.
    public void GoalReached()
    {
        if (isResetting)
            return;

        Debug.Log($"[Arena {arenaId}] Goal reached in episode {episodeIndex}. Resetting.",this);
        StartCoroutine(ResetEpisode());
    }

    private IEnumerator ResetEpisode()
    {
        isResetting = true;

        // 1. Remove the old maze objects.
        mazeGenerator.ClearMaze();

        // Destroy() happens at the end of the frame.
        yield return null;

        episodeIndex++;
        GenerateCurrentEpisode();

        PlacePlayerAndGoal();

        // 3. Reset episode counters.
        stepCount = 0;
        isResetting = false;

        Debug.Log("NEW EPISODE STARTED");
    }
    private int CalculateEpisodeSeed()
    {
        unchecked
        {
            uint hash = 2166136261u;

            hash = (hash ^ (uint)baseSeed) * 16777619u;
            hash = (hash ^ (uint)arenaId) * 16777619u;
            hash = (hash ^ (uint)episodeIndex) * 16777619u;

            return (int)(hash & 0x7FFFFFFFu);
        }
    }

    private void GenerateCurrentEpisode()
    {
        currentSeed = CalculateEpisodeSeed();
        mazeGenerator.seed = currentSeed;
        mazeGenerator.GenerateMaze();

        Debug.Log(
            $"[Arena {arenaId}] Generated episode {episodeIndex} " +
            $"with seed {currentSeed}.",
            this
        );
    }
}
