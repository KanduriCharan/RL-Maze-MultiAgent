using UnityEngine;

public class EpisodeManager : MonoBehaviour
{
    [Header("Scene References")]
    public MazeGenerator mazeGenerator;
    public Transform player;
    public Transform goal;

    [Header("Episode Settings")]
    [SerializeField, Min(0.02f)] private float timeLimitSeconds = 60f;
    [SerializeField] private float elapsedSeconds;
    [SerializeField] private string lastOutcome = "None";

    [Header("Arena Seed Settings")]
    [SerializeField, Min(0)] private int arenaId = 0;
    [SerializeField] private int baseSeed = 1000;

    [Header("Episode Debug State")]
    [SerializeField] private int episodeIndex = 0;
    [SerializeField] private int currentSeed;

    [Header("Wall Appearance")]
    [SerializeField] private Material[] wallMaterials;
    private int previousWallMaterialIndex = -1;

    private MazeAgent agent;
    private bool isResetting = false;
    private bool initialized;
    private bool advanceEpisodeOnBegin;

    private void Start()
    {
        if (!initialized)
            Initialize(arenaId, baseSeed);
    }
    public void Initialize(int id, int seed)
    {
        if (initialized)
            return;

        if (mazeGenerator == null || player == null || goal == null)
        {
            throw new System.InvalidOperationException(
                "Arena is missing its maze generator, player, or goal reference."
            );
        }

        agent = player.GetComponent<MazeAgent>();
        if (agent != null)
            agent.BindEpisodeManager(this);

        arenaId = id;
        baseSeed = seed;
        episodeIndex = 0;
        previousWallMaterialIndex = -1;

        GenerateCurrentEpisode();
        PlacePlayerAndGoal();

        elapsedSeconds = 0f;
        initialized = true;
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
    private void FixedUpdate()
    {
        if (!initialized || isResetting)
            return;

        elapsedSeconds += Time.fixedDeltaTime;
        if (elapsedSeconds + 0.00001f >= timeLimitSeconds)
            FinishEpisode(true);
    }

    public void GoalReached()
    {
        FinishEpisode(false);
    }

    private void FinishEpisode(bool timedOut)
    {
        if (!initialized || isResetting)
            return;

        isResetting = true;
        advanceEpisodeOnBegin = true;
        lastOutcome = timedOut ? "Timeout" : "Success";
        Debug.Log($"[Arena {arenaId}] Episode {episodeIndex}: {lastOutcome} " +
            $"after {elapsedSeconds:F2} simulated seconds.", this);

        // ML-Agents captures terminal observations before invoking OnEpisodeBegin.
        if (agent != null && agent.isActiveAndEnabled)
        {
            if (timedOut)
                agent.EpisodeInterrupted();
            else
                agent.EndEpisode();
        }
        else
        {
            BeginEpisode();
        }
    }

    public void BeginEpisode()
    {
        if (!initialized)
            return;

        isResetting = true;
        // Startup and Python env.reset() also invoke OnEpisodeBegin. Only a
        // completed goal/timeout should advance the deterministic maze sequence.
        if (advanceEpisodeOnBegin)
        {
            advanceEpisodeOnBegin = false;
            // ClearMaze disables old geometry immediately; deferred destruction is safe.
            mazeGenerator.ClearMaze();
            episodeIndex++;
            GenerateCurrentEpisode();
        }
        else
        {
            lastOutcome = "None";
        }
        PlacePlayerAndGoal();
        elapsedSeconds = 0f;
        isResetting = false;
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

    private Material SelectWallMaterial()
    {
        if (wallMaterials == null || wallMaterials.Length == 0)
            throw new System.InvalidOperationException("Assign wall materials on the EpisodeManager.");

        for (int i = 0; i < wallMaterials.Length; i++)
        {
            if (wallMaterials[i] == null)
                throw new System.InvalidOperationException($"Wall material at index {i} is missing.");
        }

        // Separate RNG: visual choices must not affect maze carving.
        int visualSeed = currentSeed ^ 0x5F3759DF;
        System.Random visualRandom = new System.Random(visualSeed);
        int count = wallMaterials.Length;
        int selectedIndex;

        if (count == 1)
        {
            selectedIndex = 0;
        }
        else if (previousWallMaterialIndex >= 0 && previousWallMaterialIndex < count)
        {
            selectedIndex = visualRandom.Next(count - 1);
            if (selectedIndex >= previousWallMaterialIndex)
                selectedIndex++;
        }
        else
        {
            selectedIndex = visualRandom.Next(count);
        }

        previousWallMaterialIndex = selectedIndex;
        return wallMaterials[selectedIndex];
    }

    private void GenerateCurrentEpisode()
    {
        currentSeed = CalculateEpisodeSeed();
        Material selectedMaterial = SelectWallMaterial();
        mazeGenerator.SetWallMaterial(selectedMaterial);
        mazeGenerator.seed = currentSeed;
        mazeGenerator.GenerateMaze();

        Debug.Log(
            $"[Arena {arenaId}] Generated episode {episodeIndex} " +
            $"with seed {currentSeed}, walls: {selectedMaterial.name}.",
            this
        );
    }
}
