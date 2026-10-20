"""Same-named Swift types nested in different parents must keep separate nodes.

Swift type ids were `{stem}_{name}` for nested types too, so two `Codable`
structs in one file that each declare `enum CodingKeys` collapsed onto one
`CodingKeys` node, contained by both structs and carrying both enums' cases
(Python had the same shape, #4220). A bare reference to a nested type from
inside its enclosing type must still reach that nested type, including a
reference written before the declaration, which Swift allows.
"""
from graphify.extract import extract


CODABLE = (
    "struct Person: Codable {\n"
    "    let name: String\n"
    "    enum CodingKeys: String, CodingKey { case name = \"full_name\" }\n"
    "}\n"
    "struct Place: Codable {\n"
    "    let title: String\n"
    "    enum CodingKeys: String, CodingKey { case title = \"place_title\" }\n"
    "}\n"
)

# Person refers to its Key before declaring it; Place declares it first.
SCOPED_REFS = (
    "struct Person {\n"
    "    func label(for key: Key) -> String { \"\" }\n"
    "    enum Key { case name }\n"
    "}\n"
    "struct Place {\n"
    "    enum Key { case title }\n"
    "    func label(for key: Key) -> String { \"\" }\n"
    "}\n"
)


def _extract(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    paths = sorted(root / name for name in files)
    return extract(paths, root=root, cache_root=root / "cache", parallel=False)


def _labels(result):
    return {node["id"]: node["label"] for node in result["nodes"]}


def _owner(result, nid):
    """Label of the node that owns nid: the type (or file) that `contains` it,
    or the type it is a `method` of."""
    labels = _labels(result)
    owners = [labels[e["source"]] for e in result["edges"]
              if e["relation"] in ("contains", "method") and e["target"] == nid]
    assert len(owners) == 1, owners
    return owners[0]


def test_same_named_nested_types_keep_separate_nodes(tmp_path):
    result = _extract(tmp_path, {"Models.swift": CODABLE})
    keys = [n for n in result["nodes"] if n["label"] == "CodingKeys"]
    assert len(keys) == 2
    assert len({n["id"] for n in keys}) == 2
    labels = _labels(result)
    cases = {
        _owner(result, n["id"]): sorted(
            labels[e["target"]] for e in result["edges"]
            if e["relation"] == "case_of" and e["source"] == n["id"])
        for n in keys
    }
    assert cases == {"Person": ["name"], "Place": ["title"]}


def test_top_level_type_ids_are_unchanged(tmp_path):
    result = _extract(tmp_path, {"Models.swift": CODABLE})
    ids = {n["label"]: n["id"] for n in result["nodes"] if n["label"] in ("Person", "Place")}
    assert ids == {"Person": "models_person", "Place": "models_place"}


def test_bare_reference_reaches_the_enclosing_types_nested_type(tmp_path):
    result = _extract(tmp_path, {"Models.swift": SCOPED_REFS})
    labels = _labels(result)
    keys = {_owner(result, n["id"]): n["id"] for n in result["nodes"] if n["label"] == "Key"}
    assert set(keys) == {"Person", "Place"}
    # Each struct's method references its own Key, whichever comes first in source.
    for owner, key_nid in keys.items():
        referrers = {e["source"] for e in result["edges"]
                     if e["relation"] == "references" and e["target"] == key_nid}
        assert referrers, f"{owner}.Key has no references"
        assert {_owner(result, s) for s in referrers} == {owner}
    # No sourceless `Key` stub was minted for either reference.
    assert not any(labels[n["id"]] == "Key" and not n.get("source_file")
                   for n in result["nodes"])


def test_extension_in_the_same_file_reaches_the_types_nested_type(tmp_path):
    result = _extract(tmp_path, {"Person.swift": (
        "struct Person {\n"
        "    enum Key { case name }\n"
        "}\n"
        "extension Person {\n"
        "    func label(for key: Key) -> String { \"\" }\n"
        "}\n"
    )})
    key = next(n["id"] for n in result["nodes"] if n["label"] == "Key")
    assert any(e["relation"] == "references" and e["target"] == key
               for e in result["edges"])


def test_nested_type_and_same_named_member_stay_two_nodes(tmp_path):
    """`struct Crime` and `func crime()` in one type case-fold to one plain id.
    The member keeps it; the nested type is salted, so the factory's call to
    its own nested type is an edge between two nodes, not a self-loop."""
    result = _extract(tmp_path, {"Samples.swift": (
        "enum Samples {\n"
        "    struct Crime { let level: Int }\n"
        "    static func crime() -> Crime { Crime(level: 1) }\n"
        "    struct Header { let title: String }\n"
        "    var header: Header { Header(title: \"\") }\n"
        "}\n"
    )})
    ids = {n["label"]: n["id"] for n in result["nodes"]}
    assert ids[".crime()"] == "samples_samples_crime"
    assert ids[".header"] == "samples_samples_header"
    assert ids["Crime"].startswith("samples_samples_crime_")
    assert ids["Header"].startswith("samples_samples_header_")
    assert ("calls", ids[".crime()"], ids["Crime"]) in {
        (e["relation"], e["source"], e["target"]) for e in result["edges"]}
    assert not [e for e in result["edges"] if e["source"] == e["target"]]


def test_nested_type_identity_is_stable_across_cache_and_checkout(tmp_path):
    first = _extract(tmp_path / "first", {"Models.swift": CODABLE})
    warm = _extract(tmp_path / "first", {"Models.swift": CODABLE})
    relocated = _extract(tmp_path / "second", {"Models.swift": CODABLE})
    assert first["nodes"] == warm["nodes"] == relocated["nodes"]
    assert first["edges"] == warm["edges"] == relocated["edges"]
