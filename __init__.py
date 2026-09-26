# Hermes loads this file as a package module; pytest may collect it standalone.
if __package__:
    from .story_construction_plugin import register
else:
    from story_construction_plugin import register

__all__ = ["register"]
