using UnityEngine;

public class GoalDetector : MonoBehaviour
{
    private EpisodeManager episodeManager;
    void Start()
    {
        episodeManager = FindAnyObjectByType<EpisodeManager>();

        if (episodeManager == null)
        {
            Debug.LogError("EpisodeManager not found in the scene.");
        }
    }
    private void OnTriggerEnter(Collider other)
    {
        // Temporary test: detect the Player by GameObject/root name.
        if (other.gameObject.name == "Player" || other.transform.root.name == "Player")
        {
            Debug.Log("GOAL REACHED");

        }
    }
}
