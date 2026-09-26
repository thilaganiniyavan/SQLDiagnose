# analyzer.py
# Deterministic SQL diagnostics.
#
# Two layers:
#   1. Engine check - the query is compiled (EXPLAIN, never executed) by SQLite against an
#      empty in-memory database that has the target schema. SQLite's compiler reports
#      grammar errors, unknown tables/columns, ambiguous references and several semantic
#      errors with precise messages.
#   2. Static rules on the sqlglot AST for problems SQLite tolerates but standard SQL
#      (and PostgreSQL/MySQL strict mode) rejects: NULL compared with '=', GROUP BY
#      violations, missing join conditions, type mismatches, duplicate table aliases,
#      and access-policy violations.
#
# Without a schema, a permissive schema is synthesised from the query itself so that
# syntax and schema-independent semantic errors are still detected.

import re
from typing import Dict, Iterator, List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from models.domain.entities import AnalysisResult, Issue
from models.domain.labels import PRIORITY
from .schema import NUMBER, TEXT, Column, DatabaseSchema, Table

_ENGINE_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"syntax error|incomplete input|unrecognized token|unterminated|one statement at a time|"
                r"should come after", re.I), "SYNTAX_ERROR"),
    (re.compile(r"not authorized", re.I), "SYNTAX_ERROR"),
    (re.compile(r"no such table: (?P<tok>.+)", re.I), "UNKNOWN_TABLE"),
    (re.compile(r"no such column: (?P<tok>.+)", re.I), "UNKNOWN_COLUMN"),
    (re.compile(r"ambiguous column name: (?P<tok>.+)", re.I), "AMBIGUOUS_REFERENCE"),
    (re.compile(r"no such function: (?P<tok>.+)", re.I), "SEMANTIC_ERROR"),
    (re.compile(r"misuse of (aggregate|window)|wrong number of arguments|term out of range|"
                r"same number of result columns|sub-select returns|row value misused|"
                r"not allowed|circular reference|must appear", re.I), "SEMANTIC_ERROR"),
]

_FORBIDDEN_START = re.compile(r"^\s*(attach|detach|pragma|vacuum|reindex|analyze)\b", re.I)
_NUMERIC_LITERAL = re.compile(r"^\s*[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?\s*$")
_NUMERIC_AGGS = (exp.Sum, exp.Avg)
_COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)

def normalize_query(query: str) -> str:
    q = (query or "").strip()
    while q.endswith(";"):
        q = q[:-1].rstrip()
    return q


def classify_engine_error(message: str) -> Tuple[str, Optional[str]]:
    for pattern, cls in _ENGINE_RULES:
        m = pattern.search(message)
        if m:
            tok = m.groupdict().get("tok")
            return cls, tok.strip() if tok else None
    return "SEMANTIC_ERROR", None


def _walk_scope(node: exp.Expression) -> Iterator[exp.Expression]:
    """Yields descendants of `node` without entering nested SELECTs / subqueries."""
    stack = list(node.iter_expressions())
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, (exp.Select, exp.Subquery, exp.Union, exp.Except, exp.Intersect)):
            continue
        stack.extend(n.iter_expressions())


def _is_aggregate(node: exp.Expression) -> bool:
    return isinstance(node, exp.AggFunc) and not isinstance(node.parent, exp.Window)


def _contains_aggregate(node: exp.Expression) -> bool:
    if _is_aggregate(node):
        return True
    return any(_is_aggregate(n) for n in _walk_scope(node))


def _bare_columns(node: exp.Expression) -> List[exp.Column]:
    """Columns in `node` that are not inside an aggregate, window or subquery."""
    out: List[exp.Column] = []
    if isinstance(node, (exp.AggFunc, exp.Window, exp.Select, exp.Subquery)):
        return out
    if isinstance(node, exp.Column):
        return [node]
    stack = list(node.iter_expressions())
    while stack:
        n = stack.pop()
        if isinstance(n, (exp.AggFunc, exp.Window, exp.Select, exp.Subquery)):
            continue
        if isinstance(n, exp.Column):
            out.append(n)
            continue
        stack.extend(n.iter_expressions())
    return out


