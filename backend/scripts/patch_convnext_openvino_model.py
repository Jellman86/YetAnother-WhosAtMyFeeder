#!/usr/bin/env python3
"""Patch ConvNeXt ONNX graph for OpenVINO compatibility.

The current ConvNeXt export can include a Loop/Sequence subgraph that OpenVINO
cannot compile (`SequenceEmpty`, `SequenceInsert`, `ConcatFromSequence`).

This script replaces that Loop output with an equivalent constant tensor
(`indices_17`) derived from the classifier channel dimension, preserving ONNX
Runtime outputs while enabling OpenVINO compile on GPU/CPU.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Iterable

import numpy as np
import onnx
from onnx import AttributeProto, helper, numpy_helper


def _count_sequence_ops(model: onnx.ModelProto) -> int:
    count = 0

    def walk(graph: onnx.GraphProto) -> None:
        nonlocal count
        for node in graph.node:
            if node.op_type in ("SequenceEmpty", "SequenceInsert", "ConcatFromSequence"):
                count += 1
            for attr in node.attribute:
                if attr.type == AttributeProto.GRAPH:
                    walk(attr.g)
                elif attr.type == AttributeProto.GRAPHS:
                    for subgraph in attr.graphs:
                        walk(subgraph)

    walk(model.graph)
    return count


def _consumers_by_input(graph: onnx.GraphProto) -> dict[str, list[onnx.NodeProto]]:
    consumers: dict[str, list[onnx.NodeProto]] = {}
    for node in graph.node:
        for tensor_name in node.input:
            consumers.setdefault(tensor_name, []).append(node)
    return consumers


def _resolve_channel_dim(graph: onnx.GraphProto) -> int:
    initializers = {init.name: init for init in graph.initializer}

    if "head.fc.weight" in initializers:
        dims = tuple(int(d) for d in initializers["head.fc.weight"].dims)
        if len(dims) >= 2 and dims[1] > 0:
            return int(dims[1])

    for name, init in initializers.items():
        dims = tuple(int(d) for d in init.dims)
        if len(dims) != 2:
            continue
        if dims[0] == 10000 and dims[1] > 0:
            return int(dims[1])
        if name.endswith("head.weight") and dims[1] > 0:
            return int(dims[1])

    raise RuntimeError("Could not resolve ConvNeXt classifier channel dimension from initializers")


def _find_patch_nodes(graph: onnx.GraphProto) -> tuple[onnx.NodeProto, onnx.NodeProto | None, str]:
    consumers = _consumers_by_input(graph)
    producers = {}
    for node in graph.node:
        for output_name in node.output:
            producers[output_name] = node

    loop_candidate: onnx.NodeProto | None = None
    loop_target_output = ""
    for node in graph.node:
        if node.op_type != "Loop" or len(node.output) < 2:
            continue
        first_output = node.output[0]
        second_output = node.output[1]
        first_consumers = consumers.get(first_output, [])
        second_consumers = consumers.get(second_output, [])
        if first_consumers:
            continue
        if not any(c.op_type in ("CastLike", "Add") for c in second_consumers):
            continue
        loop_candidate = node
        loop_target_output = second_output
        break

    if loop_candidate is None:
        raise RuntimeError("Could not find Loop candidate to patch")

    seq_node: onnx.NodeProto | None = None
    for loop_input in loop_candidate.input:
        prod = producers.get(loop_input)
        if prod and prod.op_type == "SequenceEmpty":
            seq_node = prod
            break

    return loop_candidate, seq_node, loop_target_output


def patch_convnext_model(model_path: Path, output_path: Path) -> dict[str, object]:
    model = onnx.load(str(model_path), load_external_data=False)
    seq_ops_before = _count_sequence_ops(model)

    loop_node, sequence_node, loop_output_name = _find_patch_nodes(model.graph)
    channel_dim = _resolve_channel_dim(model.graph)
    indices = np.arange(channel_dim, dtype=np.int64).reshape(1, channel_dim, 1, 1)

    replacement_const = helper.make_node(
        "Constant",
        inputs=[],
        outputs=[loop_output_name],
        name="openvino_compat_indices_const",
        value=numpy_helper.from_array(indices, name="openvino_compat_indices_tensor"),
    )

    rewritten_nodes: list[onnx.NodeProto] = []
    for node in model.graph.node:
        if sequence_node is not None and node is sequence_node:
            continue
        if node is loop_node:
            rewritten_nodes.append(replacement_const)
            continue
        rewritten_nodes.append(node)

    model.graph.ClearField("node")
    model.graph.node.extend(rewritten_nodes)

    seq_ops_after = _count_sequence_ops(model)
    onnx.save(model, str(output_path))

    return {
        "loop_name": loop_node.name,
        "sequence_name": sequence_node.name if sequence_node is not None else None,
        "loop_output": loop_output_name,
        "channel_dim": channel_dim,
        "sequence_ops_before": seq_ops_before,
        "sequence_ops_after": seq_ops_after,
        "output_path": str(output_path),
    }


def _replace_with_backup(src: Path, patched: Path) -> tuple[Path, Path]:
    timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = src.with_name(f"{src.stem}.pre_openvino_patch.{timestamp}{src.suffix}")
    src.rename(backup)
    patched.rename(src)
    return backup, src


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch ConvNeXt ONNX model for OpenVINO compatibility")
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("/data/models/convnext_large_inat21/model.onnx"),
        help="Path to source model.onnx",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Patched model output path (default: <model>.openvino.onnx)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace source model with patched model and keep timestamped backup",
    )
    args = parser.parse_args()

    model_path = args.model.resolve()
    if not model_path.exists():
        raise SystemExit(f"Model path not found: {model_path}")

    if args.output is not None:
        output_path = args.output.resolve()
    else:
        output_path = model_path.with_name(f"{model_path.stem}.openvino{model_path.suffix}")

    report = patch_convnext_model(model_path, output_path)
    print("Patch report:")
    for key, value in report.items():
        print(f"  - {key}: {value}")

    if args.replace:
        backup, replaced = _replace_with_backup(model_path, output_path)
        print(f"Replaced source model: {replaced}")
        print(f"Backup created at: {backup}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
