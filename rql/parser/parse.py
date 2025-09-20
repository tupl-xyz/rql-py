"""RQL Parser implementation using Lark."""

from pathlib import Path
from typing import Any, Dict, List, Union

from lark import Lark, Token, Transformer
from lark.exceptions import LarkError

from ..engine.ast import (
    DefinePolicy,
    DefineSource,
    DescribeStmt,
    DeterminismLevel,
    RefCall,
    SelectStmt,
    SetStmt,
    Statement,
    TaskInvocation,
)


class RQLParseError(Exception):
    """Exception raised when RQL parsing fails."""

    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Parse error at line {line}, column {column}: {message}")


class RQLParser:
    """Parser for RQL statements using Lark grammar."""

    def __init__(self):
        grammar_path = Path(__file__).parent / "grammar.lark"
        with open(grammar_path) as f:
            grammar = f.read()

        self.parser = Lark(
            grammar,
            parser="lalr",
        )
        self.transformer = RQLTransformer()

    def parse(self, text: str) -> List[Statement]:
        """Parse RQL text into a list of Statement objects."""
        try:
            tree = self.parser.parse(text)
            return self.transformer.transform(tree)
        except LarkError as e:
            raise RQLParseError(str(e)) from e

    def parse_file(self, path: Path) -> List[Statement]:
        """Parse an RQL file into a list of Statement objects."""
        try:
            with open(path) as f:
                content = f.read()
            return self.parse(content)
        except FileNotFoundError:
            raise RQLParseError(f"File not found: {path}")
        except Exception as e:
            raise RQLParseError(f"Error reading file {path}: {e}")


