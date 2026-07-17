"""
Writes parsed module/file data to Neo4j.

Python schema:
  Nodes:         Module, Class, Method, Function, Parameter
  Relationships: DEFINES_CLASS, DEFINES_FUNCTION, HAS_METHOD,
                 INHERITS_FROM, HAS_PARAMETER, IMPORTS

Terraform schema:
  Nodes:         TFFile, Resource, TFModule, Variable, Output, DataSource, Provider
  Relationships: DEFINES_RESOURCE, CALLS_MODULE, DEFINES_VARIABLE,
                 DEFINES_OUTPUT, USES_DATA, USES_PROVIDER
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
            SET mt.line = $line, mt.docstring = $docstring, mt.returns = $returns,
                mt.string_literals = $string_literals
            """,
            name=method["name"], file_path=file_path, class_name=cls["name"],
            line=method["line"], docstring=method["docstring"], returns=method["returns"],
            string_literals=method["string_literals"],
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
        SET f.line = $line, f.docstring = $docstring, f.returns = $returns,
            f.string_literals = $string_literals
        """,
        name=func["name"], file_path=file_path,
        line=func["line"], docstring=func["docstring"], returns=func["returns"],
        string_literals=func["string_literals"],
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


def write_parsed_tf_file(session: Session, data: dict) -> None:
    file_path = data["file"]["file_path"]

    session.run(
        "MERGE (f:TFFile {file_path: $file_path}) SET f.name = $name",
        file_path=file_path, name=data["file"]["name"],
    )

    for r in data["resources"]:
        session.run(
            """
            MERGE (res:Resource {type: $type, name: $name, file_path: $file_path})
            SET res.description = $description
            """,
            type=r["type"], name=r["name"], file_path=file_path,
            description=r["description"],
        )
        session.run(
            """
            MATCH (f:TFFile {file_path: $file_path})
            MATCH (res:Resource {type: $type, name: $name, file_path: $file_path})
            MERGE (f)-[:DEFINES_RESOURCE]->(res)
            """,
            file_path=file_path, type=r["type"], name=r["name"],
        )

    for m in data["modules"]:
        session.run(
            """
            MERGE (mod:TFModule {name: $name, file_path: $file_path})
            SET mod.source = $source, mod.version = $version
            """,
            name=m["name"], file_path=file_path,
            source=m["source"], version=m["version"],
        )
        session.run(
            """
            MATCH (f:TFFile {file_path: $file_path})
            MATCH (mod:TFModule {name: $name, file_path: $file_path})
            MERGE (f)-[:CALLS_MODULE]->(mod)
            """,
            file_path=file_path, name=m["name"],
        )

    for v in data["variables"]:
        session.run(
            """
            MERGE (var:Variable {name: $name, file_path: $file_path})
            SET var.var_type = $var_type, var.default = $default,
                var.description = $description
            """,
            name=v["name"], file_path=file_path,
            var_type=v["var_type"], default=v["default"],
            description=v["description"],
        )
        session.run(
            """
            MATCH (f:TFFile {file_path: $file_path})
            MATCH (var:Variable {name: $name, file_path: $file_path})
            MERGE (f)-[:DEFINES_VARIABLE]->(var)
            """,
            file_path=file_path, name=v["name"],
        )

    for o in data["outputs"]:
        session.run(
            """
            MERGE (out:Output {name: $name, file_path: $file_path})
            SET out.value = $value, out.description = $description
            """,
            name=o["name"], file_path=file_path,
            value=o["value"], description=o["description"],
        )
        session.run(
            """
            MATCH (f:TFFile {file_path: $file_path})
            MATCH (out:Output {name: $name, file_path: $file_path})
            MERGE (f)-[:DEFINES_OUTPUT]->(out)
            """,
            file_path=file_path, name=o["name"],
        )

    for d in data["data_sources"]:
        session.run(
            """
            MERGE (ds:DataSource {type: $type, name: $name, file_path: $file_path})
            SET ds.description = $description
            """,
            type=d["type"], name=d["name"], file_path=file_path,
            description=d["description"],
        )
        session.run(
            """
            MATCH (f:TFFile {file_path: $file_path})
            MATCH (ds:DataSource {type: $type, name: $name, file_path: $file_path})
            MERGE (f)-[:USES_DATA]->(ds)
            """,
            file_path=file_path, type=d["type"], name=d["name"],
        )

    for p in data["providers"]:
        session.run(
            """
            MERGE (prov:Provider {type: $type})
            """,
            type=p["type"],
        )
        session.run(
            """
            MATCH (f:TFFile {file_path: $file_path})
            MATCH (prov:Provider {type: $type})
            MERGE (f)-[:USES_PROVIDER]->(prov)
            """,
            file_path=file_path, type=p["type"],
        )


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
