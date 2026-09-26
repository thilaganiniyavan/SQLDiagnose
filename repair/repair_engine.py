# repair_engine.py
# Verified SQL repair.
#
# For the primary issue reported by the analyzer, class-specific generators propose candidate
# rewrites (fuzzy schema matching, keyword correction, clause re-ordering, foreign-key join
# inference, AST rewrites, and a bounded single-edit search for grammar errors). Every candidate
# is re-analyzed; the engine keeps the candidate that removes the issue with the smallest change,
# and iterates until the query is clean or no candidate helps. A repair is reported as successful
# only when the final query passes the analyzer.

import difflib
import re
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from analysis.analyzer import SQLAnalyzer, normalize_query
from analysis.schema import NUMBER, TEXT, DatabaseSchema
from data_pipeline.sql_text import CLAUSE_TYPES, NAME_TYPES, SQLText, Tok
from models.domain.entities import AnalysisResult, Issue, RepairResult, RepairStep
from models.domain.labels import PRIORITY

Candidate = Tuple  # (sql, description) or (sql, description, preference); lower preference wins ties

KEYWORDS = ["SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "HAVING", "JOIN", "ON", "LIMIT", "AND", "OR",
            "NOT", "DISTINCT", "AS", "INNER", "LEFT", "UNION", "INTERSECT", "EXCEPT", "BETWEEN", "LIKE", "IN",
            "IS", "NULL", "DESC", "ASC", "CASE", "WHEN", "THEN", "ELSE", "END", "EXISTS", "OFFSET"]
FUNCTIONS = ["count", "sum", "avg", "min", "max", "lower", "upper", "length", "abs", "round", "substr",
             "coalesce", "ifnull", "strftime", "date", "julianday", "replace", "trim", "instr",
             "group_concat", "total", "cast", "nullif", "datetime", "time"]
FUNCTION_SYNONYMS = {"average": "avg", "mean": "avg", "avrg": "avg", "maximum": "max", "minimum": "min",
                     "cnt": "count", "number": "count", "count_all": "count", "counts": "count",
                     "summ": "sum", "sums": "sum", "summation": "sum", "len": "length", "lcase": "lower",
                     "ucase": "upper", "substring": "substr", "isnull": "ifnull", "nvl": "ifnull"}
_INSERTABLE = [",", "FROM", "WHERE", "BY", ")", "(", "ON", "AND", "SELECT", "="]
_NUMBER_IN_TEXT = re.compile(r"[-+]?\d+(\.\d+)?")
_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
          "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def words_to_number(text: str) -> Optional[int]:
    """'thirty', 'twenty five', 'forty-two', 'one hundred' -> int (None if not a number phrase)."""
    words = text.lower().replace("-", " ").split()
    if not words:
        return None
    total, current = 0, 0
    for w in words:
        if w in _UNITS:
            current += _UNITS.index(w)
        elif w in _TENS and w:
            current += 10 * _TENS.index(w)
        elif w == "hundred":
            current = max(current, 1) * 100
        elif w == "thousand":
            total += max(current, 1) * 1000
            current = 0
        elif w == "and":
            continue
        else:
            return None
    return total + current


def _similarity(a: str, b: str) -> float:
    a, b = a.lower(), b.lower()
    base = difflib.SequenceMatcher(None, a, b).ratio()
    na, nb = a.replace("_", "").rstrip("s"), b.replace("_", "").rstrip("s")
    if na == nb:
        return max(base, 0.97)
    if na in nb or nb in na:
        base = max(base, 0.8)
    return base


def edit_distance(a: str, b: str) -> int:
    """Optimal-string-alignment distance (insert, delete, substitute, swap adjacent = 1 each)."""
    a, b = a.lower(), b.lower()
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def keyword_matches(word: str) -> List[str]:
    """Keywords within one edit (two for words of 7+ letters), closest first."""
    limit = 2 if len(word) >= 7 else 1
    scored = sorted((edit_distance(word, k), k) for k in KEYWORDS if abs(len(k) - len(word)) <= limit)
    return [k for d, k in scored if 0 < d <= limit]


def closest(word: str, options: Iterable[str], n: int = 3, cutoff: float = 0.55) -> List[str]:
    scored = sorted(((_similarity(word, o), o) for o in set(options)), reverse=True)
    return [o for s, o in scored[:n] if s >= cutoff]


def _edit_size(a: str, b: str) -> int:
    sm = difflib.SequenceMatcher(None, a, b)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


