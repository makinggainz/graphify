"""An extension of a type the corpus doesn't define is not that type's definition.

tree-sitter-swift reuses `class_declaration` for `extension String { ... }`, so
the extension mints a `String` node with a source file. _merge_swift_extensions
rightly leaves extensions of out-of-corpus types alone, but
_rewire_unique_stub_nodes then took that node for the one real `String` and
pointed every bare `String` reference in the corpus at the extension. In an
app with one `private extension String`, that node collected every `String`
in the codebase and became the graph's top cross-community bridge.

A type declared in the same file as its own extension shares the extension's
node id and must still resolve as the real definition, and must absorb the
type's extensions in other files.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract


HELPERS = (
    "private extension String {\n"
    "    var trimmed: String { trimmingCharacters(in: .whitespaces) }\n"
    "}\n"
)
MODELS = "struct Person {\n    let name: String\n}\n"


def _extract(root: Path, files: dict[str, str]) -> dict:
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    paths = sorted(root / name for name in files)
    return extract(paths, root=root, cache_root=root / "cache", parallel=False)


def _reference_target(result: dict, source_label: str, target_label: str) -> dict:
    nodes = {n["id"]: n for n in result["nodes"]}
    targets = [nodes[e["target"]] for e in result["edges"]
               if e["relation"] == "references"
               and nodes[e["source"]]["label"] == source_label
               and nodes[e["target"]]["label"] == target_label]
    assert len(targets) == 1, targets
    return targets[0]


def test_extension_of_an_outside_type_does_not_capture_its_references(tmp_path):
    result = _extract(tmp_path, {"Helpers.swift": HELPERS, "Models.swift": MODELS})
    target = _reference_target(result, "Person", "String")
    assert target.get("source_file") != "Helpers.swift"
    # The extension itself is kept, with its member.
    ext = next(n for n in result["nodes"]
               if n["label"] == "String" and n.get("source_file") == "Helpers.swift")
    assert any(e["source"] == ext["id"] and e["relation"] == "method"
               for e in result["edges"])


def test_type_declared_beside_its_own_extension_still_resolves(tmp_path):
    result = _extract(tmp_path, {
        "Money.swift": (
            "struct Money {\n    let cents: Int\n}\n"
            "extension Money {\n    static var zero: Money { Money(cents: 0) }\n}\n"
        ),
        "Wallet.swift": "struct Wallet {\n    let balance: Money\n}\n",
    })
    target = _reference_target(result, "Wallet", "Money")
    assert target["id"] == "money_money"
    assert target.get("source_file") == "Money.swift"


def test_type_with_a_same_file_extension_absorbs_other_files_extensions(tmp_path):
    """The same-file extension shares the declaration's id, so the merge used to
    count that node as an extension, find no canonical `Money`, and leave a
    second `Money` node behind; the reference then had two candidates and
    stayed on a sourceless stub."""
    result = _extract(tmp_path, {
        "Money.swift": (
            "struct Money {\n    let cents: Int\n}\n"
            "extension Money {\n    static var zero: Money { Money(cents: 0) }\n}\n"
        ),
        "MoneyFormat.swift": "extension Money {\n    var text: String { \"\" }\n}\n",
        "Wallet.swift": "struct Wallet {\n    let balance: Money\n}\n",
    })
    sourced = [n["id"] for n in result["nodes"] if n["label"] == "Money" and n.get("source_file")]
    assert sourced == ["money_money"]
    assert _reference_target(result, "Wallet", "Money")["id"] == "money_money"


def test_cross_file_extension_of_a_corpus_type_still_merges(tmp_path):
    result = _extract(tmp_path, {
        "Money.swift": "struct Money {\n    let cents: Int\n}\n",
        "MoneyFormat.swift": "extension Money {\n    var text: String { \"\" }\n}\n",
        "Wallet.swift": "struct Wallet {\n    let balance: Money\n}\n",
    })
    assert [n["id"] for n in result["nodes"] if n["label"] == "Money"] == ["money_money"]
    assert _reference_target(result, "Wallet", "Money")["id"] == "money_money"


def test_outside_type_extension_survives_an_incremental_rebuild(tmp_path):
    """On `graphify update` the unchanged extension file arrives only as
    resolution-context nodes; it must still not absorb the reference."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "Helpers.swift").write_text(HELPERS, encoding="utf-8")
    models = corpus / "Models.swift"
    models.write_text(MODELS, encoding="utf-8")
    graph_path = corpus / "graphify-out" / "graph.json"

    def string_targets() -> set[str]:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in data["nodes"]}
        return {
            nodes[e["target"]].get("source_file") or ""
            for e in data["links"]
            if e["relation"] == "references"
            and nodes[e["source"]]["label"] == "Person"
            and nodes[e["target"]]["label"] == "String"
        }

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    assert string_targets() == {""}

    models.write_text(MODELS + "struct Pet {\n    let name: String\n}\n", encoding="utf-8")
    assert _rebuild_code(corpus, changed_paths=[models], no_cluster=True,
                         acquire_lock=False) is True
    assert string_targets() == {""}
