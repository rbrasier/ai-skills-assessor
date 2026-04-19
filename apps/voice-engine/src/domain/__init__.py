"""Domain layer: pure dataclasses, port interfaces, and orchestration services.

Nothing in this package may import from ``src.adapters``, third-party SDKs,
``fastapi``, or any other I/O dependency. It defines *what* the system needs;
adapters in ``src.adapters`` provide the *how*.
"""
