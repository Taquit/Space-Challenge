"""
Módulo de Generación y Validación de Salida JSON Estricta
=========================================================
Define el esquema Pydantic para validar rigurosamente la estructura
de salida exigida por las especificaciones de NASA, serializando
exclusivamente desviaciones confirmadas con su contexto cuantitativo.
"""

import json
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ExpectedRange(BaseModel):
    lower: float
    upper: float


class DeviationRecord(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    timestamp: str
    variable: str
    unit: str
    actual_value: float
    predicted_value: float
    expected_range: ExpectedRange
    absolute_error: float
    standardized_residual: float
    deviation_percentage: Optional[float] = None
    status: Literal["ADVERTENCIA", "ANOMALIA"]
    deviation_type: Literal["ABOVE_EXPECTED", "BELOW_EXPECTED"]
    confidence: float
    explanation: str
    model_name: str

    @field_validator("confidence")
    def check_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence debe estar entre 0.0 y 1.0")
        return v


class Metadata(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    model_name: str
    model_version: str = "1.0"
    prediction_type: str = "One-Step-Ahead"
    generated_at: str
    subject_id: str
    data_source: str
    signal_quality: Literal["GOOD", "FAIR", "DEGRADED"] = "GOOD"


class Summary(BaseModel):
    total_measurements_analyzed: int
    normal_measurements: int
    warning_measurements: int
    anomalous_measurements: int
    overall_status: Literal["NORMAL", "ADVERTENCIA", "ANOMALIA"]


class PhysiologicalPredictionOutput(BaseModel):
    metadata: Metadata
    summary: Summary
    deviations: List[DeviationRecord]


def build_and_validate_json_output(
    model_name: str,
    subject_id: str,
    data_source: str,
    signal_quality: str,
    generated_at: str,
    total_analyzed: int,
    normal_count: int,
    warning_count: int,
    anomalous_count: int,
    deviations_list: List[Dict[str, Any]],
    output_path: Optional[str] = "results/deviations.json"
) -> str:
    """
    Construye, valida contra el esquema Pydantic y serializa el JSON final.
    """
    if anomalous_count > 0:
        overall_status = "ANOMALIA"
    elif warning_count > 0:
        overall_status = "ADVERTENCIA"
    else:
        overall_status = "NORMAL"

    payload = {
        "metadata": {
            "model_name": model_name,
            "model_version": "1.0",
            "prediction_type": "One-Step-Ahead",
            "generated_at": generated_at,
            "subject_id": subject_id,
            "data_source": data_source,
            "signal_quality": signal_quality
        },
        "summary": {
            "total_measurements_analyzed": total_analyzed,
            "normal_measurements": normal_count,
            "warning_measurements": warning_count,
            "anomalous_measurements": anomalous_count,
            "overall_status": overall_status
        },
        "deviations": deviations_list
    }

    # Validación rigurosa con Pydantic
    validated = PhysiologicalPredictionOutput.model_validate(payload)
    json_str = validated.model_dump_json(indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)

    return json_str
