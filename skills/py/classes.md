# Class Traps

## Shared state
- `class A: items = []` — one list shared by every instance; `a.items.append(x)` shows up on `b.items`. Mutable state belongs in `__init__`. Reading `self.items` finds the class attribute until the first instance assignment shadows it — which is why the bug appears only on mutation, not assignment.
- Dataclasses raise at class creation for `field: list = []` — but only for list/dict/set. A mutable default of any OTHER type (custom class instance) passes silently and is shared. Always `field(default_factory=...)` for anything mutable.

## Equality and hashing
- Defining `__eq__` sets `__hash__ = None` — instances become unhashable, breaking sets and dict keys. Define `__hash__` over the same fields `__eq__` compares, or the object misbehaves in hash containers.
- Same rule inside `@dataclass`: `eq=True` (the default) kills hashing unless `frozen=True` (auto-hash) or explicit `unsafe_hash=True`. A dataclass that stops working in a set after adding fields usually lost frozen.

## Construction and inheritance
- `__init__` initializes an EXISTING instance and must return None; `__new__` creates the instance. Subclassing immutables (tuple, str, int) requires overriding `__new__` — by `__init__` time the value is already fixed.
- `super()` follows the MRO of the RUNTIME class, not "my parent". In multiple inheritance, every class in the diamond must call `super().__init__(**kwargs)` and pass through unknown kwargs, or the chain silently stops at the first non-cooperative class.
- `type(x) == T` rejects subclasses; `isinstance(x, T)` is the default. The exception: when subclass substitution is exactly the bug you are guarding against (e.g., bool passing an int check).

## Attribute machinery
- `hasattr`/`getattr(x, 'attr', default)` swallow only AttributeError — but a BUG inside a `@property` getter that raises AttributeError (a typo'd self-attribute) looks identical to "attribute missing". Symptom: property "disappears". Debug by calling the property directly.
- `@property` setter requires the getter defined first under the same name (`@x.setter` needs `@property def x` above it) — wrong order is a NameError at class-body execution.
- `__slots__` removes `__dict__`: no ad-hoc attributes, and `functools.cached_property` breaks (it stores into `__dict__`). Every class in the hierarchy must declare `__slots__` or instances get a dict anyway and the memory saving silently vanishes.
- `__x` name-mangles to `_ClassName__x` — its purpose is avoiding subclass name collisions, not privacy. It also breaks `getattr(self, '__x')` and pickling of the raw name; prefer single underscore unless collision is the actual concern.
- `__init_subclass__` and `__set_name__` (Python >=3.6) cover most registration/validation use cases that used to require a metaclass — reach for a metaclass only when you must change class CREATION itself.
