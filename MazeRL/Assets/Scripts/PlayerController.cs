using UnityEngine;
using UnityEngine.InputSystem;

[RequireComponent(typeof(CharacterController))]
public class PlayerController : MonoBehaviour
{
    public float moveSpeed = 4f;
    public float gravity = -9.81f;

    private CharacterController controller;
    private float verticalVelocity;
    private bool externalControl;

    public void SetExternalControl(bool enabled)
    {
        externalControl = enabled;
        ResetMotion();
    }

    void Awake()
    {
        controller = GetComponent<CharacterController>();
    }

    void Update()
    {
        if (externalControl || Keyboard.current == null)
            return;

        Vector2 input = Vector2.zero;

        if (Keyboard.current.wKey.isPressed) input.y += 1f;
        if (Keyboard.current.sKey.isPressed) input.y -= 1f;
        if (Keyboard.current.dKey.isPressed) input.x += 1f;
        if (Keyboard.current.aKey.isPressed) input.x -= 1f;

        Move(input, Time.deltaTime);
    }

    // Discrete movement: 0=W, 1=A (strafe left), 2=S, 3=D (strafe right).
    public void ApplyAgentAction(int action, float deltaTime)
    {
        if (!externalControl)
            return;

        Vector2 input;
        switch (action)
        {
            case 0: input = Vector2.up; break;
            case 1: input = Vector2.left; break;
            case 2: input = Vector2.down; break;
            case 3: input = Vector2.right; break;
            default: throw new System.ArgumentOutOfRangeException(nameof(action));
        }

        Move(input, deltaTime);
    }

    private void Move(Vector2 input, float deltaTime)
    {
        Vector3 move =
            transform.right * input.x +
            transform.forward * input.y;

        if (move.sqrMagnitude > 1f)
            move.Normalize();

        if (controller.isGrounded && verticalVelocity < 0f)
            verticalVelocity = -2f;

        move *= moveSpeed;
        verticalVelocity += gravity * deltaTime;
        move.y = verticalVelocity;

        controller.Move(move * deltaTime);
    }
    public void ResetMotion()
    {
        verticalVelocity = 0f;
    }
    
}