def _string_value(node: exp.Expression) -> Optional[str]:
    if isinstance(node, exp.Literal) and node.is_string:
        return node.this
    return None


def _is_number_literal(node: exp.Expression) -> bool:
    if isinstance(node, exp.Neg):
        node = node.this
    return isinstance(node, exp.Literal) and not node.is_string


class _SelectScope:
    """Name resolution for one SELECT: alias -> schema table."""

    def __init__(self, select: exp.Select, schema: DatabaseSchema, cte_names: Set[str]):
        self.select = select
        self.schema = schema
        self.sources: List[Tuple[str, Optional[Table]]] = []   # (alias, table or None for derived/cte)
        from_ = select.args.get("from_") or select.args.get("from")
        nodes = []
        if from_ is not None:
            nodes.append(from_.this)
        for j in select.args.get("joins") or []:
            nodes.append(j.this)
        for n in nodes:
            alias = n.alias_or_name
            if isinstance(n, exp.Table) and n.name.lower() not in cte_names:
                self.sources.append((alias, schema.table(n.name)))
            else:
                self.sources.append((alias, None))

    def resolve(self, col: exp.Column) -> Optional[Tuple[Table, Column]]:
        if col.table:
            for alias, table in self.sources:
                if alias.lower() == col.table.lower() and table is not None:
                    c = table.column(col.name)
                    return (table, c) if c else None
            return None
        hits = []
        for _, table in self.sources:
            if table is not None and table.column(col.name):
                hits.append((table, table.column(col.name)))
        return hits[0] if len(hits) == 1 else None


