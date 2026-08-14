class StoryError(Exception):
    """Base class for deterministic Story runtime errors."""


class StoryConfigurationError(StoryError):
    """Raised when Story Canon or a StoryDefinition is invalid."""


class StoryStateValidationError(StoryError):
    """Raised when a serialized or constructed StoryState is invalid."""


class UnknownStoryError(StoryError):
    pass


class UnknownTransitionError(StoryError):
    pass


class IllegalStoryTransitionError(StoryError):
    pass
