using System;
using System.Collections.Generic;
using UnityEngine;

public class MazeGenerator : MonoBehaviour
{
    [SerializeField] private Material floorMaterial;
    [SerializeField] private Material wallMaterial;
    [SerializeField] private Transform mazeRoot;
    public int width = 10;
    public int height = 10;
    public float cellSize = 2f;
    public float wallHeight = 2.5f;
    public int seed = 42;

    private class Cell
    {
        public bool visited;
        public bool[] walls = { true, true, true, true };
    }

    private Cell[,] cells;

    public void GenerateMaze()
    {
        cells = new Cell[width, height];

        for (int x = 0; x < width; x++)
        {
            for (int z = 0; z < height; z++)
            {
                cells[x, z] = new Cell();
            }
        }

        System.Random random = new System.Random(seed);
        Stack<Vector2Int> stack = new Stack<Vector2Int>();

        Vector2Int current = Vector2Int.zero;
        cells[0, 0].visited = true;
        stack.Push(current);

        Vector2Int[] dirs =
        {
            new Vector2Int(0, 1),
            new Vector2Int(1, 0),
            new Vector2Int(0, -1),
            new Vector2Int(-1, 0)
        };

        while (stack.Count > 0)
        {
            current = stack.Peek();
            List<int> available = new List<int>();

            for (int i = 0; i < 4; i++)
            {
                Vector2Int next = current + dirs[i];

                if (next.x >= 0 && next.x < width &&
                    next.y >= 0 && next.y < height &&
                    !cells[next.x, next.y].visited)
                {
                    available.Add(i);
                }
            }

            if (available.Count == 0)
            {
                stack.Pop();
                continue;
            }

            int dir = available[random.Next(available.Count)];
            Vector2Int neighbour = current + dirs[dir];

            cells[current.x, current.y].walls[dir] = false;
            cells[neighbour.x, neighbour.y].walls[(dir + 2) % 4] = false;

            cells[neighbour.x, neighbour.y].visited = true;
            stack.Push(neighbour);
        }

        BuildMaze();
    }

    void BuildMaze()
    {
        for (int x = 0; x < width; x++)
        {
            for (int z = 0; z < height; z++)
            {
                Vector3 center = new Vector3(x * cellSize, 0, z * cellSize);

                CreateFloor(center);

                if (cells[x, z].walls[0])
                {
                    CreateWall(
                        center + new Vector3(0, wallHeight / 2, cellSize / 2),
                        new Vector3(cellSize, wallHeight, 0.1f)
                    );
                }

                if (cells[x, z].walls[3])
                {
                    CreateWall(
                        center + new Vector3(-cellSize / 2, wallHeight / 2, 0),
                        new Vector3(0.1f, wallHeight, cellSize)
                    );
                }

                if (x == width - 1 && cells[x, z].walls[1])
                {
                    CreateWall(
                        center + new Vector3(cellSize / 2, wallHeight / 2, 0),
                        new Vector3(0.1f, wallHeight, cellSize)
                    );
                }

                if (z == 0 && cells[x, z].walls[2])
                {
                    CreateWall(
                        center + new Vector3(0, wallHeight / 2, -cellSize / 2),
                        new Vector3(cellSize, wallHeight, 0.1f)
                    );
                }
            }
        }
    }

    void CreateFloor(Vector3 position)
    {
        GameObject floor = GameObject.CreatePrimitive(PrimitiveType.Cube);

        floor.transform.SetParent(mazeRoot, false);
        floor.transform.localPosition = position + Vector3.down * 0.05f;
        floor.transform.localScale = new Vector3(cellSize, 0.1f, cellSize);

        floor.GetComponent<Renderer>().material = floorMaterial;
    }

    void CreateWall(Vector3 position, Vector3 scale)
    {
        GameObject wall = GameObject.CreatePrimitive(PrimitiveType.Cube);

        wall.transform.SetParent(mazeRoot, false);
        wall.transform.localPosition = position;
        wall.transform.localScale = scale;

        wall.GetComponent<Renderer>().material = wallMaterial;
    }
    public Vector3 GetCellWorldPosition(int x, int z, float heightOffset)
    {
        Vector3 localPosition =
            new Vector3(x * cellSize, heightOffset, z * cellSize);

        return mazeRoot.TransformPoint(localPosition);
    }
    public void ClearMaze()
    {
        foreach (Transform child in mazeRoot)
        {
            child.gameObject.SetActive(false);
            Destroy(child.gameObject);
        }
    }
}
