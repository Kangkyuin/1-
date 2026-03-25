using UnityEngine;

[RequireComponent(typeof(CharacterController))]
public class ThirdPersonCharacterController : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private Transform cameraPivot;
    [SerializeField] private Animator animator;

    [Header("Move")]
    [SerializeField] private float moveSpeed = 4.5f;
    [SerializeField] private float runMultiplier = 1.6f;
    [SerializeField] private float rotationSpeed = 12f;
    [SerializeField] private float acceleration = 18f;
    [SerializeField] private float gravity = -20f;
    [SerializeField] private float jumpHeight = 1.2f;

    [Header("Animator Params")]
    [SerializeField] private string speedParam = "Speed";
    [SerializeField] private string moveXParam = "MoveX";
    [SerializeField] private string moveYParam = "MoveY";
    [SerializeField] private string groundedParam = "IsGrounded";

    [Header("Animation Smoothing")]
    [SerializeField] private float animDampTime = 0.08f;

    private CharacterController _controller;
    private Vector3 _currentHorizontalVelocity;
    private float _verticalVelocity;

    private void Awake()
    {
        _controller = GetComponent<CharacterController>();

        if (animator == null)
        {
            animator = GetComponentInChildren<Animator>();
        }

        if (cameraPivot == null && Camera.main != null)
        {
            cameraPivot = Camera.main.transform;
        }
    }

    private void Update()
    {
        HandleMovement();
        UpdateAnimator();
    }

    private void HandleMovement()
    {
        float inputX = Input.GetAxisRaw("Horizontal");
        float inputY = Input.GetAxisRaw("Vertical");
        Vector2 input = new Vector2(inputX, inputY);
        input = Vector2.ClampMagnitude(input, 1f);

        bool isRunning = Input.GetKey(KeyCode.LeftShift);
        float targetSpeed = moveSpeed * (isRunning ? runMultiplier : 1f);

        Vector3 worldMove = GetCameraRelativeMove(input);
        Vector3 targetHorizontalVelocity = worldMove * targetSpeed;
        _currentHorizontalVelocity = Vector3.MoveTowards(
            _currentHorizontalVelocity,
            targetHorizontalVelocity,
            acceleration * Time.deltaTime
        );

        if (_controller.isGrounded)
        {
            if (_verticalVelocity < 0f)
            {
                _verticalVelocity = -2f;
            }

            if (Input.GetButtonDown("Jump"))
            {
                _verticalVelocity = Mathf.Sqrt(jumpHeight * -2f * gravity);
            }
        }

        _verticalVelocity += gravity * Time.deltaTime;

        Vector3 finalVelocity = _currentHorizontalVelocity;
        finalVelocity.y = _verticalVelocity;

        _controller.Move(finalVelocity * Time.deltaTime);
        HandleRotation(worldMove);
    }

    private Vector3 GetCameraRelativeMove(Vector2 input)
    {
        if (cameraPivot == null)
        {
            return new Vector3(input.x, 0f, input.y);
        }

        Vector3 forward = cameraPivot.forward;
        Vector3 right = cameraPivot.right;
        forward.y = 0f;
        right.y = 0f;
        forward.Normalize();
        right.Normalize();

        return (forward * input.y + right * input.x).normalized;
    }

    private void HandleRotation(Vector3 desiredMoveDirection)
    {
        if (desiredMoveDirection.sqrMagnitude <= 0.0001f)
        {
            return;
        }

        Quaternion targetRotation = Quaternion.LookRotation(desiredMoveDirection, Vector3.up);
        transform.rotation = Quaternion.Slerp(
            transform.rotation,
            targetRotation,
            rotationSpeed * Time.deltaTime
        );
    }

    private void UpdateAnimator()
    {
        if (animator == null)
        {
            return;
        }

        Vector3 horizontalVelocity = _currentHorizontalVelocity;
        horizontalVelocity.y = 0f;

        float speed01 = Mathf.InverseLerp(0f, moveSpeed * runMultiplier, horizontalVelocity.magnitude);

        Vector3 localVelocity = transform.InverseTransformDirection(horizontalVelocity);
        float moveX = localVelocity.x / (moveSpeed * runMultiplier);
        float moveY = localVelocity.z / (moveSpeed * runMultiplier);

        animator.SetFloat(speedParam, speed01, animDampTime, Time.deltaTime);
        animator.SetFloat(moveXParam, moveX, animDampTime, Time.deltaTime);
        animator.SetFloat(moveYParam, moveY, animDampTime, Time.deltaTime);
        animator.SetBool(groundedParam, _controller.isGrounded);
    }
}