class RQLTransformer(Transformer):
    """Transforms Lark parse tree into RQL AST objects."""

    def stmt_list(self, items: List[Statement]) -> List[Statement]:
        """Transform statement list."""
        return items

    def set_stmt(self, items: List[Union[Token, Any]]) -> SetStmt:
        """Transform SET statement."""
        key = str(items[0])
        raw = items[1] if len(items) > 1 else None
        value = self._convert_literal_value(raw)
        return SetStmt(key=key, value=value)

    def define_source(self, items: List[Union[Token, Any]]) -> DefineSource:
        """Transform DEFINE SOURCE statement."""
        name = str(items[0])
        source_type = str(items[1])
        config = items[2]
        alias = str(items[3]) if len(items) > 3 else None
        return DefineSource(
            name=name,
            source_type=source_type,
            config=config,
            alias=alias
        )

    def define_policy(self, items: List[Union[Token, Any]]) -> DefinePolicy:
        """Transform DEFINE POLICY statement."""
        name = str(items[0])
        config = items[1]
        return DefinePolicy(name=name, config=config)

    def desc_sources(self, _items: List[Any]) -> str:
        """Transform SOURCES target."""
        return "SOURCES"

    def desc_policies(self, _items: List[Any]) -> str:
        """Transform POLICIES target."""
        return "POLICIES"

    def describe_stmt(self, items: List[str]) -> DescribeStmt:
        """Transform DESCRIBE statement."""
        target = items[0]
        return DescribeStmt(target=target)

    def select_stmt(self, items: List[Any]) -> SelectStmt:
        """Transform SELECT statement - task-only."""
        select_items = items[0]
        task_invocation = items[1]  # Always TaskInvocation

        # Process optional clauses
        with_params = {}
        policy_name = None
        determinism_level = DeterminismLevel.PROVIDER
        return_format = "TEXT"
        into_var = None

        for item in items[2:]:
            # Handle DeterminismLevel objects first (isinstance doesn't work due to import issues)
            if item is not None and 'DeterminismLevel' in str(type(item)):
                determinism_level = item
                continue

            if isinstance(item, list) and len(item) > 0:
                if isinstance(item[0], tuple):  # WITH clause
                    for key, value in item:
                        with_params[key] = value
            elif isinstance(item, str):
                if item in ["JSON", "TEXT", "MARKDOWN"]:
                    return_format = item
                elif item.startswith("var_"):
                    into_var = item[4:]  # Remove 'var_' prefix
                else:
                    policy_name = item

        return SelectStmt(
            select_items=select_items,
            task_invocation=task_invocation,
            with_params=with_params,
            policy_name=policy_name,
            determinism_level=determinism_level,
            return_format=return_format,
            into_var=into_var
        )

    def select_items(self, items: List[str]) -> List[str]:
        """Transform select items list."""
        return items

    def sel_output(self, _items: List[Any]) -> str:
        """Transform OUTPUT selector."""
        return "OUTPUT"

    def sel_evidence(self, _items: List[Any]) -> str:
        """Transform EVIDENCE selector."""
        return "EVIDENCE"

    def sel_confidence(self, _items: List[Any]) -> str:
        """Transform CONFIDENCE selector."""
        return "CONFIDENCE"

    def sel_star(self, _items: List[Any]) -> str:
        """Transform * selector."""
        return "*"

    def task_invocation(self, items: List[Any]) -> TaskInvocation:
        """Transform task invocation (only execution method)."""
        task_name_token = items[0]
        task_args = items[1] if len(items) > 1 else {}

        # Extract task name from token
        task_name = task_name_token.type.replace('task_', '').upper()

        return TaskInvocation(name=task_name, args=task_args)

    def task_answer(self, _items: List[Any]) -> Token:
        """Transform ANSWER task name."""
        token = Token("task_answer", "ANSWER")
        return token

    def task_summarize(self, _items: List[Any]) -> Token:
        """Transform SUMMARIZE task name."""
        token = Token("task_summarize", "SUMMARIZE")
        return token

    def task_extract(self, _items: List[Any]) -> Token:
        """Transform EXTRACT task name."""
        token = Token("task_extract", "EXTRACT")
        return token

    def task_args(self, items: List[Any]) -> Dict[str, Any]:
        """Transform task arguments into dictionary."""
        args = {}
        for arg in items:
            if isinstance(arg, tuple):
                key, value = arg
                args[key] = value
            elif hasattr(arg, 'ref_key') and isinstance(arg.ref_call, RefCall):
                # Handle REF calls with their associated keys
                args[arg.ref_key] = arg.ref_call
        return args

    def task_arg(self, items: List[Any]) -> Union[tuple, Any]:
        """Transform individual task argument."""
        if len(items) == 2:
            # Handle basic parameters: NAME ":" literal
            key = str(items[0])
            value = self._convert_literal_value(items[1])
            return (key, value)
        elif len(items) == 3:
            # Handle REF calls: "context" ":" ref_call
            ref_key = str(items[0])  # context, input_ref, text_ref
            ref_call = items[2]
            # Create a temporary object to carry both pieces
            class RefArg:
                def __init__(self, key, call):
                    self.ref_key = key
                    self.ref_call = call
            return RefArg(ref_key, ref_call)
        elif len(items) == 1 and isinstance(items[0], dict):
            # Handle schema object shorthand: schema: { ... }
            return ("schema", items[0])
        return items[0]

    def ref_call(self, items: List[Any]) -> RefCall:
        """Transform REF() call."""
        source_name = str(items[0])
        args = items[1] if len(items) > 1 else {}
        return RefCall(source=source_name, args=args)

    def determinism_clause(self, items: List[Any]) -> DeterminismLevel:
        """Transform determinism requirement."""
        level_token = items[0]
        level_str = level_token.type.replace('det_', '')
        return DeterminismLevel(level_str)

    def det_provider(self, _items: List[Any]) -> Token:
        """Transform provider determinism level."""
        return Token("det_provider", "provider")

    def det_strong(self, _items: List[Any]) -> Token:
        """Transform strong determinism level."""
        return Token("det_strong", "strong")

    def dotted_name(self, items: List[Token]) -> str:
        """Transform dotted name like 'decode.temperature'."""
        return '.'.join(str(item) for item in items)

    def with_clause(self, items: List[tuple]) -> List[tuple]:
        """Transform WITH clause."""
        return items

    def with_kv(self, items: List[Union[str, Any]]) -> tuple:
        """Transform WITH key=value, supporting dotted keys."""
        key = items[0]  # Can be dotted like 'decode.temperature'
        value = self._convert_literal_value(items[1])
        return (key, value)

    def _convert_literal_value(self, value: Any) -> Any:
        """Convert Token literals to proper Python types."""
        if isinstance(value, Token):
            if value.type == "SIGNED_NUMBER":
                # Convert to int if no decimal, float otherwise
                if '.' in value.value:
                    return float(value.value)
                else:
                    return int(value.value)
            elif value.type == "ESCAPED_STRING":
                # Remove quotes and handle escape sequences
                return value.value[1:-1]  # Remove surrounding quotes
            else:
                # Handle inline literal tokens like 'true', 'false', 'null'
                v = value.value.lower()
                if v == "true":
                    return True
                if v == "false":
                    return False
                if v == "null":
                    return None
        elif isinstance(value, str):
            # Handle boolean and null literals
            if value == "true":
                return True
            elif value == "false":
                return False
            elif value == "null":
                return None
        return value

    # Ensure '?literal' unpacks to a Python value
    def literal(self, items: List[Any]) -> Any:
        return self._convert_literal_value(items[0]) if items else None

    def policy_clause(self, items: List[Union[Token, Dict[str, Any]]]) -> str:
        """Transform POLICY clause."""
        if isinstance(items[0], str):
            return items[0]
        else:
            return str(items[0])

    def return_clause(self, items: List[str]) -> str:
        """Transform RETURN clause."""
        return items[0] if items else "TEXT"

    def into_clause(self, items: List[Token]) -> str:
        """Transform INTO clause."""
        return f"var_{str(items[0])}"


    # Literal value transformers
    def string(self, items: List[Token]) -> str:
        """Transform string literal."""
        # Remove quotes from the string
        return str(items[0])[1:-1]

    def number(self, items: List[Token]) -> Union[int, float]:
        """Transform number literal."""
        value = str(items[0])
        return int(value) if "." not in value else float(value)

    def true(self, _items: List[Any]) -> bool:
        """Transform true literal."""
        return True

    def false(self, _items: List[Any]) -> bool:
        """Transform false literal."""
        return False

    def null(self, _items: List[Any]) -> None:
        """Transform null literal."""
        return None

    def value(self, items: List[Any]) -> Any:
        """Unwrap generic JSON value nodes."""
        return items[0] if items else None

    # Return format tokens
    def json_format(self, _items: List[Any]) -> str:
        """Transform JSON format."""
        return "JSON"

    def text_format(self, _items: List[Any]) -> str:
        """Transform TEXT format."""
        return "TEXT"

    def markdown_format(self, _items: List[Any]) -> str:
        """Transform MARKDOWN format."""
        return "MARKDOWN"

    # JSON transformers
    def json(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Transform JSON object."""
        return items[0]

    def object(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Transform JSON object."""
        obj = {}
        for item in items:
            obj.update(item)
        return obj

    def pair(self, items: List[Any]) -> Dict[str, Any]:
        """Transform JSON key-value pair."""
        key = items[0]
        value = items[1]
        if isinstance(value, Token) or isinstance(value, str):
            value = self._convert_literal_value(value)
        elif isinstance(value, list):
            value = value
        elif isinstance(value, dict):
            value = value
        elif value is None:
            value = None
        return {key: value}

    def array(self, items: List[Any]) -> List[Any]:
        """Transform JSON array."""
        return items


def parse_rql(text: str) -> List[Statement]:
    """Convenience function to parse RQL text."""
    parser = RQLParser()
    return parser.parse(text)


def parse_rql_file(path: Path) -> List[Statement]:
    """Convenience function to parse RQL file."""
    parser = RQLParser()
    return parser.parse_file(path)
