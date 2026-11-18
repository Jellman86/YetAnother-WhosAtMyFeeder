"""Every cause a status verdict can carry is in the list the status column words, and no other."""

import ast
import json
from pathlib import Path
from typing import get_args

from app.models.service_connections import MqttConnectionState
from app.services import system_status
from app.services.system_status import MQTT_PRESSURE_LEVELS

CAUSES = json.loads((Path(__file__).parent.parent / "fixtures" / "status_causes.json").read_text())["causes"]


def _verdict_calls() -> list[tuple[str, ast.Call]]:
    """Every `SubsystemVerdict(...)` written in system_status.py, with the function it is in."""
    tree = ast.parse(Path(system_status.__file__).read_text())
    calls: list[tuple[str, ast.Call]] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "SubsystemVerdict":
                calls.append((function.name, node))
    return calls


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _is_mqtt_state(function: str, cause: ast.expr) -> bool:
    """`cause=state` in the broker verdict: a connection that is not connected names its state."""
    return function == "_mqtt_verdict" and isinstance(cause, ast.Name) and cause.id == "state"


def _is_pressure(function: str, cause: ast.expr) -> bool:
    """`cause=f"pressure_{pressure}"` in the broker verdict, for a level in MQTT_PRESSURE_LEVELS."""
    if function != "_mqtt_verdict" or not isinstance(cause, ast.JoinedStr):
        return False
    parts = cause.values
    return (
        len(parts) == 2
        and isinstance(parts[0], ast.Constant)
        and parts[0].value == "pressure_"
        and isinstance(parts[1], ast.FormattedValue)
        and isinstance(parts[1].value, ast.Name)
        and parts[1].value.id == "pressure"
    )


def _sayable() -> dict[str, set[str]]:
    """Every cause the verdicts can carry: the literals, and the two computed forms expanded."""
    found: dict[str, set[str]] = {}
    for function, call in _verdict_calls():
        key, cause = _keyword(call, "key"), _keyword(call, "cause")
        assert isinstance(key, ast.Constant), f"{function}: a verdict's key must be written out"
        assert cause is not None, f"{function}: a verdict without a cause"
        causes = found.setdefault(key.value, set())
        if isinstance(cause, ast.Constant):
            causes.add(cause.value)
        elif _is_mqtt_state(function, cause):
            causes.update(set(get_args(MqttConnectionState)) - {"connected", "connecting"})
        elif _is_pressure(function, cause):
            causes.update(f"pressure_{level}" for level in MQTT_PRESSURE_LEVELS)
        else:
            raise AssertionError(
                f"{function} computes a cause in a new way ({ast.unparse(cause)}): write it out, or teach this test "
                "and the status column's words every value it can take"
            )
    return found


def test_every_cause_a_verdict_can_carry_is_in_the_worded_list():
    for key, causes in _sayable().items():
        assert causes <= set(CAUSES[key]), (key, causes - set(CAUSES[key]))


def test_the_list_names_nothing_the_status_cannot_say():
    sayable = _sayable()
    for key, causes in CAUSES.items():
        assert set(causes) <= sayable.get(key, set()), (key, set(causes) - sayable.get(key, set()))


def test_a_cause_computed_in_a_new_way_is_refused():
    # A verdict whose cause is a variable could carry a value nobody has worded.
    function = ast.parse(
        'def _storage_verdict(inputs):\n    return SubsystemVerdict(key="storage", state="error", cause=reason)'
    )
    call = next(node for node in ast.walk(function) if isinstance(node, ast.Call))
    cause = _keyword(call, "cause")
    assert cause is not None
    assert not isinstance(cause, ast.Constant)
    assert not _is_mqtt_state("_storage_verdict", cause)
    assert not _is_pressure("_storage_verdict", cause)