class SQLRepairEngine:
    def __init__(self, analyzer: Optional[SQLAnalyzer] = None, max_rounds: int = 5):
        self.analyzer = analyzer or SQLAnalyzer()
        self.max_rounds = max_rounds
        self._generators = {
            "SYNTAX_ERROR": self._fix_syntax,
            "UNKNOWN_TABLE": self._fix_unknown_table,
            "UNKNOWN_COLUMN": self._fix_unknown_column,
            "AMBIGUOUS_REFERENCE": self._fix_ambiguous,
            "DATATYPE_MISMATCH": self._fix_datatype,
            "SEMANTIC_ERROR": self._fix_semantic,
        }

    # ------------------------------------------------------------------ public API
    def repair(self, query: str, schema: Optional[DatabaseSchema] = None) -> RepairResult:
        original = query
        current = normalize_query(query)
        analysis = self.analyzer.analyze(current, schema)
        steps: List[RepairStep] = []
        notes: List[str] = []
        for _ in range(self.max_rounds):
            if not analysis.is_error:
                break
            issue = analysis.issues[0]
            if issue.error_class == "PERMISSION_DENIED":
                notes.append(f"{issue.message} Access-policy violations cannot be repaired automatically; "
                             "remove the restricted table/column or request access.")
                break
            best = self._best_candidate(current, schema, issue, analysis)
            if best is None:
                notes.append(f"No verified fix found for: {issue.message}")
                break
            new_sql, desc, new_analysis = best
            steps.append(RepairStep(issue.error_class, desc, current, new_sql))
            current, analysis = new_sql, new_analysis

        success = not analysis.is_error
        explanation = self._explain(steps, notes, success, analysis)
        return RepairResult(original, current if steps else (original if success else None), success,
                            None if success else analysis.error_class, steps, explanation)

    # ------------------------------------------------------------------ search
    def _best_candidate(self, sql: str, schema, issue: Issue, before: AnalysisResult):
        gen = self._generators.get(issue.error_class)
        if gen is None:
            return None
        candidates = self._dedupe(gen(sql, schema, issue))
        before_rank = self._rank(before)
        scored = []
        for cand, desc, pref in candidates:
            cand = normalize_query(cand)
            if not cand or cand == sql:
                continue
            res = self.analyzer.analyze(cand, schema)
            if any(i.message == issue.message for i in res.issues):
                continue                                  # targeted issue still present
            rank = self._rank(res)
            if rank < before_rank:
                continue                                  # introduced a more severe error
            scored.append(((0 if not res.is_error else 1, pref, -rank, len(res.issues), _edit_size(sql, cand)),
                           cand, desc, res))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0])
        _, cand, desc, res = scored[0]
        return cand, desc, res

    @staticmethod
    def _rank(analysis: AnalysisResult) -> int:
        """Higher is better: CORRECT > SEMANTIC > ... > SYNTAX."""
        if not analysis.is_error:
            return len(PRIORITY) + 1
        return PRIORITY.index(analysis.error_class)

    @staticmethod
    def _dedupe(cands: Iterable[Candidate]) -> List[Tuple[str, str, int]]:
        seen, out = set(), []
        for c in cands:
            sql, desc, pref = (c[0], c[1], c[2] if len(c) > 2 else 0)
            if sql and sql not in seen:
                seen.add(sql)
                out.append((sql, desc, pref))
        return out

    @staticmethod
    def _explain(steps: List[RepairStep], notes: List[str], success: bool, analysis: AnalysisResult) -> str:
        parts = [f"{i + 1}. [{s.error_class}] {s.description}" for i, s in enumerate(steps)]
        if success and steps:
            parts.append("The repaired query passes all checks.")
        elif success:
            parts.append("No errors detected; no changes needed.")
        else:
            if analysis.issues:
                parts.append(f"Remaining problem: {analysis.issues[0].message}")
        parts.extend(notes)
        return "\n".join(parts)

    # ------------------------------------------------------------------ SYNTAX_ERROR
    def _fix_syntax(self, sql: str, schema, issue: Issue) -> List[Candidate]:
        cands: List[Candidate] = []
        st = SQLText.try_parse(sql)
        if st is None:
            return self._fix_unterminated(sql)
        names = set()
        if schema is not None:
            names = {n.lower() for n in schema.table_names + schema.all_column_names()}

        # misspelled keywords (FORM -> FROM, WHRE -> WHERE, GROUP -> GROUP BY)
        for t in st.tokens:
            if t.type in NAME_TYPES and t.lower not in names and not st.is_function_name(t) and len(t.text) >= 2:
                for kw in keyword_matches(t.text)[:2]:
                    rep = kw
                    if kw in ("GROUP", "ORDER"):
                        rep = kw + " BY"
                    if t.text.upper() != kw:
                        cands.append((st.apply([st.replace_token(t, self._match_case(rep, t.text))]),
                                      f"Corrected the misspelled keyword '{t.text}' to {rep}", -1))
            if t.type in ("GROUP_BY", "ORDER_BY") or t.text.upper() in ("GROUP", "ORDER"):
                if t.text.upper() in ("GROUP", "ORDER"):
                    cands.append((st.apply([st.insert_after(t, " BY")]), f"Added the missing BY after {t.text.upper()}"))

        # glued tokens: countDISTINCT -> count(DISTINCT, LOCATIONFROM -> LOCATION) FROM
        upper_kw = set(KEYWORDS)
        for t in st.tokens:
            if t.type not in NAME_TYPES or t.lower in names or len(t.text) < 4:
                continue
            for i in range(1, len(t.text)):
                left, right = t.text[:i], t.text[i:]
                if right.upper() in upper_kw or left.upper() in upper_kw:
                    for glue in (" ", "(", ") ", ", "):
                        cands.append((st.apply([st.replace_token(t, left + glue + right)]),
                                      f"Separated '{left}' and '{right}'"))

        # clause order (e.g. WHERE after GROUP BY / ORDER BY)
        reordered = self._reorder_clauses(st)
        if reordered:
            cands.append((reordered, "Moved clauses into the standard order (SELECT, FROM, WHERE, GROUP BY, HAVING, ORDER BY, LIMIT)"))

        # bounded single-edit search: delete one keyword/punctuation token, or insert one token
        protected = {"NUMBER", "STRING", "IDENTIFIER", "VAR", "EQ", "NEQ", "GT", "GTE", "LT", "LTE", "STAR"}
        for t in st.tokens[:200]:
            if t.type in protected:
                continue
            cands.append((st.apply([st.delete_token(t)]), f"Removed the misplaced '{t.text}'", 1))
        positions = st.tokens[:150]
        for t in positions:
            for ins in _INSERTABLE:
                if ins == "," and t.type in ("SELECT", "FROM"):
                    continue
                text = (" " + ins) if ins not in (",", ")") else ins
                cands.append((st.apply([st.insert_after(t, text)]), f"Inserted the missing '{ins}' after '{t.text}'", 1))
        first = st.tokens[0] if st.tokens else None
        if first is not None and first.type != "SELECT":
            cands.append(("SELECT " + sql, "Added the missing SELECT keyword"))
        return cands

    @staticmethod
    def _match_case(keyword: str, like: str) -> str:
        return keyword.lower() if like.islower() else keyword

    @staticmethod
    def _fix_unterminated(sql: str) -> List[Candidate]:
        cands = []
        for q in ("'", '"'):
            if sql.count(q) % 2 == 1:
                start = sql.rfind(q)
                for m in re.finditer(r"(?=\s|\)|$)", sql[start + 1:]):
                    pos = start + 1 + m.start()
                    cands.append((sql[:pos] + q + sql[pos:], "Closed an unterminated string literal"))
                    if len(cands) > 12:
                        break
        return cands

    @staticmethod
    def _reorder_clauses(st: SQLText) -> Optional[str]:
        order = ["SELECT", "FROM", "WHERE", "GROUP_BY", "HAVING", "ORDER_BY", "LIMIT"]
        top = [t for t in st.tokens if t.depth == 0 and t.type in order]
        if any(t.type in ("UNION", "INTERSECT", "EXCEPT") and t.depth == 0 for t in st.tokens):
            return None
        if [t.type for t in top] == sorted((t.type for t in top), key=order.index):
            return None
        spans = []
        for i, t in enumerate(top):
            end = top[i + 1].start if i + 1 < len(top) else len(st.sql)
            spans.append((order.index(t.type), st.sql[t.start:end].strip()))
        spans.sort(key=lambda x: x[0])
        return " ".join(s for _, s in spans)

    # ------------------------------------------------------------------ UNKNOWN_TABLE
    def _fix_unknown_table(self, sql: str, schema, issue: Issue) -> List[Candidate]:
        if schema is None or not issue.token:
            return []
        st = SQLText.try_parse(sql)
        if st is None:
            return []
        bad = issue.token.strip('"`[]')
        occurrences = [t for t in st.tokens if t.type in NAME_TYPES and t.lower == bad.lower()]
        options = closest(bad, schema.table_names, n=3, cutoff=0.5)
        # tables that contain the columns used through this table/alias
        used_cols = self._columns_used_with(st, bad)
        known = [schema.table(t.text) for t, _ in st.table_refs(schema)]
        used_cols += [c for c in self._unqualified_names(st, schema) if not any(k.column(c) for k in known)]
        if used_cols:
            cover = sorted(schema.tables.values(),
                           key=lambda t: -sum(1 for c in used_cols if t.column(c)))
            if cover and sum(1 for c in used_cols if cover[0].column(c)):
                options.append(cover[0].name)
        cands = []
        for opt in options:
            edits = [st.replace_token(t, opt) for t in occurrences]
            cands.append((st.apply(edits), f"Replaced unknown table '{bad}' with '{opt}'"))
        return cands

    @staticmethod
    def _unqualified_names(st: SQLText, schema) -> List[str]:
        out = []
        for t in st.tokens:
            if t.type not in NAME_TYPES or st.is_function_name(t) or schema.has_table(t.text):
                continue
            p, n = st.prev(t), st.next(t)
            if (p is not None and p.type in ("DOT", "FROM", "JOIN", "ALIAS")) or (n is not None and n.type == "DOT"):
                continue
            out.append(t.text)
        return out

    @staticmethod
    def _columns_used_with(st: SQLText, table_or_alias: str) -> List[str]:
        aliases = {table_or_alias.lower()}
        for t in st.tokens:
            if t.type in NAME_TYPES and t.lower == table_or_alias.lower():
                n = st.next(t)
                if n is not None and n.type == "ALIAS":
                    n = st.next(n)
                if n is not None and n.type in NAME_TYPES:
                    aliases.add(n.lower)
        cols = []
        for t in st.tokens:
            if t.type == "DOT":
                p, n = st.prev(t), st.next(t)
                if p is not None and n is not None and p.lower in aliases:
                    cols.append(n.text)
        return cols

    # ------------------------------------------------------------------ UNKNOWN_COLUMN
    def _fix_unknown_column(self, sql: str, schema, issue: Issue) -> List[Candidate]:
        if schema is None or not issue.token:
            return []
        st = SQLText.try_parse(sql)
        if st is None:
            return []
        token = issue.token
        qual, _, col = token.rpartition(".")
        col = col.strip('"`[]')
        amap = st.alias_map(schema)
        from_tables = [schema.table(t.text) for t, _ in st.table_refs(schema)]
        cands = []
        targets = []
        for t in st.tokens:
            if t.type in NAME_TYPES and t.lower == col.lower():
                p = st.prev(t)
                q = st.prev(p) if (p is not None and p.type == "DOT") else None
                if qual and (q is None or q.lower != qual.lower()):
                    continue
                if not qual and q is not None:
                    continue
                targets.append((q, t))
        if not targets:
            return []
        if qual and qual.lower() in amap:
            table = schema.table(amap[qual.lower()])
            pool = table.column_names
        elif qual:
            # undefined qualifier: point it at a table that has the column, or at a similar alias
            pool = []
            for alias in closest(qual, list(amap.keys()), n=2, cutoff=0.3):
                cands.append((st.apply([st.replace_token(q, alias) for q, _ in targets if q is not None]),
                              f"Replaced undefined qualifier '{qual}' with '{alias}'"))
        else:
            pool = [c for t in from_tables if t for c in t.column_names]
        for opt in closest(col, pool, n=3, cutoff=0.6):
            edits = [st.replace_token(t, opt) for _, t in targets]
            cands.append((st.apply(edits), f"Replaced unknown column '{token}' with '{opt}'"))
        # join key: in "A.bad = B.col", use the foreign-key partner of B.col in A's table
        if qual and qual.lower() in amap:
            table = schema.table(amap[qual.lower()])
            for q, t in targets:
                op = st.next(t)
                other_q = st.next(op) if op is not None and op.type == "EQ" else None
                if op is not None and op.type == "EQ" and other_q is not None and st.next(other_q) is not None \
                        and st.next(other_q).type == "DOT":
                    other_col = st.next(st.next(other_q))
                else:
                    prev_op = st.prev(q) if q is not None else None
                    if prev_op is None or prev_op.type != "EQ":
                        continue
                    other_col = st.prev(prev_op)
                    other_q = st.prev(st.prev(other_col)) if st.prev(other_col) is not None and st.prev(other_col).type == "DOT" else None
                if other_q is None or other_col is None or other_q.lower not in amap:
                    continue
                other = schema.table(amap[other_q.lower])
                partners = [tc for c, tt, tc in other.foreign_keys
                            if c.lower() == other_col.lower and tt.lower() == table.name.lower()]
                partners += [c for c, tt, tc in table.foreign_keys
                             if tt.lower() == other.name.lower() and tc.lower() == other_col.lower]
                for p in dict.fromkeys(partners):
                    real = table.column(p)
                    if real is not None:
                        cands.append((st.apply([st.replace_token(t, real.name)]),
                                      f"Replaced unknown join column '{token}' with the foreign-key partner "
                                      f"'{qual}.{real.name}'", -1))
        # the column exists, but in another joined table: re-qualify
        if qual:
            for t_tok, alias in st.table_refs(schema):
                tab = schema.table(t_tok.text)
                a = alias.text if alias is not None else t_tok.text
                if tab.column(col) and a.lower() != qual.lower():
                    edits = [st.replace_token(q, a) for q, _ in targets if q is not None]
                    cands.append((st.apply(edits), f"'{col}' belongs to {tab.name}; qualified it with '{a}'", 1))
        return cands

    # ------------------------------------------------------------------ AMBIGUOUS_REFERENCE
    def _fix_ambiguous(self, sql: str, schema, issue: Issue) -> List[Candidate]:
        st = SQLText.try_parse(sql)
        if st is None or schema is None:
            return []
        refs = st.table_refs(schema)
        cands = []
        token = (issue.token or "").split(".")[-1]
        if "used for more than one table" in issue.message or (issue.token or "").count(".") >= 1:
            cands.extend(self._split_duplicate_alias(st, schema, refs))
        if token:
            owners = [(t, a) for t, a in refs if schema.table(t.text).column(token)]
            targets = [t for t in st.tokens if t.type in NAME_TYPES and t.lower == token.lower()
                       and not (st.prev(t) is not None and st.prev(t).type == "DOT")
                       and not (st.next(t) is not None and st.next(t).type == "DOT")]
            for t_tok, alias in owners:
                a = alias.text if alias is not None else t_tok.text
                for i, target in enumerate(targets):
                    edits = [st.insert_before(target, f"{a}.")]
                    cands.append((st.apply(edits), f"Qualified the ambiguous column '{token}' as {a}.{token}"))
                if targets:
                    edits = [st.insert_before(target, f"{a}.") for target in targets]
                    cands.append((st.apply(edits), f"Qualified the ambiguous column '{token}' as {a}.{token}"))
        return cands

    @staticmethod
    def _split_duplicate_alias(st: SQLText, schema, refs) -> List[Candidate]:
        seen = {}
        cands = []
        for t_tok, alias in refs:
            key = (alias.lower if alias is not None else t_tok.lower)
            if key not in seen:
                seen[key] = (t_tok, alias)
                continue
            first_tab = schema.table(seen[key][0].text)
            second_tab = schema.table(t_tok.text)
            used = {a.lower if a is not None else t.lower for t, a in refs}
            new = next(f"T{i}" for i in range(1, 20) if f"t{i}" not in used)
            edits = [st.replace_token(alias, new)] if alias is not None else [st.insert_after(t_tok, f" AS {new}")]
            # re-point qualified references whose column only exists in the second table,
            # and the right-hand side of self-comparisons such as T1.a = T1.b
            for t in st.tokens:
                if t.type == "DOT":
                    q, c = st.prev(t), st.next(t)
                    if q is None or c is None or q.lower != key or q is alias:
                        continue
                    in_first = first_tab.column(c.text) is not None
                    in_second = second_tab.column(c.text) is not None
                    prev_op = st.prev(q)
                    rhs = prev_op is not None and prev_op.type in ("EQ",)
                    if in_second and (not in_first or rhs):
                        edits.append(st.replace_token(q, new))
            try:
                cands.append((st.apply(edits), f"Gave {t_tok.text} its own alias '{new}' (the alias '{key}' was used twice)"))
            except ValueError:
                pass
        return cands

    # ------------------------------------------------------------------ DATATYPE_MISMATCH
    def _fix_datatype(self, sql: str, schema, issue: Issue) -> List[Candidate]:
        tree = self._parse(sql)
        if tree is None:
            return []
        cands = []
        msg = issue.message
        if "compared with the number" in msg:
            for lit in tree.find_all(exp.Literal):
                if not lit.is_string and self._compared_with_text_column(lit, schema, tree):
                    new = tree.copy()
                    target = next(n for n in new.find_all(exp.Literal) if n.sql() == lit.sql()
                                  and n.parent.sql() == lit.parent.sql())
                    target.replace(exp.Literal.string(lit.this))
                    cands.append((new.sql(dialect="sqlite"), f"Quoted {lit.sql()} because it is compared with a text column"))
        if "compared with the text value" in msg:
            for lit in tree.find_all(exp.Literal):
                if lit.is_string:
                    m = _NUMBER_IN_TEXT.search(lit.this)
                    number = m.group(0) if m else None
                    if number is None and words_to_number(lit.this) is not None:
                        number = str(words_to_number(lit.this))
                    if number is not None:
                        new = tree.copy()
                        target = next(n for n in new.find_all(exp.Literal) if n.is_string and n.this == lit.this)
                        target.replace(exp.Literal.number(number))
                        cands.append((new.sql(dialect="sqlite"), f"Replaced '{lit.this}' with the number {number}"))
        if "is applied to the text column" in msg:
            for agg in tree.find_all(exp.Sum, exp.Avg):
                new = tree.copy()
                target = next(n for n in new.find_all(type(agg)) if n.sql() == agg.sql())
                arg = target.this
                target.set("this", exp.Cast(this=arg.copy(), to=exp.DataType.build("REAL")))
                cands.append((new.sql(dialect="sqlite"),
                              f"Cast {arg.sql()} to REAL inside {agg.key.upper()}() (assumes the text values are numeric)"))
        return cands

    @staticmethod
    def _compared_with_text_column(lit: exp.Literal, schema, tree) -> bool:
        parent = lit.parent
        if not isinstance(parent, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In, exp.Between)):
            return False
        cols = [c for c in parent.find_all(exp.Column)]
        if schema is None:
            return False
        for c in cols:
            owners = schema.tables_with_column(c.name)
            if owners and all(schema.column_type(o, c.name) == TEXT for o in owners):
                return True
        return False

    # ------------------------------------------------------------------ SEMANTIC_ERROR
    def _fix_semantic(self, sql: str, schema, issue: Issue) -> List[Candidate]:
        msg = issue.message
        tree = self._parse(sql)
        cands: List[Candidate] = []
        if "NULL' is never true" in msg and tree is not None:
            new = tree.copy()
            for n in list(new.find_all(exp.EQ, exp.NEQ)):
                other = n.left if isinstance(n.right, exp.Null) else n.right if isinstance(n.left, exp.Null) else None
                if other is None:
                    continue
                repl = exp.Is(this=other.copy(), expression=exp.Null())
                n.replace(exp.Not(this=repl) if isinstance(n, exp.NEQ) else repl)
            cands.append((new.sql(dialect="sqlite"), "Replaced '= NULL' / '<> NULL' with IS NULL / IS NOT NULL"))
        if msg.lower().startswith("misuse of aggregate") and tree is not None:
            cands.extend(self._fix_aggregate_in_where(tree))
        if ("must appear in GROUP BY" in msg or "not in a GROUP BY" in msg or "neither grouped" in msg) and tree is not None:
            cands.extend(self._fix_grouping(tree, issue))
        if "HAVING is used without GROUP BY" in msg and tree is not None:
            new = tree.copy()
            for sel in new.find_all(exp.Select):
                having = sel.args.get("having")
                if having is not None and sel.args.get("group") is None:
                    sel.set("having", None)
                    sel.where(having.this.copy(), copy=False)
            cands.append((new.sql(dialect="sqlite"), "Turned HAVING (no aggregate) into WHERE"))
        if "Cartesian product" in msg:
            cands.extend(self._fix_join_condition(sql, schema, issue))
        if msg.startswith("Function '") or "no such function" in msg.lower():
            cands.extend(self._fix_function(sql, issue))
        if "wrong number of arguments" in msg.lower() and tree is not None:
            new = tree.copy()
            for f in new.find_all(exp.Func):
                if f.expressions and f.this is not None:
                    f.set("expressions", [])
            cands.append((new.sql(dialect="sqlite"), "Kept only the first argument of the aggregate"))
        if ("sub-select returns" in msg or "row value misused" in msg) and tree is not None:
            new = tree.copy()
            for sub in new.find_all(exp.Subquery):
                sel = sub.this
                if isinstance(sel, exp.Select) and len(sel.expressions) > 1:
                    sel.set("expressions", sel.expressions[:1])
            cands.append((new.sql(dialect="sqlite"), "Reduced the subquery to the single column it must return"))
        if "same number of result columns" in msg and tree is not None:
            cands.extend(self._fix_set_arity(tree))
        if "ORDER BY term out of range" in msg and tree is not None:
            cands.extend(self._fix_order_position(tree))
        if ("non-aggregate query" in msg or msg.lower().startswith("misuse of aggregate")) and tree is not None:
            cands.extend(self._add_group_by(tree))
        return cands

    @staticmethod
    def _fix_order_position(tree: exp.Expression) -> List[Candidate]:
        cands = []
        for sel in tree.find_all(exp.Select):
            order = sel.args.get("order")
            if order is None:
                continue
            n = len(sel.expressions)
            for o in order.expressions:
                if isinstance(o.this, exp.Literal) and not o.this.is_string and int(float(o.this.this)) > n:
                    for k, proj in enumerate(sel.expressions, 1):
                        new = tree.copy()
                        target = next(x for x in new.find_all(exp.Ordered) if x.sql() == o.sql())
                        target.set("this", (proj.this if isinstance(proj, exp.Alias) else proj).copy())
                        cands.append((new.sql(dialect="sqlite"),
                                      f"ORDER BY {o.this.sql()} is out of range; ordered by {proj.sql()} instead"))
        return cands

    @staticmethod
    def _add_group_by(tree: exp.Expression) -> List[Candidate]:
        cands = []
        for sel in tree.find_all(exp.Select):
            if sel.args.get("group") is not None:
                continue
            bare = []
            for p in sel.expressions:
                node = p.this if isinstance(p, exp.Alias) else p
                if isinstance(node, exp.Column) and not isinstance(node.this, exp.Star):
                    bare.append(node)
            if not bare:
                continue
            options = [[b] for b in bare] + ([bare] if len(bare) > 1 else [])
            for cols in options:
                new = tree.copy()
                nsel = next(s for s in new.find_all(exp.Select) if s.sql() == sel.sql())
                nsel.group_by(*[c.copy() for c in cols], copy=False)
                cands.append((new.sql(dialect="sqlite"),
                              "Added the missing GROUP BY " + ", ".join(c.sql() for c in cols)))
        return cands

    @staticmethod
    def _parse(sql: str) -> Optional[exp.Expression]:
        try:
            return sqlglot.parse_one(sql, read="sqlite")
        except (SqlglotError, ValueError):
            return None

    @staticmethod
    def _fix_aggregate_in_where(tree: exp.Expression) -> List[Candidate]:
        cands = []
        for sel in tree.find_all(exp.Select):
            where = sel.args.get("where")
            if where is None:
                continue
            conjuncts = list(where.this.flatten()) if isinstance(where.this, exp.And) else [where.this]
            bad = [c for c in conjuncts if any(isinstance(n, exp.AggFunc) for n in c.find_all(exp.AggFunc)
                                               if n.find_ancestor(exp.Select) is sel)]
            if not bad:
                continue
            keep = [c for c in conjuncts if c not in bad]
            from_ = sel.args.get("from_")
            single = from_ is not None and isinstance(from_.this, exp.Table) and not sel.args.get("joins")
            # (a) compare against a scalar subquery: x > avg(x)  ->  x > (SELECT avg(x) FROM t)
            if single:
                new = tree.copy()
                nsel = next(s for s in new.find_all(exp.Select) if s.sql() == sel.sql())
                for agg in list(nsel.args["where"].find_all(exp.AggFunc)):
                    sub = exp.select(agg.copy()).from_(from_.this.copy())
                    agg.replace(exp.Subquery(this=sub))
                cands.append((new.sql(dialect="sqlite"), "Replaced the aggregate in WHERE with a scalar subquery"))
            # (b) move aggregate conditions to HAVING (requires grouping)
            new = tree.copy()
            nsel = next(s for s in new.find_all(exp.Select) if s.sql() == sel.sql())
            nsel.set("where", exp.Where(this=exp.and_(*[k.copy() for k in keep])) if keep else None)
            nsel.having(exp.and_(*[b.copy() for b in bad]), copy=False)
            cands.append((new.sql(dialect="sqlite"), "Moved the aggregate condition from WHERE to HAVING"))
        return cands

    @staticmethod
    def _fix_grouping(tree: exp.Expression, issue: Issue) -> List[Candidate]:
        cands = []
        col_sql = issue.token
        for sel in tree.find_all(exp.Select):
            group = sel.args.get("group")
            bare = [c for p in sel.expressions for c in p.find_all(exp.Column)
                    if not c.find_ancestor(exp.AggFunc) and c.find_ancestor(exp.Select) is sel]
            if col_sql and not any(c.sql() == col_sql for c in bare) and not (
                    sel.args.get("having") and any(c.sql() == col_sql for c in sel.args["having"].find_all(exp.Column))):
                continue
            new = tree.copy()
            nsel = next(s for s in new.find_all(exp.Select) if s.sql() == sel.sql())
            existing = {g.sql().lower() for g in (group.expressions if group else [])}
            to_add = []
            for c in bare:
                if c.sql().lower() not in existing and c.sql().lower() not in {t.sql().lower() for t in to_add}:
                    to_add.append(c.copy())
            if col_sql and col_sql.lower() not in existing and col_sql.lower() not in {t.sql().lower() for t in to_add}:
                to_add.append(sqlglot.parse_one(col_sql, read="sqlite"))
            if to_add:
                nsel.group_by(*to_add, copy=False)
                cands.append((new.sql(dialect="sqlite"),
                              "Added " + ", ".join(t.sql() for t in to_add) + " to GROUP BY"))
            # alternative: aggregate the offending column
            if col_sql:
                new2 = tree.copy()
                nsel2 = next(s for s in new2.find_all(exp.Select) if s.sql() == sel.sql())
                for c in list(nsel2.find_all(exp.Column)):
                    if c.sql() == col_sql and not c.find_ancestor(exp.AggFunc) and c.find_ancestor(exp.Select) is nsel2 \
                            and not c.find_ancestor(exp.Group) and not c.find_ancestor(exp.Order):
                        c.replace(exp.Max(this=c.copy()))
                cands.append((new2.sql(dialect="sqlite"), f"Wrapped {col_sql} in MAX() so it is aggregated", 1))
        return cands

    def _fix_join_condition(self, sql: str, schema, issue: Issue) -> List[Candidate]:
        st = SQLText.try_parse(sql)
        if st is None or schema is None or not issue.token:
            return []
        refs = st.table_refs(schema)
        target = next(((t, a) for t, a in refs if (a.text if a is not None else t.text).lower() == issue.token.lower()), None)
        if target is None:
            return []
        t_tok, alias = target
        me = schema.table(t_tok.text)
        my_alias = alias.text if alias is not None else t_tok.text
        conds = []
        for o_tok, o_alias in refs:
            if o_tok is t_tok:
                continue
            other = schema.table(o_tok.text)
            oa = o_alias.text if o_alias is not None else o_tok.text
            for col, tt, tc in me.foreign_keys:
                if tt.lower() == other.name.lower():
                    conds.append((f"{my_alias}.{col} = {oa}.{tc}", 0))
            for col, tt, tc in other.foreign_keys:
                if tt.lower() == me.name.lower():
                    conds.append((f"{oa}.{col} = {my_alias}.{tc}", 0))
            shared = [c.name for c in me.columns if other.column(c.name)
                      and c.name.lower().endswith("id") and c.name.lower() != "id"]
            conds.extend((f"{my_alias}.{c} = {oa}.{other.column(c).name}", 1) for c in shared)
        anchor = alias if alias is not None else t_tok
        cands = []
        for cond, pref in dict.fromkeys(conds):
            nxt = st.next(anchor)
            if nxt is not None and nxt.type == "ON":
                end = st.clause_end(nxt, stop_types=CLAUSE_TYPES | {"JOIN", "LEFT", "INNER"})
                cands.append((st.apply([st.insert_after(end, f" AND {cond}")]), f"Added the join condition {cond}", pref))
            else:
                cands.append((st.apply([st.insert_after(anchor, f" ON {cond}")]), f"Added the join condition ON {cond}", pref))
        return cands

    @staticmethod
    def _fix_function(sql: str, issue: Issue) -> List[Candidate]:
        st = SQLText.try_parse(sql)
        if st is None or not issue.token:
            return []
        bad = issue.token.lower()
        options = [FUNCTION_SYNONYMS[bad]] if bad in FUNCTION_SYNONYMS else closest(bad, FUNCTIONS, n=2, cutoff=0.5)
        cands = []
        for opt in options:
            edits = [st.replace_token(t, opt.upper() if t.text.isupper() else opt)
                     for t in st.tokens if t.type != "STRING" and t.lower == bad
                     and st.next(t) is not None and st.next(t).type == "L_PAREN"]
            if edits:
                cands.append((st.apply(edits), f"Replaced the unknown function {issue.token}() with {opt}()"))
        return cands

    @staticmethod
    def _fix_set_arity(tree: exp.Expression) -> List[Candidate]:
        cands = []
        for setop in tree.find_all(exp.Union, exp.Intersect, exp.Except):
            left, right = setop.left, setop.right
            if not isinstance(left, exp.Select) or not isinstance(right, exp.Select):
                continue
            n = min(len(left.expressions), len(right.expressions))
            for side in ("left", "right"):
                new = tree.copy()
                nset = next(s for s in new.find_all(type(setop)) if s.sql() == setop.sql())
                sel = nset.left if side == "left" else nset.right
                if len(sel.expressions) > n:
                    names = {e.alias_or_name.lower() for e in (nset.right if side == "left" else nset.left).expressions}
                    keep = [e for e in sel.expressions if e.alias_or_name.lower() in names][:n] or sel.expressions[-n:]
                    sel.set("expressions", keep)
                    cands.append((new.sql(dialect="sqlite"),
                                  f"Dropped extra columns so both sides of {setop.key.upper()} return {n} column(s)"))
        return cands