class SQLAnalyzer:
    """Deterministic analyzer. Thread-safe; one instance can serve many requests."""

    def analyze(self, query: str, schema: Optional[DatabaseSchema] = None) -> AnalysisResult:
        q = normalize_query(query)
        if not q:
            return AnalysisResult("SYNTAX_ERROR", [Issue("SYNTAX_ERROR", "The query is empty.", source="engine")],
                                  engine_error="empty query", schema_checked=schema is not None)
        if _FORBIDDEN_START.match(q):
            msg = "Only data queries (SELECT/INSERT/UPDATE/DELETE) can be diagnosed."
            return AnalysisResult("SYNTAX_ERROR", [Issue("SYNTAX_ERROR", msg, source="engine")],
                                  engine_error=msg, schema_checked=schema is not None)

        schema_checked = schema is not None and bool(schema.tables)
        tree = self._parse(q)
        if schema_checked:
            check_schema = schema
        else:
            check_schema = self._synthesise_schema(tree) if tree is not None else DatabaseSchema([], "empty")

        issues: List[Issue] = []
        engine_error = check_schema.compile_errors(q)
        if engine_error:
            cls, tok = classify_engine_error(engine_error)
            issues.append(Issue(cls, self._engine_message(cls, engine_error, tok), tok, "engine"))

        if tree is not None and not (engine_error and issues[0].error_class == "SYNTAX_ERROR"):
            if schema_checked:
                issues.extend(self._policy_issues(tree, schema))
            if not engine_error:
                issues.extend(self._static_issues(tree, check_schema, typed=schema_checked))

        issues = self._dedupe(issues)
        primary = "CORRECT"
        if issues:
            primary = min((i.error_class for i in issues), key=PRIORITY.index)
            issues.sort(key=lambda i: PRIORITY.index(i.error_class))
        return AnalysisResult(primary, issues, engine_error, schema_checked)

    # ---------------------------------------------------------------- engine layer
    @staticmethod
    def _engine_message(cls: str, raw: str, tok: Optional[str]) -> str:
        if cls == "SYNTAX_ERROR":
            if "incomplete input" in raw:
                return "The query ends unexpectedly (missing operand, closing parenthesis or clause body)."
            if "unrecognized token" in raw:
                return f"Unrecognized token {raw.split(':', 1)[-1].strip()} (often an unterminated string or stray character)."
            if "one statement" in raw:
                return "Only a single SQL statement can be diagnosed at a time."
            if "not authorized" in raw:
                return "This statement type is not allowed."
            m = re.match(r'near (.+): syntax error', raw)
            return f"Syntax error near {m.group(1)}." if m else f"Syntax error: {raw}."
        if cls == "UNKNOWN_TABLE":
            return f"Table '{tok}' does not exist in the schema."
        if cls == "UNKNOWN_COLUMN":
            return f"Column '{tok}' does not exist in the referenced table(s)."
        if cls == "AMBIGUOUS_REFERENCE":
            return f"Column reference '{tok}' is ambiguous: it matches more than one table in FROM/JOIN."
        if raw.startswith("no such function"):
            return f"Function '{tok}' does not exist."
        return raw[0].upper() + raw[1:] + "."

    # ---------------------------------------------------------------- parsing helpers
    @staticmethod
    def _parse(q: str) -> Optional[exp.Expression]:
        try:
            trees = sqlglot.parse(q, read="sqlite")
        except (SqlglotError, ValueError, RecursionError):
            return None
        trees = [t for t in trees if t is not None]
        return trees[0] if len(trees) == 1 else None

    @staticmethod
    def _cte_names(tree: exp.Expression) -> Set[str]:
        return {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}

    def _synthesise_schema(self, tree: exp.Expression) -> DatabaseSchema:
        """Permissive schema: every referenced table exists with every column the query uses on it."""
        ctes = self._cte_names(tree)
        tables: Dict[str, Table] = {}
        alias_to_table: Dict[str, str] = {}
        for t in tree.find_all(exp.Table):
            if not t.name or t.name.lower() in ctes:
                continue
            tables.setdefault(t.name.lower(), Table(t.name))
            alias_to_table[t.alias_or_name.lower()] = t.name.lower()
        derived_aliases = {s.alias.lower() for s in tree.find_all(exp.Subquery) if s.alias} | ctes
        select_aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)}
        for col in tree.find_all(exp.Column):
            name = col.name
            if not name or isinstance(col.this, exp.Star):
                continue
            target = None
            if col.table:
                if col.table.lower() in derived_aliases:
                    continue
                target = alias_to_table.get(col.table.lower())
            else:
                if name.lower() in select_aliases:
                    continue
                sel = col.find_ancestor(exp.Select)
                from_ = sel.args.get("from_") if sel is not None else None
                if from_ is not None and isinstance(from_.this, exp.Table):
                    target = from_.this.name.lower() if from_.this.name.lower() in tables else None
            if target and not tables[target].column(name):
                tables[target].columns.append(Column(name))
        return DatabaseSchema(tables.values(), "synthetic")

    # ---------------------------------------------------------------- policy layer
    def _policy_issues(self, tree: exp.Expression, schema: DatabaseSchema) -> List[Issue]:
        if not schema.restricted_tables and not schema.restricted_columns:
            return []
        issues: List[Issue] = []
        ctes = self._cte_names(tree)
        for t in tree.find_all(exp.Table):
            if t.name and t.name.lower() not in ctes and t.name.lower() in schema.restricted_tables:
                issues.append(Issue("PERMISSION_DENIED",
                                    f"Access to table '{t.name}' is denied by the access policy.", t.name, "policy"))
        if schema.restricted_columns:
            for sel in tree.find_all(exp.Select):
                scope = _SelectScope(sel, schema, ctes)
                for col in _walk_scope(sel):
                    if isinstance(col, exp.Column) and not isinstance(col.this, exp.Star):
                        hit = scope.resolve(col)
                        if hit and schema.is_restricted(hit[0].name, hit[1].name):
                            issues.append(Issue("PERMISSION_DENIED",
                                                f"Access to column '{hit[0].name}.{hit[1].name}' is denied by the access policy.",
                                                f"{hit[0].name}.{hit[1].name}", "policy"))
                    elif col.parent is sel and (isinstance(col, exp.Star) or
                                                (isinstance(col, exp.Column) and isinstance(col.this, exp.Star))):
                        qual = col.table if isinstance(col, exp.Column) else ""
                        for alias, table in scope.sources:
                            if table is None or (qual and alias.lower() != qual.lower()):
                                continue
                            for c in table.columns:
                                if schema.is_restricted(table.name, c.name):
                                    issues.append(Issue("PERMISSION_DENIED",
                                                        f"'*' expands to restricted column '{table.name}.{c.name}'.",
                                                        f"{table.name}.{c.name}", "policy"))
        return issues

    # ---------------------------------------------------------------- static rules
    def _static_issues(self, tree: exp.Expression, schema: DatabaseSchema, typed: bool) -> List[Issue]:
        issues: List[Issue] = []
        ctes = self._cte_names(tree)
        for sel in tree.find_all(exp.Select):
            scope = _SelectScope(sel, schema, ctes)
            issues.extend(self._duplicate_alias(sel))
            issues.extend(self._null_comparisons(sel))
            issues.extend(self._self_comparisons(sel))
            issues.extend(self._join_conditions(sel, scope))
            issues.extend(self._grouping(sel, scope, typed))
            if typed:
                issues.extend(self._types(sel, scope))
        return issues

    @staticmethod
    def _duplicate_alias(sel: exp.Select) -> List[Issue]:
        from_ = sel.args.get("from_")
        nodes = ([from_.this] if from_ is not None else []) + [j.this for j in sel.args.get("joins") or []]
        seen: Set[str] = set()
        out = []
        for n in nodes:
            name = n.alias_or_name.lower()
            if not name:
                continue
            if name in seen:
                out.append(Issue("AMBIGUOUS_REFERENCE",
                                 f"'{n.alias_or_name}' is used for more than one table in FROM/JOIN; give each a distinct alias.",
                                 n.alias_or_name, "static"))
            seen.add(name)
        return out

    @staticmethod
    def _null_comparisons(sel: exp.Select) -> List[Issue]:
        out = []
        for n in _walk_scope(sel):
            if isinstance(n, (exp.EQ, exp.NEQ)) and (isinstance(n.left, exp.Null) or isinstance(n.right, exp.Null)):
                op = "=" if isinstance(n, exp.EQ) else "<>"
                fix = "IS NULL" if isinstance(n, exp.EQ) else "IS NOT NULL"
                out.append(Issue("SEMANTIC_ERROR",
                                 f"'{op} NULL' is never true; use {fix} instead ({n.sql()}).", n.sql(), "static"))
        return out

    @staticmethod
    def _self_comparisons(sel: exp.Select) -> List[Issue]:
        out = []
        for n in _walk_scope(sel):
            if isinstance(n, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)) \
                    and isinstance(n.left, exp.Column) and isinstance(n.right, exp.Column) \
                    and n.left.sql().lower() == n.right.sql().lower():
                verdict = "always true" if isinstance(n, (exp.EQ, exp.GTE, exp.LTE)) else "never true"
                out.append(Issue("SEMANTIC_ERROR", f"'{n.sql()}' compares a column with itself and is {verdict}.",
                                 n.sql(), "static"))
        return out

    @staticmethod
    def _join_conditions(sel: exp.Select, scope: _SelectScope) -> List[Issue]:
        """
        Every source in FROM/JOIN must be connected to the others through ON/WHERE predicates
        (or an explicit CROSS/NATURAL/USING join); otherwise the query silently builds a Cartesian product.
        """
        joins = sel.args.get("joins") or []
        if not joins:
            return []
        aliases = [a.lower() for a, _ in scope.sources]
        parent = {a: a for a in aliases}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        def alias_of(col: exp.Column) -> Optional[str]:
            if col.table:
                return col.table.lower() if col.table.lower() in parent else None
            owners = [a.lower() for a, t in scope.sources if t is not None and t.column(col.name)]
            return owners[0] if len(owners) == 1 else None

        for j in joins:
            if j.args.get("kind") == "CROSS" or j.args.get("method") or j.args.get("using"):
                union(aliases[0], j.this.alias_or_name.lower())
        conds = [sel.args.get("where")] + [j.args.get("on") for j in joins]
        for cond in conds:
            if cond is None or (isinstance(cond, exp.Boolean) and cond.this is True):
                continue
            for pred in [cond] + list(_walk_scope(cond)):
                if not isinstance(pred, (exp.Binary, exp.In, exp.Between)) or isinstance(pred, (exp.And, exp.Or)):
                    continue
                used = {alias_of(c) for c in _walk_scope(pred) if isinstance(c, exp.Column)}
                used |= {alias_of(pred.left)} if isinstance(getattr(pred, "left", None), exp.Column) else set()
                used |= {alias_of(pred.right)} if isinstance(getattr(pred, "right", None), exp.Column) else set()
                used.discard(None)
                used = list(used)
                for other in used[1:]:
                    union(used[0], other)
        out = []
        root = find(aliases[0])
        for j in joins:
            alias = j.this.alias_or_name.lower()
            if alias in parent and find(alias) != root:
                out.append(Issue("SEMANTIC_ERROR",
                                 f"{j.this.alias_or_name} is joined without a condition linking it to the other tables "
                                 f"(Cartesian product).", j.this.alias_or_name, "static"))
        return out

    @staticmethod
    def _grouping(sel: exp.Select, scope: _SelectScope, typed: bool) -> List[Issue]:
        out = []
        projections = sel.expressions
        group = sel.args.get("group")
        having = sel.args.get("having")
        has_agg = any(_contains_aggregate(p) for p in projections) or (having is not None)
        if group is None and not has_agg:
            return out
        if group is None:
            if not any(_contains_aggregate(p) for p in projections) and having is not None and not _contains_aggregate(having):
                out.append(Issue("SEMANTIC_ERROR", "HAVING is used without GROUP BY or any aggregate.", None, "static"))
                return out
            for p in projections:
                for col in _bare_columns(p.this if isinstance(p, exp.Alias) else p):
                    if isinstance(col.this, exp.Star):
                        continue
                    out.append(Issue("SEMANTIC_ERROR",
                                     f"Column '{col.sql()}' is selected alongside an aggregate but is not in a GROUP BY clause.",
                                     col.sql(), "static"))
            return out

        group_exprs = list(group.expressions)
        group_keys = {g.sql().lower() for g in group_exprs}
        group_names = {g.name.lower() for g in group_exprs if isinstance(g, exp.Column)}
        grouped_cols: Set[Tuple[str, str]] = set()
        for g in group_exprs:
            if isinstance(g, exp.Column):
                hit = scope.resolve(g)
                if hit:
                    grouped_cols.add((hit[0].name.lower(), hit[1].name.lower()))
        # Columns equated to a grouped column (JOIN ... ON a.x = b.x, WHERE a.x = b.x) are grouped too,
        # as in MySQL's functional-dependency detection.
        equalities = []
        for cond in [sel.args.get("where")] + [j.args.get("on") for j in sel.args.get("joins") or []]:
            if cond is None:
                continue
            for eq in [cond] + list(_walk_scope(cond)):
                if isinstance(eq, exp.EQ) and isinstance(eq.left, exp.Column) and isinstance(eq.right, exp.Column):
                    l, r = scope.resolve(eq.left), scope.resolve(eq.right)
                    if l and r:
                        equalities.append(((l[0].name.lower(), l[1].name.lower()), (r[0].name.lower(), r[1].name.lower())))
        changed = True
        while changed:
            changed = False
            for a, b in equalities:
                if (a in grouped_cols) != (b in grouped_cols):
                    grouped_cols |= {a, b}
                    changed = True
        # positional GROUP BY (e.g. GROUP BY 1) -> trust it
        if any(isinstance(g, exp.Literal) for g in group_exprs):
            return out
        aliases = {p.alias.lower() for p in projections if isinstance(p, exp.Alias)}

        def covered(col: exp.Column) -> bool:
            if col.sql().lower() in group_keys or col.name.lower() in aliases:
                return True
            hit = scope.resolve(col)
            if hit is None:
                # unresolved: fall back to name comparison
                return col.name.lower() in group_names or not typed
            table, column = hit
            if (table.name.lower(), column.name.lower()) in grouped_cols:
                return True
            # functional dependency: grouping by the table's primary key determines its other columns
            pks = {p.lower() for p in table.primary_keys}
            return bool(pks) and pks <= {c for t, c in grouped_cols if t == table.name.lower()}

        for p in projections:
            node = p.this if isinstance(p, exp.Alias) else p
            if node.sql().lower() in group_keys:
                continue
            for col in _bare_columns(node):
                if isinstance(col.this, exp.Star):
                    continue
                if not covered(col):
                    out.append(Issue("SEMANTIC_ERROR",
                                     f"Column '{col.sql()}' must appear in GROUP BY or be used in an aggregate function.",
                                     col.sql(), "static"))
        if having is not None:
            for col in _bare_columns(having):
                if not covered(col):
                    out.append(Issue("SEMANTIC_ERROR",
                                     f"HAVING references '{col.sql()}', which is neither grouped nor aggregated.",
                                     col.sql(), "static"))
        return out

    @staticmethod
    def _types(sel: exp.Select, scope: _SelectScope) -> List[Issue]:
        out = []

        def col_type(node) -> Optional[str]:
            if isinstance(node, exp.Column):
                hit = scope.resolve(node)
                return hit[1].type if hit else None
            return None

        for n in _walk_scope(sel):
            if isinstance(n, _COMPARISONS):
                pairs = [(n.left, n.right), (n.right, n.left)]
            elif isinstance(n, exp.Between):
                pairs = [(n.this, n.args.get("low")), (n.this, n.args.get("high"))]
            elif isinstance(n, exp.In) and n.expressions:
                pairs = [(n.this, e) for e in n.expressions]
            else:
                pairs = []
            reported = False
            for a, b in pairs:
                if reported or a is None or b is None:
                    continue
                ta = col_type(a)
                if ta is None:
                    continue
                s = _string_value(b)
                if ta == NUMBER and s is not None and not _NUMERIC_LITERAL.match(s):
                    out.append(Issue("DATATYPE_MISMATCH",
                                     f"Numeric column '{a.sql()}' is compared with the text value '{s}'.", a.sql(), "static"))
                    reported = True
                elif ta == TEXT and _is_number_literal(b):
                    out.append(Issue("DATATYPE_MISMATCH",
                                     f"Text column '{a.sql()}' is compared with the number {b.sql()}; quote the value.",
                                     a.sql(), "static"))
                    reported = True
            if isinstance(n, _NUMERIC_AGGS):
                arg = n.this
                if isinstance(arg, exp.Distinct):
                    arg = arg.expressions[0] if arg.expressions else None
                if col_type(arg) == TEXT:
                    fn = n.key.upper()
                    out.append(Issue("DATATYPE_MISMATCH",
                                     f"{fn}() is applied to the text column '{arg.sql()}'.", arg.sql(), "static"))
        return out

    @staticmethod
    def _dedupe(issues: List[Issue]) -> List[Issue]:
        seen, out = set(), []
        for i in issues:
            key = (i.error_class, i.message)
            if key not in seen:
                seen.add(key)
                out.append(i)
        return out
