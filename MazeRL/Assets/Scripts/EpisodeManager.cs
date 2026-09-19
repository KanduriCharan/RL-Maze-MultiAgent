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

    private int stepCount = 0;
    private bool isResetting = false;

    // Call this once for every W/A/S/D action.
    public void RegisterStep()
    {
        if (isResetting)
            return;

        stepCount++;

        if (stepCount >= maxSteps)
        {
            Debug.Log("MAX STEPS REACHED - RESETTING EPISODE");
            StartCoroutine(ResetEpisode());
        }
    }

    // Call this when the player reaches the goal.
    public void GoalReached()
    {
        if (isResetting)
            return;

        Debug.Log("GOAL REACHED - RESETTING EPISODE");
        StartCoroutine(ResetEpisode());
    }

    private IEnumerator ResetEpisode()
    {
        isResetting = true;

        // 1. Remove the old maze objects.
        foreach (Transform child in mazeGenerator.transform)
        {
            Destroy(child.gameObject);
        }

        // Destroy() happens at the end of the frame.
        yield return null;

        // 2. Use a new random seed.
        mazeGenerator.seed = Random.Range(0, int.MaxValue);

        // 3. Generate a new maze using the existing MazeGenerator.cs.
        // GenerateMaze() is private in your current file, so SendMessage is
        // used here without requiring you to edit MazeGenerator.cs yet.
        mazeGenerator.SendMessage("GenerateMaze", SendMessageOptions.DontRequireReceiver);

        // 4. Reset the player to cell (0, 0).
        CharacterController controller = player.GetComponent<CharacterController>();

        if (controller != null)
            controller.enabled = false;

        player.position = new Vector3(0f, 1f, 0f);

        if (controller != null)
            controller.enabled = true;

        // 5. Put the goal in the last maze cell.
        float goalX = (mazeGenerator.width - 1) * mazeGenerator.cellSize;
        float goalZ = (mazeGenerator.height - 1) * mazeGenerator.cellSize;
        goal.position = new Vector3(goalX, 0.25f, goalZ);

        // 6. Reset episode counters.
        stepCount = 0;
        isResetting = false;

        Debug.Log("NEW EPISODE STARTED");
    }
}
