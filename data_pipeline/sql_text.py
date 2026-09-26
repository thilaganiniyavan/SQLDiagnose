# sql_text.py
# Span-preserving view over a SQL string. Mutations are expressed as edits of exact
# character spans of the original text, so a mutated query differs from its source only
# where the error was introduced (no formatting artefacts a classifier could latch onto).

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from sqlglot.dialects.sqlite import SQLite
from sqlglot.errors import TokenError

from analysis.schema import DatabaseSchema

_DIALECT = SQLite()

CLAUSE_TYPES = {"SELECT", "FROM", "WHERE", "GROUP_BY", "HAVING", "ORDER_BY", "LIMIT",
                "UNION", "INTERSECT", "EXCEPT", "SEMICOLON"}
JOIN_TYPES = {"JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "CROSS", "NATURAL", "FULL"}
COMPARISON_TYPES = {"EQ", "NEQ", "GT", "GTE", "LT", "LTE"}
NAME_TYPES = {"VAR", "IDENTIFIER"}
AGGREGATES = {"count", "sum", "avg", "min", "max"}


@dataclass
class Tok:
    type: str
    text: str
    start: int          # inclusive
    end: int            # exclusive
    depth: int          # parenthesis depth before this token
    index: int

    @property
    def lower(self) -> str:
        return self.text.lower()


Edit = Tuple[int, int, str]   # (start, end, replacement)


class SQLText:
    def __init__(self, sql: str):
        self.sql = sql
        self.tokens: List[Tok] = []
        depth = 0
        for i, t in enumerate(_DIALECT.tokenize(sql)):
            ttype = t.token_type.name
            if ttype == "R_PAREN":
                depth -= 1
            self.tokens.append(Tok(ttype, t.text, t.start, t.end + 1, depth, i))
            if ttype == "L_PAREN":
                depth += 1

    @classmethod
    def try_parse(cls, sql: str) -> Optional["SQLText"]:
        try:
            return cls(sql)
        except (TokenError, ValueError):
            return None

    # ------------------------------------------------------------------ editing
    def apply(self, edits: Sequence[Edit]) -> str:
        out, pos = [], 0
        for start, end, text in sorted(edits, key=lambda e: (e[0], e[1])):
            if start < pos:
                raise ValueError("overlapping edits")
            out.append(self.sql[pos:start])
            out.append(text)
            pos = end
        out.append(self.sql[pos:])
        return "".join(out)

    def delete_token(self, tok: Tok) -> Edit:
        """Deletes a token, keeping exactly one space between neighbours that need separating."""
        start, end = tok.start, tok.end
        left = self.sql[start - 1] if start > 0 else ""
        right = self.sql[end] if end < len(self.sql) else ""
        if left == " " and right == " ":
            while end < len(self.sql) and self.sql[end] == " ":
                end += 1
            return (start, end, "")
        if left not in ("", " ") and right not in ("", " ") and (left.isalnum() or left in "_\"'`") \
                and (right.isalnum() or right in "_\"'`"):
            return (start, end, " ")
        return (start, end, "")

    def replace_token(self, tok: Tok, text: str) -> Edit:
        return (tok.start, tok.end, text)

    def insert_before(self, tok: Tok, text: str) -> Edit:
        return (tok.start, tok.start, text)

    def insert_after(self, tok: Tok, text: str) -> Edit:
        return (tok.end, tok.end, text)

    def span(self, first: Tok, last: Tok) -> Tuple[int, int]:
        return first.start, last.end

    # ------------------------------------------------------------------ queries
    def of_type(self, *types: str) -> List[Tok]:
        return [t for t in self.tokens if t.type in types]

    def prev(self, tok: Tok) -> Optional[Tok]:
        return self.tokens[tok.index - 1] if tok.index > 0 else None

    def next(self, tok: Tok) -> Optional[Tok]:
        return self.tokens[tok.index + 1] if tok.index + 1 < len(self.tokens) else None

    def is_function_name(self, tok: Tok) -> bool:
        nxt = self.next(tok)
        return tok.type == "VAR" and nxt is not None and nxt.type == "L_PAREN"

    def clause_end(self, tok: Tok, stop_types=CLAUSE_TYPES) -> Tok:
        """Last token of the clause that starts at `tok` (same depth, until the next clause keyword)."""
        last = tok
        for t in self.tokens[tok.index + 1:]:
            if t.depth < tok.depth or (t.depth == tok.depth and t.type in stop_types):
                break
            last = t
        return last

    def table_refs(self, schema: DatabaseSchema) -> List[Tuple[Tok, Optional[Tok]]]:
        """(table token, alias token or None) for every FROM/JOIN source that names a schema table."""
        refs = []
        for t in self.tokens:
            if t.type not in NAME_TYPES:
                continue
            p = self.prev(t)
            if p is None or p.type not in ("FROM", "JOIN", "COMMA"):
                continue
            if p.type == "COMMA" and not self._in_from_list(t):
                continue
            if not schema.has_table(t.text):
                continue
            alias = None
            n = self.next(t)
            if n is not None and n.type == "ALIAS":
                n = self.next(n)
            if n is not None and n.type in NAME_TYPES and n.index != t.index:
                alias = n
            refs.append((t, alias))
        return refs

    def _in_from_list(self, tok: Tok) -> bool:
        for t in reversed(self.tokens[:tok.index]):
            if t.depth != tok.depth:
                continue
            if t.type == "FROM":
                return True
            if t.type in CLAUSE_TYPES or t.type == "ON":
                return False
        return False

    def alias_map(self, schema: DatabaseSchema) -> Dict[str, str]:
        """alias (lower) -> table name, including tables referenced without alias."""
        amap = {}
        for table, alias in self.table_refs(schema):
            amap[table.lower] = table.text
            if alias is not None:
                amap[alias.lower] = table.text
        return amap

    def column_refs(self, schema: DatabaseSchema) -> List[Tuple[Optional[Tok], Tok, Optional[str]]]:
        """
        (qualifier token, column token, resolved table name) for identifiers that name schema columns.
        Resolution is best effort (unqualified names resolve to the first FROM table that has them).
        """
        amap = self.alias_map(schema)
        from_tables = [t.text for t, _ in self.table_refs(schema)]
        refs = []
        for t in self.tokens:
            if t.type not in NAME_TYPES or self.is_function_name(t):
                continue
            p = self.prev(t)
            if p is not None and p.type in ("FROM", "JOIN", "ALIAS"):
                continue
            n = self.next(t)
            if n is not None and n.type == "DOT":
                continue                                     # this is a qualifier
            qualifier = p if (p is not None and p.type == "DOT") else None
            qual_tok = self.prev(qualifier) if qualifier is not None else None
            if qual_tok is not None:
                table = amap.get(qual_tok.lower)
                if table is None or not schema.table(table).column(t.text):
                    continue
                refs.append((qual_tok, t, schema.table(table).name))
            else:
                owners = [tb for tb in from_tables if schema.table(tb).column(t.text)]
                if not owners:
                    continue
                refs.append((None, t, owners[0]))
        return refs

    def string_literals(self, schema: DatabaseSchema) -> List[Tok]:
        """String values: single-quoted literals, plus double-quoted tokens that name no column or table
        (SQLite falls back to treating those as strings, and Spider uses them that way)."""
        cols = {c.lower() for c in schema.all_column_names()}
        out = []
        for t in self.tokens:
            if t.type == "STRING":
                out.append(t)
            elif (t.type == "IDENTIFIER" and self.sql[t.start] == '"'
                  and t.lower not in cols and not schema.has_table(t.text)):
                out.append(t)
        return out
