#!/usr/bin/env python3
"""A file with intentional lint issues for testing."""


# TODO: fix this later
def greet(name: str) -> str:
    """Return a greeting with tab indentation."""
    return f"Hello, {name}!"


# This line is intentionally way too long for lint testing purposes to trigger the L002 rule which checks for lines exceeding 120 characters

if __name__ == "__main__":
    print(greet("World"))
