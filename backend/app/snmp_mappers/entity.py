"""ENTITY-MIB and ENTITY-SENSOR-MIB mapper with explicit class evidence."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..contracts import StrictModel
from ..ssh import ConnectionPolicyError
from .common import int_value, text_value


ENTITY_COLUMNS = {
    "description": "1.3.6.1.2.1.47.1.1.1.1.2",
    "contained_in": "1.3.6.1.2.1.47.1.1.1.1.4",
    "class": "1.3.6.1.2.1.47.1.1.1.1.5",
    "parent_position": "1.3.6.1.2.1.47.1.1.1.1.6",
    "name": "1.3.6.1.2.1.47.1.1.1.1.7",
    "serial": "1.3.6.1.2.1.47.1.1.1.1.11",
}
SENSOR_COLUMNS = {
    "type": "1.3.6.1.2.1.99.1.1.1.1",
    "scale": "1.3.6.1.2.1.99.1.1.1.2",
    "precision": "1.3.6.1.2.1.99.1.1.1.3",
    "value": "1.3.6.1.2.1.99.1.1.1.4",
    "status": "1.3.6.1.2.1.99.1.1.1.5",
}

ENTITY_CLASSES = {3: "chassis", 6: "psu", 7: "fan", 8: "sensor", 9: "module", 10: "port", 11: "stack_member"}
SENSOR_TYPES = {1: "other", 2: "unknown", 3: "volts_ac", 4: "volts_dc", 5: "amperes", 6: "watts",
                7: "hertz", 8: "celsius", 9: "percent_relative_humidity", 10: "rpm", 11: "cmm",
                12: "truth_value"}
SCALES = {1: -24, 2: -21, 3: -18, 4: -15, 5: -12, 6: -9, 7: -6, 8: -3, 9: 0,
          10: 3, 11: 6, 12: 9, 13: 12, 14: 15, 15: 18, 16: 21, 17: 24}


class EntityRecord(StrictModel):
    index: int = Field(ge=1)
    entity_class: Literal["chassis", "psu", "fan", "sensor", "module", "port", "stack_member", "unknown"]
    name: str = Field(max_length=160)
    description: str = Field(max_length=300)
    serial: str | None = Field(default=None, max_length=160)
    contained_in: int | None = Field(default=None, ge=0)
    parent_position: int | None = None
    connector: Literal["unknown"] = "unknown"
    source: Literal["snmp"] = "snmp"


class SensorRecord(StrictModel):
    entity_index: int = Field(ge=1)
    sensor_type: Literal[
        "other", "unknown", "volts_ac", "volts_dc", "amperes", "watts",
        "hertz", "celsius", "percent_relative_humidity", "rpm", "cmm",
        "truth_value",
    ]
    value: float | None = None
    status: Literal["ok", "unavailable", "nonoperational", "unknown"]
    source: Literal["snmp"] = "snmp"


def parse_entity_mib(columns, sensors):
    indices = sorted(set(columns.get("class", {})) | set(columns.get("name", {})))
    entities, partial = [], False
    for index in indices:
        raw_class = columns.get("class", {}).get(index)
        if raw_class is None:
            partial = True
            class_name = "unknown"
        else:
            class_name = ENTITY_CLASSES.get(int_value(raw_class), "unknown")
        name = text_value(columns.get("name", {}).get(index, ""), maximum=160)
        description = text_value(columns.get("description", {}).get(index, ""), maximum=300)
        serial = text_value(columns.get("serial", {}).get(index, ""), maximum=160) or None
        if not name and not description:
            partial = True
            continue
        entities.append(EntityRecord(
            index=int(index), entity_class=class_name, name=name or description,
            description=description, serial=serial,
            contained_in=(int_value(columns["contained_in"][index]) if index in columns.get("contained_in", {}) else None),
            parent_position=(int(columns["parent_position"][index]) if index in columns.get("parent_position", {}) else None),
        ))
    readings = []
    for index, raw_value in sorted(sensors.get("value", {}).items()):
        sensor_type = SENSOR_TYPES.get(int_value(sensors.get("type", {}).get(index, 2)), "unknown")
        status = {1: "ok", 2: "unavailable", 3: "nonoperational"}.get(
            int_value(sensors.get("status", {}).get(index, 2)), "unknown")
        scale = SCALES.get(int_value(sensors.get("scale", {}).get(index, 9)))
        try:
            precision = int(sensors.get("precision", {}).get(index, 0))
        except (TypeError, ValueError, OverflowError):
            precision = 10
        value = None
        if scale is not None and -8 <= precision <= 9:
            try:
                value = int(raw_value) * (10 ** (scale - precision))
            except (TypeError, ValueError, OverflowError):
                partial = True
        else:
            partial = True
        readings.append(SensorRecord(entity_index=int(index), sensor_type=sensor_type,
                                     value=value, status=status))
    return {
        "entities": [entity.model_dump(mode="json") for entity in entities],
        "sensors": [sensor.model_dump(mode="json") for sensor in readings],
    }, bool(entities) and not partial

