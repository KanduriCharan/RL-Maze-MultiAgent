using UnityEngine;

public class GoalDetector : MonoBehaviour
{
    [SerializeField]
    private EpisodeManager episodeManager;

    private void Start()
    {
        if (episodeManager == null)
        {
            Debug.LogError(
                "Assign this goal's EpisodeManager in the Inspector.",
                this
            );
        }
    }

    private void OnTriggerEnter(Collider other)
    {
        if (episodeManager == null)
            return;

        PlayerController player =
            other.GetComponentInParent<PlayerController>();

        if (player == null)
            return;

        if (player.transform != episodeManager.player)
            return;

        episodeManager.GoalReached();
    }
}