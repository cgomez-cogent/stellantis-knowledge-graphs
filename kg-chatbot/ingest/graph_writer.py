"""
Writes parsed module data to Neo4j.

Schema:
  Nodes:         Module, Class, Method, Function, Parameter
  Relationships: DEFINES_CLASS, DEFINES_FUNCTION, HAS_METHOD,
                 INHERITS_FROM, HAS_PARAMETER, IMPORTS
"""

import logging
from neo4j import Driver, Session

logger = logging.getLogger(__name__)


def clear_graph(driver: Driver) -> None:
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    logger.info("Graph cleared.")


def write_parsed_module(session: Session, data: dict) -> None:
    mod_name = data["module"]["name"]
    file_path = data["module"]["file_path"]

    session.run(
        "MERGE (m:Module {name: $name}) SET m.file_path = $file_path",
        name=mod_name, file_path=file_path,
    )

    for cls in data["classes"]:
        _write_class(session, cls, mod_name, file_path)

    for func in data["functions"]:
        _write_function(session, func, mod_name, file_path)

    for imp in data["imports"]:
        session.run(
            """
            MATCH (m:Module {name: $mod_name})
            MERGE (i:Module {name: $imp_name})
            MERGE (m)-[:IMPORTS]->(i)
            """,
            mod_name=mod_name, imp_name=imp,
        )


def _write_class(session: Session, cls: dict, mod_name: str, file_path: str) -> None:
    session.run(
        """
        MERGE (c:Class {name: $name, file_path: $file_path})
        SET c.line = $line, c.docstring = $docstring
        """,
        name=cls["name"], file_path=file_path,
        line=cls["line"], docstring=cls["docstring"],
    )
    session.run(
        """
        MATCH (m:Module {name: $mod_name})
        MATCH (c:Class {name: $cls_name, file_path: $file_path})
        MERGE (m)-[:DEFINES_CLASS]->(c)
        """,
        mod_name=mod_name, cls_name=cls["name"], file_path=file_path,
    )

    for base in cls["bases"]:
        session.run(
            """
            MATCH (c:Class {name: $cls_name, file_path: $file_path})
            MERGE (b:Class {name: $base_name})
            MERGE (c)-[:INHERITS_FROM]->(b)
            """,
            cls_name=cls["name"], file_path=file_path, base_name=base,
        )

    for method in cls["methods"]:
        session.run(
            """
            MERGE (mt:Method {name: $name, file_path: $file_path, class_name: $class_name})
            SET mt.line = $line, mt.docstring = $docstring, mt.returns = $returns
            """,
            name=method["name"], file_path=file_path, class_name=cls["name"],
            line=method["line"], docstring=method["docstring"], returns=method["returns"],
        )
        session.run(
            """
            MATCH (c:Class {name: $cls_name, file_path: $file_path})
            MATCH (mt:Method {name: $method_name, file_path: $file_path, class_name: $cls_name})
            MERGE (c)-[:HAS_METHOD]->(mt)
            """,
            cls_name=cls["name"], file_path=file_path, method_name=method["name"],
        )
        _write_params(session, "Method", method["name"], file_path, cls["name"], method["params"])


def _write_function(session: Session, func: dict, mod_name: str, file_path: str) -> None:
    session.run(
        """
        MERGE (f:Function {name: $name, file_path: $file_path})
        SET f.line = $line, f.docstring = $docstring, f.returns = $returns
        """,
        name=func["name"], file_path=file_path,
        line=func["line"], docstring=func["docstring"], returns=func["returns"],
    )
    session.run(
        """
        MATCH (m:Module {name: $mod_name})
        MATCH (f:Function {name: $func_name, file_path: $file_path})
        MERGE (m)-[:DEFINES_FUNCTION]->(f)
        """,
        mod_name=mod_name, func_name=func["name"], file_path=file_path,
    )
    _write_params(session, "Function", func["name"], file_path, None, func["params"])


def _write_params(
    session: Session,
    parent_label: str,
    parent_name: str,
    file_path: str,
    class_name: str | None,
    params: list[dict],
) -> None:
    for param in params:
        if class_name is not None:
            session.run(
                f"""
                MATCH (p:{parent_label} {{name: $parent_name, file_path: $file_path, class_name: $class_name}})
                MERGE (param:Parameter {{name: $param_name, parent_name: $parent_name,
                                         class_name: $class_name, file_path: $file_path}})
                SET param.annotation = $annotation, param.default = $default
                MERGE (p)-[:HAS_PARAMETER]->(param)
                """,
                parent_name=parent_name, file_path=file_path, class_name=class_name,
                param_name=param["name"], annotation=param["annotation"], default=param["default"],
            )
        else:
            session.run(
                f"""
                MATCH (p:{parent_label} {{name: $parent_name, file_path: $file_path}})
                MERGE (param:Parameter {{name: $param_name, parent_name: $parent_name,
                                         class_name: '', file_path: $file_path}})
                SET param.annotation = $annotation, param.default = $default
                MERGE (p)-[:HAS_PARAMETER]->(param)
                """,
                parent_name=parent_name, file_path=file_path,
                param_name=param["name"], annotation=param["annotation"], default=param["default"],
            )
