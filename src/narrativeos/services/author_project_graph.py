from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..persistence.repositories import SQLAlchemyPlatformRepository
from .authoring import AuthoringService


QUANTUM_STUDIO_ENGINES = ["balanced", "effect", "speed", "cost"]


class AuthorProjectGraphService:
    def __init__(
        self,
        repository: SQLAlchemyPlatformRepository,
        *,
        authoring_service: AuthoringService,
    ) -> None:
        self.repository = repository
        self.authoring = authoring_service

    def _title(self, worldpack: Dict[str, Any], project_id: str) -> str:
        return str(worldpack.get("title") or project_id)

    def _quantum_frontend_metadata(self, worldpack: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(worldpack.get("metadata") or {})
        return dict(metadata.get("quantum_frontend") or {})

    def _engine(self, worldpack: Dict[str, Any]) -> str:
        stored = str(self._quantum_frontend_metadata(worldpack).get("engine") or "").strip()
        return stored if stored in QUANTUM_STUDIO_ENGINES else "balanced"

    def _world_rule_specs(self, worldpack: Dict[str, Any]) -> List[Dict[str, Any]]:
        world_bible = dict(worldpack.get("world_bible") or {})
        characters = list(worldpack.get("characters") or [])
        arc_plans = list(worldpack.get("arc_plans") or [])
        locations = list(world_bible.get("locations") or [])
        return [
            {"id": "rule_premise", "name": "核心设定", "default_enabled": bool(str(world_bible.get("premise") or "").strip())},
            {"id": "rule_characters", "name": "角色阵列", "default_enabled": bool(characters)},
            {"id": "rule_arc_plan", "name": "章节弧线", "default_enabled": bool(arc_plans)},
            {"id": "rule_locations", "name": "地点锚定", "default_enabled": bool(locations)},
        ]

    def _world_rules(self, worldpack: Dict[str, Any], enabled_rule_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
        if enabled_rule_ids is not None:
            enabled_set = {str(item).strip() for item in enabled_rule_ids if str(item).strip()}
            return [
                {"id": item["id"], "name": item["name"], "enabled": item["id"] in enabled_set}
                for item in self._world_rule_specs(worldpack)
            ]
        return [
            {"id": item["id"], "name": item["name"], "enabled": bool(item["default_enabled"])}
            for item in self._world_rule_specs(worldpack)
        ]

    def _characters(self, worldpack: Dict[str, Any]) -> List[Dict[str, Any]]:
        characters = []
        for index, item in enumerate(list(worldpack.get("characters") or []), start=1):
            payload = dict(item or {})
            character_id = str(
                payload.get("character_id")
                or payload.get("id")
                or payload.get("display_name")
                or payload.get("name")
                or f"character_{index}"
            ).strip()
            display_name = str(
                payload.get("display_name")
                or payload.get("name")
                or payload.get("character_id")
                or f"角色 {index}"
            ).strip()
            characters.append({"id": character_id, "name": display_name, "avatar": ""})
        return characters

    def _seed_arc_graph(self, worldpack: Dict[str, Any], *, project_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
        world_bible = dict(worldpack.get("world_bible") or {})
        volume_order_map = {
            str(item.get("volume_id") or ""): int(item.get("order") or 0)
            for item in list(worldpack.get("volume_plans") or [])
            if str(item.get("volume_id") or "").strip()
        }
        arc_plans = sorted(
            [dict(item or {}) for item in list(worldpack.get("arc_plans") or [])],
            key=lambda item: (
                volume_order_map.get(str(item.get("volume_id") or ""), 10_000),
                int(item.get("order") or 0),
                str(item.get("arc_id") or ""),
            ),
        )[:12]
        nodes: List[Dict[str, Any]] = [
            {
                "id": project_id,
                "title": self._title(worldpack, project_id),
                "type": "root",
                "x": 380,
                "y": 72,
                "description": str(world_bible.get("premise") or ""),
                "status": "active",
            }
        ]
        connections: List[Dict[str, Any]] = []
        for index, arc in enumerate(arc_plans):
            arc_id = str(arc.get("arc_id") or f"arc_{index + 1}").strip()
            first_task = dict((list(arc.get("chapter_tasks") or [{}]) or [{}])[0] or {})
            description = str(
                first_task.get("objective")
                or first_task.get("notes")
                or arc.get("title")
                or arc.get("completion_conditions")
                or ""
            ).strip()
            nodes.append(
                {
                    "id": arc_id,
                    "title": str(arc.get("title") or f"章节弧线 {index + 1}").strip(),
                    "type": "branch",
                    "x": 120 + (index % 3) * 260,
                    "y": 260 + (index // 3) * 210,
                    "description": description,
                    "status": "active",
                }
            )
            connections.append(
                {
                    "from": project_id,
                    "to": arc_id,
                    "label": str(arc.get("volume_id") or ""),
                }
            )
        return nodes, connections, "arc_plan_projection"

    def _seed_graph_from_worldpack(self, worldpack: Dict[str, Any], *, project_id: str) -> Dict[str, Any]:
        quantum_frontend = self._quantum_frontend_metadata(worldpack)
        stored_nodes = list(quantum_frontend.get("nodes") or [])
        stored_connections = list(quantum_frontend.get("connections") or [])
        if stored_nodes:
            nodes = []
            for index, item in enumerate(stored_nodes):
                payload = dict(item or {})
                node_id = str(payload.get("id") or f"node_{index + 1}").strip()
                if not node_id:
                    continue
                nodes.append(
                    {
                        "id": node_id,
                        "title": str(payload.get("title") or node_id),
                        "type": str(payload.get("type") or "branch"),
                        "x": int(payload.get("x") or 0),
                        "y": int(payload.get("y") or 0),
                        "description": str(payload.get("description") or ""),
                        "status": str(payload.get("status") or "active"),
                    }
                )
            connections = [
                {
                    "from": str(dict(item or {}).get("from") or ""),
                    "to": str(dict(item or {}).get("to") or ""),
                    "label": str(dict(item or {}).get("label") or ""),
                }
                for item in stored_connections
                if str(dict(item or {}).get("from") or "").strip() and str(dict(item or {}).get("to") or "").strip()
            ]
            if nodes:
                return {
                    "engine": self._engine(worldpack),
                    "enabled_rule_ids": [item["id"] for item in self._world_rules(worldpack, quantum_frontend.get("enabled_rule_ids")) if item["enabled"]],
                    "nodes": nodes,
                    "connections": connections,
                    "metadata_json": {"graph_source": "worldpack_quantum_frontend"},
                }
        nodes, connections, source = self._seed_arc_graph(worldpack, project_id=project_id)
        return {
            "engine": self._engine(worldpack),
            "enabled_rule_ids": [item["id"] for item in self._world_rules(worldpack, None) if item["enabled"]],
            "nodes": nodes,
            "connections": connections,
            "metadata_json": {"graph_source": source},
        }

    def _mirror_into_worldpack(
        self,
        worldpack: Dict[str, Any],
        *,
        engine: str,
        enabled_rule_ids: List[str],
        nodes: List[Dict[str, Any]],
        connections: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        next_worldpack = copy.deepcopy(worldpack)
        metadata = dict(next_worldpack.get("metadata") or {})
        quantum_frontend = dict(metadata.get("quantum_frontend") or {})
        quantum_frontend["engine"] = engine
        quantum_frontend["enabled_rule_ids"] = list(enabled_rule_ids)
        quantum_frontend["nodes"] = list(nodes)
        quantum_frontend["connections"] = list(connections)
        metadata["quantum_frontend"] = quantum_frontend
        next_worldpack["metadata"] = metadata
        return next_worldpack

    def _persist_graph_and_mirror(
        self,
        *,
        project_id: str,
        draft_detail: Dict[str, Any],
        engine: str,
        enabled_rule_ids: List[str],
        nodes: List[Dict[str, Any]],
        connections: List[Dict[str, Any]],
        change_context: Dict[str, Any],
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        worldpack = dict(draft_detail.get("worldpack") or {})
        mirrored_worldpack = self._mirror_into_worldpack(
            worldpack,
            engine=engine,
            enabled_rule_ids=enabled_rule_ids,
            nodes=nodes,
            connections=connections,
        )
        updated_draft = self.authoring.update_draft(project_id, mirrored_worldpack, change_context=change_context)
        self.repository.save_author_project_graph(
            {
                "project_id": project_id,
                "world_version_id": project_id,
                "account_id": str(((updated_draft.get("worldpack") or {}).get("manifest") or {}).get("author_id") or ""),
                "engine": engine,
                "enabled_rule_ids": enabled_rule_ids,
                "nodes": nodes,
                "connections": connections,
                "metadata_json": dict(metadata_json or {}),
            }
        )
        return updated_draft

    def _graph_row(self, *, project_id: str, draft_detail: Dict[str, Any]) -> Dict[str, Any]:
        row = self.repository.get_author_project_graph(project_id, default=None)
        if row is not None:
            return row
        seed = self._seed_graph_from_worldpack(dict(draft_detail.get("worldpack") or {}), project_id=project_id)
        return self.repository.save_author_project_graph(
            {
                "project_id": project_id,
                "world_version_id": project_id,
                "account_id": str(((draft_detail.get("worldpack") or {}).get("manifest") or {}).get("author_id") or ""),
                **seed,
            }
        )

    def project_payload(self, *, project_id: str, draft_detail: Dict[str, Any]) -> Dict[str, Any]:
        worldpack = dict(draft_detail.get("worldpack") or {})
        graph = self._graph_row(project_id=project_id, draft_detail=draft_detail)
        return {
            "id": project_id,
            "title": self._title(worldpack, project_id),
            "engine": str(graph.get("engine") or self._engine(worldpack)),
            "availableEngines": list(QUANTUM_STUDIO_ENGINES),
            "worldRules": self._world_rules(worldpack, list(graph.get("enabled_rule_ids") or [])),
            "characters": self._characters(worldpack),
            "nodes": list(graph.get("nodes") or []),
            "connections": list(graph.get("connections") or []),
        }

    def set_engine(self, *, project_id: str, draft_detail: Dict[str, Any], engine: str) -> Dict[str, Any]:
        graph = self._graph_row(project_id=project_id, draft_detail=draft_detail)
        updated = self._persist_graph_and_mirror(
            project_id=project_id,
            draft_detail=draft_detail,
            engine=engine,
            enabled_rule_ids=list(graph.get("enabled_rule_ids") or []),
            nodes=list(graph.get("nodes") or []),
            connections=list(graph.get("connections") or []),
            change_context={"source": "author_project_graph_set_engine", "label": "Quantum Studio set engine"},
            metadata_json={**dict(graph.get("metadata_json") or {}), "graph_source": "author_project_graph"},
        )
        return self.project_payload(project_id=project_id, draft_detail=updated)

    def set_world_rules(self, *, project_id: str, draft_detail: Dict[str, Any], rule_ids: List[str]) -> Dict[str, Any]:
        graph = self._graph_row(project_id=project_id, draft_detail=draft_detail)
        updated = self._persist_graph_and_mirror(
            project_id=project_id,
            draft_detail=draft_detail,
            engine=str(graph.get("engine") or self._engine(dict(draft_detail.get("worldpack") or {}))),
            enabled_rule_ids=sorted(set(rule_ids)),
            nodes=list(graph.get("nodes") or []),
            connections=list(graph.get("connections") or []),
            change_context={"source": "author_project_graph_set_rules", "label": "Quantum Studio update world rules"},
            metadata_json={**dict(graph.get("metadata_json") or {}), "graph_source": "author_project_graph"},
        )
        return self.project_payload(project_id=project_id, draft_detail=updated)

    def add_node(self, *, project_id: str, draft_detail: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        graph = self._graph_row(project_id=project_id, draft_detail=draft_detail)
        nodes = list(graph.get("nodes") or [])
        connections = list(graph.get("connections") or [])
        node_id = f"studio_node_{uuid4().hex[:10]}"
        nodes.append(
            {
                "id": node_id,
                "title": str(payload.get("title") or "新节点").strip() or "新节点",
                "type": str(payload.get("type") or "branch"),
                "x": int(payload.get("x") or 0),
                "y": int(payload.get("y") or 0),
                "description": str(payload.get("description") or ""),
                "status": "active",
            }
        )
        parent_id = str(payload.get("parentId") or project_id).strip() or project_id
        if parent_id != node_id and any(str(item.get("id") or "") == parent_id for item in nodes):
            connections.append({"from": parent_id, "to": node_id, "label": ""})
        updated = self._persist_graph_and_mirror(
            project_id=project_id,
            draft_detail=draft_detail,
            engine=str(graph.get("engine") or self._engine(dict(draft_detail.get("worldpack") or {}))),
            enabled_rule_ids=list(graph.get("enabled_rule_ids") or []),
            nodes=nodes,
            connections=connections,
            change_context={"source": "author_project_graph_add_node", "label": "Quantum Studio add node"},
            metadata_json={**dict(graph.get("metadata_json") or {}), "graph_source": "author_project_graph"},
        )
        return self.project_payload(project_id=project_id, draft_detail=updated)

    def update_node(self, *, project_id: str, draft_detail: Dict[str, Any], node_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        graph = self._graph_row(project_id=project_id, draft_detail=draft_detail)
        nodes = list(graph.get("nodes") or [])
        connections = list(graph.get("connections") or [])
        target = next((item for item in nodes if str(item.get("id") or "") == node_id), None)
        if target is None:
            raise KeyError("studio_node_missing")
        if payload.get("title") is not None:
            target["title"] = str(payload.get("title") or "").strip() or target["title"]
        if payload.get("description") is not None:
            target["description"] = str(payload.get("description") or "")
        if payload.get("x") is not None:
            target["x"] = int(payload.get("x"))
        if payload.get("y") is not None:
            target["y"] = int(payload.get("y"))
        updated = self._persist_graph_and_mirror(
            project_id=project_id,
            draft_detail=draft_detail,
            engine=str(graph.get("engine") or self._engine(dict(draft_detail.get("worldpack") or {}))),
            enabled_rule_ids=list(graph.get("enabled_rule_ids") or []),
            nodes=nodes,
            connections=connections,
            change_context={"source": "author_project_graph_update_node", "label": "Quantum Studio update node"},
            metadata_json={**dict(graph.get("metadata_json") or {}), "graph_source": "author_project_graph"},
        )
        return self.project_payload(project_id=project_id, draft_detail=updated)

    def export_project(self, *, project: Dict[str, Any], format_value: str) -> str:
        normalized = str(format_value or "").strip().lower()
        if normalized == "json":
            return json.dumps(project, ensure_ascii=False, indent=2)
        lines = [
            f"# {project['title']}",
            "",
            f"- projectId: {project['id']}",
            f"- engine: {project['engine']}",
            f"- worldRules: {', '.join(item['name'] for item in project.get('worldRules', []) if item.get('enabled')) or '-'}",
            "",
            "## Characters",
            *(f"- {item['name']}" for item in project.get("characters", [])),
            "",
            "## Nodes",
            *(f"- {item['id']}: {item['title']} ({item['type']})" for item in project.get("nodes", [])),
            "",
            "## Connections",
            *(f"- {item['from']} -> {item['to']}" + (f" [{item['label']}]" if item.get("label") else "") for item in project.get("connections", [])),
        ]
        return "\n".join(lines).strip() + "\n"
