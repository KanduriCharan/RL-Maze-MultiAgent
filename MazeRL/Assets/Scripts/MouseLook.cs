using UnityEngine;
using UnityEngine.InputSystem;

public class MouseLook : MonoBehaviour
{
    public Transform playerBody;
    public float mouseSensitivity = 0.15f;

    private bool externalControl;

    public void SetExternalControl(bool enabled)
    {
        externalControl = enabled;
    }

    void Start()
    {
        ResetLook();
        if (externalControl)
            return;

        Cursor.lockState = CursorLockMode.Locked;
        Cursor.visible = false;
    }

    void Update()
    {
        if (externalControl || Mouse.current == null)
            return;

        Vector2 mouseDelta = Mouse.current.delta.ReadValue() * mouseSensitivity;

        ApplyLook(mouseDelta.x);

        if (Keyboard.current != null &&
            Keyboard.current.escapeKey.wasPressedThisFrame)
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }
    }
    // Keep the camera level at its existing head-height offset; turn only the body.
    public void ApplyLook(float yawDegrees)
    {
        transform.localRotation = Quaternion.identity;
        playerBody.Rotate(Vector3.up * yawDegrees);
    }

    public void ResetLook()
    {
        transform.localRotation = Quaternion.identity;
    }
}
