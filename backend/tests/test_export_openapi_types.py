from scripts.export_openapi_types import render


def test_render_openapi_types_covers_components_paths_and_payload_shapes():
    schema = {
        "components": {
            "schemas": {
                "Bird-Result": {
                    "type": "object",
                    "required": ["id", "species", "tags"],
                    "properties": {
                        "id": {"type": "integer"},
                        "species": {"type": "string"},
                        "confidence": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "status": {"enum": ["new", "reviewed"]},
                        "metadata": {"type": "object", "additionalProperties": {"type": "string"}},
                    },
                },
                "Update Request": {
                    "type": "object",
                    "required": ["enabled"],
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "note": {"type": ["string", "null"]},
                    },
                },
            }
        },
        "paths": {
            "/api/birds/{event_id}": {
                "patch": {
                    "operationId": "update_bird",
                    "parameters": [
                        {
                            "name": "event_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "include_hidden",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "boolean"},
                        },
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Update Request"},
                            },
                        },
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Bird-Result"},
                                },
                            },
                        },
                    },
                }
            },
            "/api/birds/stream": {
                "get": {
                    "operationId": "stream_birds",
                    "responses": {
                        "200": {
                            "content": {
                                "text/event-stream": {
                                    "schema": {"type": "string"},
                                },
                            },
                        },
                    },
                }
            },
        },
    }

    output = render(schema)

    assert "export interface components" in output
    assert "BirdResult: {" in output
    assert "id: number;" in output
    assert "confidence?: number | null;" in output
    assert 'status?: "new" | "reviewed";' in output
    assert "metadata?: Record<string, string>;" in output
    assert "UpdateRequest: {" in output
    assert "note?: string | null;" in output
    assert '"/api/birds/{event_id}": {' in output
    assert 'operationId: "update_bird";' in output
    assert "event_id: string;" in output
    assert "include_hidden?: boolean;" in output
    assert "requestBody: components['schemas']['UpdateRequest'];" in output
    assert "response: components['schemas']['BirdResult'];" in output
    assert '"/api/birds/stream": {' in output
    assert 'operationId: "stream_birds";' in output
    assert "path: never;" in output
    assert "query: never;" in output
    assert "response: string;" in output
