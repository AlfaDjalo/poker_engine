"""
poker_engine/graph/graph_export.py

export_graph_yaml(graph, path): dump a built GameGraph to a readable
YAML file -- nodes, their config, and every outgoing transition with
its condition, in the same order build_standard_graph() laid them
down.

This is a DERIVED artifact, not a source of truth. Nothing reads this
file back in; the graph is always (re)built from a variant's
GameDefinition (via build_standard_graph() or a custom {name}_graph.py
-- see graph_loader.py). Its only purpose is documentation/debugging:
letting a human see the whole flow of a hand -- every node and every
transition condition -- without reading Python.
"""

import yaml


def _condition_repr(condition) -> str:
    return repr(condition)


def graph_to_dict(graph) -> dict:
    data = {"entry_node": graph.entry_node, "nodes": {}}

    for node_id, node in graph.nodes.items():
        entry = {"kind": node.kind.name}

        if node.kind.name == "AUTO":
            entry["auto_type"] = node.auto_type
        else:
            entry["domain"] = node.domain.name
            entry["decider"] = node.decider

        if node.metadata:
            entry["metadata"] = dict(node.metadata)

        if node.config:
            cfg = {}
            for k, v in node.config.items():
                cfg[k] = v.__class__.__name__ if k == "rules" else v
            entry["config"] = cfg

        if node.card_moves:
            entry["card_moves"] = [
                f"{cm.source.zone.name}[{cm.source.index}] -> {cm.destination.zone.name}[{cm.destination.index}]"
                if cm.destination.zone.name == "BOARD_NODE"
                else f"{cm.source.zone.name} -> {cm.destination.zone.name} x{cm.count or len(cm.card_ids or [])}"
                for cm in node.card_moves
            ]

        outgoing = graph.outgoing(node_id)
        if outgoing:
            entry["transitions"] = [
                {"to": t.to_node, "when": _condition_repr(t.condition)} for t in outgoing
            ]
        else:
            entry["terminal"] = True

        data["nodes"][node_id] = entry

    return data


def export_graph_yaml(graph, path: str) -> None:
    data = graph_to_dict(graph)
    with open(path, "w") as f:
        f.write(
            "# AUTO-GENERATED -- derived from the GameGraph built by "
            "build_standard_graph()/load_game_graph().\n"
            "# This is a debugging/documentation export, not a source "
            "file: nothing reads it back in.\n"
            "# The actual source of truth is the variant's own "
            "{name}.yaml plus poker_engine/graph/standard_graph.py.\n\n"
        )
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False, width=100)