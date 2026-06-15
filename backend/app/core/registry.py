"""Generic type-safe registry — foundation for plugins, agents, integrations."""

from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """
    Thread-safe-ish registry for pluggable components.
    Use for agents, integrations, features, API modules.

    Example:
        integrations = Registry[BaseIntegration]("integrations")
        integrations.register("github", GitHubIntegration())

        @integrations.plugin("bitbucket")
        class BitbucketIntegration(BaseIntegration):
            ...
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._items: dict[str, T] = {}
        self._metadata: dict[str, dict] = {}

    def register(self, key: str, item: T, **metadata) -> None:
        if key in self._items:
            raise ValueError(f"[{self.name}] Already registered: {key}")
        self._items[key] = item
        self._metadata[key] = metadata

    def register_factory(self, key: str, factory: Callable[[], T], **metadata) -> None:
        self.register(key, factory(), **metadata)

    def get(self, key: str) -> T:
        if key not in self._items:
            raise KeyError(f"[{self.name}] Not found: {key}")
        return self._items[key]

    def get_optional(self, key: str) -> T | None:
        return self._items.get(key)

    def list_keys(self) -> list[str]:
        return list(self._items.keys())

    def list_items(self) -> list[T]:
        return list(self._items.values())

    def list_with_metadata(self) -> list[dict]:
        return [
            {"key": key, "metadata": self._metadata.get(key, {}), "registered": True}
            for key in self._items
        ]

    def plugin(self, key: str, **metadata):
        """Decorator to register a class instance."""

        def decorator(cls: type[T]) -> type[T]:
            self.register(key, cls(), **metadata)
            return cls

        return decorator

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)
