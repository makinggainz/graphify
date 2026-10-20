# graphify: unofficial Swift-fixes fork

This is an unofficial fork of [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) at v0.9.92, with two fixes for Swift code. It is not affiliated with or endorsed by Graphify Labs. When an official release fixes the two issues below, switch back to the official package.

## What changed

- **Nested types keep separate nodes** ([#4575](https://github.com/Graphify-Labs/graphify/issues/4575)).
  - Before: same-named nested types in one file, such as the `CodingKeys` enum in every `Codable` struct, collapsed into a single node.
  - Now: a nested type's id includes its enclosing type's.
  - A nested type that would clash with a same-named member (`struct Crime` next to `func crime()`) gets a short hash suffix.
  - A bare type name inside a type resolves to that type's own nested type, even when the declaration comes later in the file.
- **An extension of an outside type is not its definition** ([#4574](https://github.com/Graphify-Labs/graphify/issues/4574)).
  - Before: `extension String { … }` in one file became the target of every `String` reference in the project.
  - Now: those references stay unresolved stubs, as `Int` and `Bool` references already do.
  - A type declared next to its own extension now also absorbs its extensions in other files.

Both fixes come with regression tests: `tests/test_swift_nested_type_identity.py` and `tests/test_swift_extension_stub_rewire.py`. Both raise the AST cache schema to 18, so your first build after installing re-parses every file.

These files differ from upstream:
- `graphify/extractors/engine.py`, `graphify/extract.py`, `graphify/cache.py`, `graphify/watch.py` and `graphify/cli.py`, each marked on its first line;
- `pyproject.toml`, for the version `0.9.92+swiftfix.1`;
- `README.md`, for the notice at the top;
- this file.

## Install

```sh
uv tool install "graphifyy[sql] @ git+https://github.com/makinggainz/graphify@swift-fixes"
graphify install
```

`graphify --version` should print `graphify 0.9.92+swiftfix.1`. `[sql]` adds the SQL parser; leave it out if your project has no `.sql` files. If you already have graphify installed, add `--force` to the first command.

## Going back to the official package

```sh
uv tool install --force graphifyy
```

An official release that doesn't yet include these fixes brings the two bugs back.

## License

Apache-2.0, as upstream: see `LICENSE` and `NOTICE`. The changes in this fork are under the same license.
