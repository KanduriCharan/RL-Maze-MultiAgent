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
    public void Start()
    {
        mazeGenerator.GenerateMaze();
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
        mazeGenerator.GenerateMaze();

        PlacePlayerAndGoal();

        // 3. Reset episode counters.
        stepCount = 0;
        isResetting = false;

        Debug.Log("NEW EPISODE STARTED");
    }
}
