"""Pygments lexer for the RQL language subset."""

from pygments.lexer import RegexLexer, bygroups
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String, Text


class RqlLexer(RegexLexer):
    """Lightweight lexer to highlight RQL statements inside the REPL."""

    name = "RQL"
    aliases = ["rql"]
    filenames = ["*.rql"]

    KEYWORDS = (
        "SELECT",
        "FROM",
        "TASK",
        "ANSWER",
        "SUMMARIZE",
        "EXTRACT",
        "WITH",
        "RETURN",
        "JSON",
        "TEXT",
        "MARKDOWN",
        "DEFINE",
        "SOURCE",
        "POLICY",
        "TYPE",
        "USING",
        "AS",
        "SET",
        "DESCRIBE",
        "SOURCES",
        "POLICIES",
        "INTO",
        "REF",
        "REQUIRE",
        "DETERMINISM",
        "STRONG",
        "PROVIDER",
    )

    tokens = {
        "root": [
            (r"--.*$", Comment.Single),
            (r"\s+", Text),
            (r"(REQUIRE)(\s+)(DETERMINISM)(\s+)(STRONG|PROVIDER)", bygroups(Keyword, Text, Keyword, Text, Keyword)),
            (r"(" + "|".join(KEYWORDS) + r")\b", Keyword),
            (r"(TASK)(\s+)(ANSWER|SUMMARIZE|EXTRACT)", bygroups(Keyword, Text, Keyword)),
            (r"[A-Za-z_][A-Za-z0-9_]*", Name),
            (r"[{}()\[\],.;]", Punctuation),
            (r"[=:+-]", Operator),
            (r'"([^"\\]|\\.)*"', String.Double),
            (r"'(?:[^'\\]|\\.)*'", String.Single),
            (r"-?\d+\.\d+", Number.Float),
            (r"-?\d+", Number.Integer),
        ]
    }
