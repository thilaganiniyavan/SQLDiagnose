# mutator.py
# Injects realistic errors into correct SQL queries.
#
# Every mutation edits exact character spans of the source query (see sql_text.py), and
# every candidate is re-checked by the SQLAnalyzer before it is accepted: a sample's label
# is the class the analyzer confirms, never merely the class the mutation intended.

import random
import re
from typing import Callable, Dict, List, Optional, Tuple

from analysis.schema import NUMBER, TEXT, DatabaseSchema
from .sql_text import AGGREGATES, CLAUSE_TYPES, COMPARISON_TYPES, NAME_TYPES, SQLText, Tok

MutationResult = Optional[Tuple[str, str]]         # (mutated sql, human readable description)
Mutation = Callable[[SQLText, DatabaseSchema, random.Random, "SQLMutator"], MutationResult]

_KEYBOARD = {
    "a": "sqwz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wsdr", "f": "drtgvc", "g": "ftyhbv",
    "h": "gyujnb", "i": "ujko", "j": "huikmn", "k": "jiolm", "l": "kop", "m": "njk", "n": "bhjm",
    "o": "iklp", "p": "ol", "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy", "u": "yhji",
    "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tghu", "z": "asx",
}
_WORDS = ["high", "low", "young", "old", "unknown", "none", "many", "ten", "twenty", "large", "small",
          "recent", "yes", "no", "N/A", "abc", "top", "first", "last", "big", "cheap", "expensive"]
_AFFIXES = [("tbl_", ""), ("", "_table"), ("", "_info"), ("", "_data"), ("", "_list"), ("", "s_tbl")]
_FUNC_TYPOS = {
    "count": ["cnt", "counts", "coun", "count_all", "number"],
    "avg": ["average", "mean", "avrg", "avgs"],
    "max": ["maximum", "mx", "maxi"],
    "min": ["minimum", "mn", "mini"],
    "sum": ["summ", "sums", "summation"],
}
_KEYWORD_TARGETS = {"SELECT", "FROM", "WHERE", "GROUP_BY", "ORDER_BY", "HAVING", "JOIN", "LIMIT"}


# ---------------------------------------------------------------------- word-level helpers
def typo(word: str, rng: random.Random) -> str:
    if len(word) < 3:
        return word + rng.choice("sx_")
    for _ in range(10):
        i = rng.randrange(1, len(word))
        op = rng.choice(["delete", "swap", "double", "neighbour"])
        if op == "delete":
            w = word[:i] + word[i + 1:]
        elif op == "swap" and i < len(word) - 1:
            w = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        elif op == "double":
            w = word[:i] + word[i] + word[i:]
        else:
            ch = word[i].lower()
            if ch not in _KEYBOARD:
                continue
            rep = rng.choice(_KEYBOARD[ch])
            w = word[:i] + (rep.upper() if word[i].isupper() else rep) + word[i + 1:]
        if w != word and w.lower() != word.lower():
            return w
    return word + "s"


def toggle_plural(word: str) -> str:
    low = word.lower()
    if low.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if low.endswith("ses") or low.endswith("xes"):
        return word[:-2]
    if low.endswith("s") and not low.endswith("ss"):
        return word[:-1]
    if low.endswith("y") and len(word) > 2 and low[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def column_variant(name: str, table: str, rng: random.Random) -> str:
    choices = [
        lambda: typo(name, rng),
        lambda: toggle_plural(name),
        lambda: name.replace("_", "") if "_" in name else f"{table.lower()}_{name}",
        lambda: name.split("_")[-1] + "_" + name.split("_")[0] if "_" in name else name + "_name",
        lambda: {"id": "identifier", "name": "full_name", "age": "years", "date": "day"}.get(name.lower(), typo(name, rng)),
    ]
    return rng.choice(choices)()


def _quote_like(tok: Tok, sql: str, value: str) -> str:
    q = sql[tok.start]
    if q in "'\"":
        return q + value.replace(q, q + q) + q
    return "'" + value.replace("'", "''") + "'"


# ---------------------------------------------------------------------- mutations: SYNTAX_ERROR
def syn_drop_comma(st: SQLText, schema, rng, m) -> MutationResult:
    commas = [t for t in st.of_type("COMMA")]
    if not commas:
        return None
    t = rng.choice(commas)
    return st.apply([st.delete_token(t)]), "Removed a comma between list items"


def syn_drop_keyword(st: SQLText, schema, rng, m) -> MutationResult:
    kws = [t for t in st.tokens if t.type in ("FROM", "WHERE", "ON", "SELECT", "HAVING")]
    if not kws:
        return None
    t = rng.choice(kws)
    return st.apply([st.delete_token(t)]), f"Removed the {t.text.upper()} keyword"


def syn_keyword_typo(st: SQLText, schema, rng, m) -> MutationResult:
    kws = [t for t in st.tokens if t.type in _KEYWORD_TARGETS]
    if not kws:
        return None
    t = rng.choice(kws)
    words = t.text.split()
    k = rng.randrange(len(words))
    words[k] = typo(words[k], rng)
    return st.apply([st.replace_token(t, " ".join(words))]), f"Misspelled the keyword {t.text.upper()}"


def syn_split_by(st: SQLText, schema, rng, m) -> MutationResult:
    kws = st.of_type("GROUP_BY", "ORDER_BY")
    if not kws:
        return None
    t = rng.choice(kws)
    return st.apply([st.replace_token(t, t.text.split()[0])]), f"Dropped BY from {t.text.upper()}"


def syn_parenthesis(st: SQLText, schema, rng, m) -> MutationResult:
    parens = st.of_type("L_PAREN", "R_PAREN")
    if parens and rng.random() < 0.7:
        t = rng.choice(parens)
        return st.apply([st.delete_token(t)]), "Removed a parenthesis, leaving them unbalanced"
    names = [t for t in st.tokens if t.type in NAME_TYPES]
    if not names:
        return None
    t = rng.choice(names)
    return st.apply([st.insert_before(t, "(")]), "Inserted an unmatched opening parenthesis"


def syn_unclosed_quote(st: SQLText, schema, rng, m) -> MutationResult:
    strings = [t for t in st.tokens if t.type == "STRING"]
    if not strings:
        return None
    t = rng.choice(strings)
    return st.apply([(t.end - 1, t.end, "")]), "Removed the closing quote of a string literal"


def syn_dangling_operator(st: SQLText, schema, rng, m) -> MutationResult:
    where = st.of_type("WHERE", "HAVING", "ON")
    comps = st.of_type(*COMPARISON_TYPES)
    options = []
    if where:
        w = rng.choice(where)
        options.append(([st.insert_after(w, " " + rng.choice(["AND", "OR"]))], f"Put a dangling AND/OR right after {w.text.upper()}"))
    if comps:
        c = rng.choice(comps)
        nxt = st.next(c)
        if nxt is not None and nxt.type in ("NUMBER", "STRING", "IDENTIFIER", "VAR"):
            options.append(([st.delete_token(nxt)], "Removed the right-hand operand of a comparison"))
        options.append(([st.delete_token(c)], "Removed a comparison operator"))
    if not options:
        return None
    edits, desc = rng.choice(options)
    return st.apply(edits), desc


def syn_trailing_comma(st: SQLText, schema, rng, m) -> MutationResult:
    froms = st.of_type("FROM")
    if not froms:
        return None
    f = froms[0]
    prev = st.prev(f)
    if prev is None:
        return None
    return st.apply([st.insert_after(prev, ",")]), "Left a trailing comma before FROM"


def syn_clause_order(st: SQLText, schema, rng, m) -> MutationResult:
    wheres = [t for t in st.of_type("WHERE") if t.depth == 0]
    if not wheres:
        return None
    w = wheres[0]
    end = st.clause_end(w)
    later = [t for t in st.tokens[end.index + 1:] if t.depth == 0 and t.type in ("GROUP_BY", "ORDER_BY")]
    if not later:
        return None
    target = st.clause_end(later[0])
    clause = st.sql[w.start:end.end]
    start, stop = w.start, end.end
    while stop < len(st.sql) and st.sql[stop] == " ":
        stop += 1
    return st.apply([(start, stop, ""), (target.end, target.end, " " + clause)]), \
        f"Moved the WHERE clause after {later[0].text.upper()}"


def syn_duplicate_keyword(st: SQLText, schema, rng, m) -> MutationResult:
    kws = [t for t in st.tokens if t.type in ("SELECT", "FROM", "WHERE")]
    if not kws:
        return None
    t = rng.choice(kws)
    return st.apply([st.insert_after(t, " " + t.text)]), f"Repeated the keyword {t.text.upper()}"


# ---------------------------------------------------------------------- mutations: UNKNOWN_TABLE
def tab_rename(st: SQLText, schema, rng, m) -> MutationResult:
    refs = st.table_refs(schema)
    if not refs:
        return None
    tok, _ = rng.choice(refs)
    r = rng.random()
    if r < 0.35:
        new, how = typo(tok.text, rng), "misspelled"
    elif r < 0.7:
        new, how = toggle_plural(tok.text), "singular/plural confusion in"
    elif r < 0.9 and m.foreign_tables:
        new, how = rng.choice(m.foreign_tables), "table from a different database instead of"
    else:
        pre, suf = rng.choice(_AFFIXES)
        new, how = f"{pre}{tok.text}{suf}", "invented variant of"
    if schema.has_table(new):
        return None
    # all references of this table name (not aliases) are renamed consistently
    edits = [st.replace_token(t, new) for t in st.tokens if t.type in NAME_TYPES and t.lower == tok.lower
             and (st.prev(t) is None or st.prev(t).type in ("FROM", "JOIN", "COMMA")
                  or (st.next(t) is not None and st.next(t).type == "DOT"))]
    return st.apply(edits), f"Table '{new}' ({how} '{tok.text}')"


# ---------------------------------------------------------------------- mutations: UNKNOWN_COLUMN
def col_rename(st: SQLText, schema, rng, m) -> MutationResult:
    refs = st.column_refs(schema)
    if not refs:
        return None
    qual, tok, table = rng.choice(refs)
    r = rng.random()
    if r < 0.6:
        new, how = column_variant(tok.text, table, rng), "misspelled/variant of"
    elif r < 0.85:
        others = [c for t in schema.tables.values() if t.name != table for c in t.column_names
                  if not schema.table(table).column(c)]
        if not others:
            return None
        new, how = rng.choice(others), "column of another table instead of"
    else:
        if not m.foreign_columns:
            return None
        new, how = rng.choice(m.foreign_columns), "column from a different database instead of"
    if schema.table(table).column(new):
        return None
    return st.apply([st.replace_token(tok, new)]), f"Column '{new}' ({how} '{tok.text}')"


# ---------------------------------------------------------------------- mutations: DATATYPE_MISMATCH
def _comparisons(st: SQLText, schema) -> List[Tuple[Tok, Tok, str, str]]:
    """(column token, value token, resolved table, column type) for `col <op> literal` patterns."""
    out = []
    for q, col, table in st.column_refs(schema):
        op = st.next(col)
        if op is None or op.type not in COMPARISON_TYPES:
            continue
        val = st.next(op)
        if val is None:
            continue
        ctype = schema.column_type(table, col.text)
        out.append((col, val, table, ctype))
    return out


def dt_literal(st: SQLText, schema, rng, m) -> MutationResult:
    options = []
    strings = {t.index for t in st.string_literals(schema)}
    for col, val, table, ctype in _comparisons(st, schema):
        if ctype == NUMBER and val.type == "NUMBER":
            word = m.text_value(rng).replace("'", "''")
            options.append(([st.replace_token(val, f"'{word}'")], f"Compared numeric column '{col.text}' with the text '{word}'"))
        elif ctype == TEXT and val.index in strings:
            num = str(rng.choice([0, 1, 5, 10, 42, 100, 2000, 2010, rng.randint(2, 999)]))
            options.append(([st.replace_token(val, num)], f"Compared text column '{col.text}' with the number {num}"))
    if not options:
        return None
    edits, desc = rng.choice(options)
    return st.apply(edits), desc


def dt_aggregate(st: SQLText, schema, rng, m) -> MutationResult:
    options = []
    for q, col, table in st.column_refs(schema):
        # pattern: sum|avg ( [q .] col )
        head = st.prev(q) if q is not None else st.prev(col)
        func = st.prev(head) if head is not None else None
        if head is None or head.type != "L_PAREN" or func is None or func.lower not in ("sum", "avg"):
            continue
        texts = [c.name for c in schema.table(table).columns if c.type == TEXT]
        if texts:
            new = rng.choice(texts)
            options.append(([st.replace_token(col, new)], f"Applied {func.text.upper()}() to the text column '{new}'"))
    if not options:
        # turn count(*) / max(x) into sum/avg over a text column
        for f in st.tokens:
            if f.type == "VAR" and f.lower in ("max", "min", "count") and st.is_function_name(f):
                refs = st.table_refs(schema)
                if not refs:
                    break
                tab = schema.table(refs[0][0].text)
                texts = [c.name for c in tab.columns if c.type == TEXT]
                close = next((t for t in st.tokens[f.index + 1:] if t.type == "R_PAREN" and t.depth == f.depth), None)
                if texts and close is not None:
                    new = rng.choice(texts)
                    fn = rng.choice(["SUM", "AVG"])
                    options.append(([(f.start, close.end, f"{fn}({new})")], f"Applied {fn}() to the text column '{new}'"))
                break
    if not options:
        return None
    edits, desc = rng.choice(options)
    return st.apply(edits), desc


def dt_predicate(st: SQLText, schema, rng, m) -> MutationResult:
    refs = st.table_refs(schema)
    if not refs:
        return None
    table_tok, alias = rng.choice(refs)
    tab = schema.table(table_tok.text)
    nums = [c.name for c in tab.columns if c.type == NUMBER]
    texts = [c.name for c in tab.columns if c.type == TEXT]
    qual = (alias.text if alias is not None else table_tok.text) + "." if len(refs) > 1 else ""
    if nums and (not texts or rng.random() < 0.6):
        value = m.text_value(rng).replace("'", "''")
        pred = f"{qual}{rng.choice(nums)} {rng.choice(['=', '>', '<', '!='])} '{value}'"
    elif texts:
        pred = f"{qual}{rng.choice(texts)} = {rng.randint(1, 500)}"
    else:
        return None
    wheres = [t for t in st.of_type("WHERE") if t.depth == 0]
    if wheres:
        return st.apply([st.insert_after(wheres[0], f" {pred} AND")]), f"Added a type-incompatible predicate: {pred}"
    anchor = next((t for t in st.tokens if t.depth == 0 and t.type in ("GROUP_BY", "ORDER_BY", "LIMIT", "UNION", "INTERSECT", "EXCEPT")), None)
    if anchor is not None:
        return st.apply([st.insert_before(anchor, f"WHERE {pred} ")]), f"Added a type-incompatible predicate: {pred}"
    return st.sql.rstrip() + f" WHERE {pred}", f"Added a type-incompatible predicate: {pred}"


# ---------------------------------------------------------------------- mutations: AMBIGUOUS_REFERENCE
def amb_unqualify(st: SQLText, schema, rng, m) -> MutationResult:
    refs = st.table_refs(schema)
    if len(refs) < 2:
        return None
    tables = [schema.table(t.text) for t, _ in refs]
    options = []
    for q, col, table in st.column_refs(schema):
        if q is None:
            continue
        owners = [t for t in tables if t.column(col.text)]
        if len({t.name.lower() for t in owners}) >= 2:
            options.append((q, col))
    if not options:
        return None
    q, col = rng.choice(options)
    dot = st.next(q)
    return st.apply([(q.start, dot.end, "")]), f"Removed the table qualifier from '{col.text}', which exists in several joined tables"


def _rename_alias(st: SQLText, old: str, new: str) -> list:
    """Edits renaming alias `old` to `new` at its definition and at every qualified use."""
    edits = []
    for t in st.tokens:
        if t.type in NAME_TYPES and t.lower == old.lower():
            p, n = st.prev(t), st.next(t)
            if (n is not None and n.type == "DOT") or (p is not None and p.type == "ALIAS") \
                    or (p is not None and p.type in NAME_TYPES):
                edits.append(st.replace_token(t, new))
    return edits


def amb_duplicate_alias(st: SQLText, schema, rng, m) -> MutationResult:
    refs = [(t, a) for t, a in st.table_refs(schema) if a is not None]
    if len(refs) < 2:
        return None
    (t1, a1), (t2, a2) = rng.sample(refs, 2)
    if a1.lower == a2.lower:
        return None
    return st.apply(_rename_alias(st, a2.text, a1.text)), f"Reused alias '{a1.text}' for both {t1.text} and {t2.text}"


def amb_self_join(st: SQLText, schema, rng, m) -> MutationResult:
    refs = [(t, a) for t, a in st.table_refs(schema) if a is not None]
    if len(refs) < 2:
        return None
    (t1, a1), (t2, a2) = rng.sample(refs, 2)
    if a1.lower == a2.lower or t1.lower == t2.lower:
        return None
    edits = [st.replace_token(t2, t1.text)] + _rename_alias(st, a2.text, a1.text)
    return st.apply(edits), f"Joined {t1.text} to itself under the same alias '{a1.text}'"


# ---------------------------------------------------------------------- mutations: SEMANTIC_ERROR
def sem_null_compare(st: SQLText, schema, rng, m) -> MutationResult:
    options = []
    for t in st.of_type("IS"):
        n = st.next(t)
        if n is not None and n.type == "NOT" and st.next(n) is not None and st.next(n).type == "NULL":
            options.append(([(t.start, n.end, rng.choice(["!=", "<>"]))], "Wrote '!= NULL' instead of IS NOT NULL"))
        elif n is not None and n.type == "NULL":
            options.append(([st.replace_token(t, "=")], "Wrote '= NULL' instead of IS NULL"))
    for col, val, table, ctype in _comparisons(st, schema):
        op = st.next(col)
        if op.type in ("EQ", "NEQ") and val.type in ("NUMBER", "STRING", "IDENTIFIER"):
            options.append(([st.replace_token(val, "NULL")], f"Compared '{col.text}' with NULL using {op.text}"))
    if not options:
        return None
    edits, desc = rng.choice(options)
    return st.apply(edits), desc


def sem_having_to_where(st: SQLText, schema, rng, m) -> MutationResult:
    havings = [t for t in st.of_type("HAVING")]
    if not havings:
        return None
    h = rng.choice(havings)
    end = st.clause_end(h)
    cond = st.sql[st.next(h).start:end.end]
    group = next((t for t in reversed(st.tokens[:h.index]) if t.type == "GROUP_BY" and t.depth == h.depth), None)
    if group is None:
        return None
    where = next((t for t in reversed(st.tokens[:group.index]) if t.type == "WHERE" and t.depth == h.depth), None)
    hs, he = h.start, end.end
    while hs > 0 and st.sql[hs - 1] == " ":
        hs -= 1
    edits = [(hs, he, "")]
    if where is not None:
        edits.append(st.insert_after(where, f" {cond} AND"))
    else:
        edits.append(st.insert_before(group, f"WHERE {cond} "))
    return st.apply(edits), "Moved an aggregate condition from HAVING into WHERE"


def sem_aggregate_in_where(st: SQLText, schema, rng, m) -> MutationResult:
    # "x > (SELECT avg(x) FROM t)"  ->  "x > avg(x)"
    for t in st.of_type("L_PAREN"):
        s = st.next(t)
        if s is None or s.type != "SELECT":
            continue
        f = st.next(s)
        if f is None or f.lower not in AGGREGATES or not st.is_function_name(f):
            continue
        close = next((x for x in st.tokens[t.index + 1:] if x.type == "R_PAREN" and x.depth == t.depth), None)
        fclose = next((x for x in st.tokens[f.index + 2:] if x.type == "R_PAREN" and x.depth == f.depth), None)
        if close is None or fclose is None:
            continue
        if any(x.type == "WHERE" for x in st.tokens[t.index + 1:close.index]):
            continue                      # correlated/filtered subquery: not equivalent to a bare aggregate
        agg = st.sql[f.start:fclose.end]
        return st.apply([(t.start, close.end, agg)]), "Used an aggregate directly in WHERE instead of a subquery"
    wheres = [t for t in st.of_type("WHERE") if t.depth == 0]
    refs = st.column_refs(schema)
    if not wheres or not refs:
        return None
    _, col, table = rng.choice(refs)
    fn = rng.choice(["count", "sum", "avg", "max"])
    arg = "*" if fn == "count" else col.text
    return st.apply([st.insert_after(wheres[0], f" {fn}({arg}) > {rng.randint(1, 10)} AND")]), \
        "Put an aggregate condition in WHERE"


def sem_drop_group_by(st: SQLText, schema, rng, m) -> MutationResult:
    groups = st.of_type("GROUP_BY")
    if not groups:
        return None
    g = rng.choice(groups)
    end = st.clause_end(g)
    s, e = g.start, end.end
    while s > 0 and st.sql[s - 1] == " ":
        s -= 1
    return st.apply([(s, e, "")]), "Removed GROUP BY while keeping non-aggregated columns"


def sem_ungrouped_column(st: SQLText, schema, rng, m) -> MutationResult:
    groups = st.of_type("GROUP_BY")
    if not groups:
        return None
    g = groups[0]
    sel = next((t for t in reversed(st.tokens[:g.index]) if t.type == "SELECT" and t.depth == g.depth), None)
    refs = st.table_refs(schema)
    if sel is None or not refs:
        return None
    table_tok, alias = rng.choice(refs)
    grouped = {t.lower for t in st.tokens[g.index:st.clause_end(g).index + 1]}
    cols = [c.name for c in schema.table(table_tok.text).columns if c.name.lower() not in grouped]
    if not cols:
        return None
    col = rng.choice(cols)
    qual = (alias.text + ".") if (alias is not None and len(refs) > 1) else ""
    after = st.next(sel)
    if after is not None and after.type == "DISTINCT":
        sel = after
    return st.apply([st.insert_after(sel, f" {qual}{col} ,")]), f"Selected '{qual}{col}', which is neither grouped nor aggregated"


def sem_drop_join_condition(st: SQLText, schema, rng, m) -> MutationResult:
    ons = st.of_type("ON")
    if not ons:
        return None
    on = rng.choice(ons)
    end = st.clause_end(on, stop_types=CLAUSE_TYPES | {"JOIN", "LEFT", "INNER", "RIGHT", "CROSS"})
    s = on.start
    while s > 0 and st.sql[s - 1] == " ":
        s -= 1
    return st.apply([(s, end.end, "")]), "Removed the ON condition of a JOIN"


def sem_order_position(st: SQLText, schema, rng, m) -> MutationResult:
    orders = [t for t in st.of_type("ORDER_BY")]
    if not orders:
        return None
    o = rng.choice(orders)
    end = st.clause_end(o)
    keep = [t for t in st.tokens[o.index + 1:end.index + 1] if t.type in ("DESC", "ASC")]
    suffix = (" " + keep[-1].text) if keep else ""
    return st.apply([(st.next(o).start, end.end, f"{rng.randint(5, 9)}{suffix}")]), "ORDER BY a column position that does not exist"


def sem_set_op_arity(st: SQLText, schema, rng, m) -> MutationResult:
    ops = [t for t in st.tokens if t.type in ("UNION", "INTERSECT", "EXCEPT") and t.depth == 0]
    if not ops:
        return None
    op = ops[0]
    sel = next((t for t in st.tokens[op.index:] if t.type == "SELECT"), None)
    refs = st.column_refs(schema)
    if sel is None or not refs:
        return None
    _, col, _ = rng.choice(refs)
    return st.apply([st.insert_after(sel, f" {col.text} ,")]), f"The SELECTs around {op.text.upper()} return different numbers of columns"


def sem_subquery_arity(st: SQLText, schema, rng, m) -> MutationResult:
    for t in st.of_type("IN"):
        p = st.next(t)
        s = st.next(p) if p is not None else None
        if p is None or p.type != "L_PAREN" or s is None or s.type != "SELECT":
            continue
        first = st.next(s)
        if first is None:
            continue
        return st.apply([st.insert_after(s, f" {first.text} ,")] if first.type in NAME_TYPES else [st.insert_after(s, " 1 ,")]), \
            "The IN subquery returns more than one column"
    return None


def sem_function_typo(st: SQLText, schema, rng, m) -> MutationResult:
    funcs = [t for t in st.tokens if t.type == "VAR" and t.lower in _FUNC_TYPOS and st.is_function_name(t)]
    if not funcs:
        return None
    f = rng.choice(funcs)
    new = rng.choice(_FUNC_TYPOS[f.lower])
    new = new.upper() if f.text.isupper() else new
    return st.apply([st.replace_token(f, new)]), f"Called the non-existent function {new}() instead of {f.text}()"


MUTATIONS: Dict[str, List[Tuple[Mutation, float]]] = {
    "SYNTAX_ERROR": [
        (syn_drop_comma, 1.0), (syn_drop_keyword, 1.2), (syn_keyword_typo, 1.5), (syn_split_by, 0.5),
        (syn_parenthesis, 1.0), (syn_unclosed_quote, 0.7), (syn_dangling_operator, 1.2),
        (syn_trailing_comma, 0.6), (syn_clause_order, 0.6), (syn_duplicate_keyword, 0.4),
    ],
    "UNKNOWN_TABLE": [(tab_rename, 1.0)],
    "UNKNOWN_COLUMN": [(col_rename, 1.0)],
    "DATATYPE_MISMATCH": [(dt_literal, 1.5), (dt_aggregate, 1.0), (dt_predicate, 0.8)],
    "AMBIGUOUS_REFERENCE": [(amb_unqualify, 2.0), (amb_duplicate_alias, 1.0), (amb_self_join, 0.4)],
    "SEMANTIC_ERROR": [
        (sem_null_compare, 1.2), (sem_having_to_where, 1.0), (sem_aggregate_in_where, 1.0),
        (sem_drop_group_by, 1.0), (sem_ungrouped_column, 1.0), (sem_drop_join_condition, 1.0),
        (sem_order_position, 0.4), (sem_set_op_arity, 0.6), (sem_subquery_arity, 0.5),
        (sem_function_typo, 1.0),
    ],
}


class SQLMutator:
    def __init__(self, foreign_tables: List[str] = (), foreign_columns: List[str] = (),
                 string_values: List[str] = ()):
        # names from *other* databases, used for realistic "hallucinated" identifiers
        self.foreign_tables = list(foreign_tables)
        self.foreign_columns = list(foreign_columns)
        # real string values seen in queries, so injected type errors use natural-looking text
        self.string_values = [v for v in string_values if v and not re.match(r"^[-+.\d\s]+$", v)]

    def text_value(self, rng: random.Random) -> str:
        if self.string_values and rng.random() < 0.7:
            return rng.choice(self.string_values)
        return rng.choice(_WORDS)

    def mutate(self, sql: str, schema: DatabaseSchema, target_class: str,
               rng: random.Random) -> Optional[Tuple[str, str, str]]:
        """Returns (mutated sql, mutation name, description) or None if no mutation applies."""
        st = SQLText.try_parse(sql)
        if st is None:
            return None
        pool = MUTATIONS[target_class]
        funcs, weights = zip(*pool)
        order = []
        remaining = list(range(len(pool)))
        while remaining:
            i = rng.choices(remaining, weights=[weights[j] for j in remaining])[0]
            order.append(i)
            remaining.remove(i)
        for i in order:
            try:
                res = funcs[i](st, schema, rng, self)
            except (ValueError, IndexError, AttributeError):
                res = None
            if res is not None and res[0].strip() != sql.strip():
                return res[0], funcs[i].__name__, res[1]
        return None


# ---------------------------------------------------------------------- label-preserving augmentation
_SPACES = re.compile(r"[ \t]+")


def augment_surface(sql: str, rng: random.Random) -> str:
    """
    Surface variation applied to every sample regardless of class, so that keyword casing and
    spacing carry no label information: keyword case, whitespace style, trailing semicolon.
    """
    st = SQLText.try_parse(sql)
    if st is None:
        return sql
    case = rng.choices(["upper", "lower", "keep"], weights=[0.4, 0.3, 0.3])[0]
    collapse = rng.random() < 0.5
    out, pos = [], 0
    for t in st.tokens:
        gap = sql[pos:t.start]
        if collapse and gap:
            gap = " " if gap.strip() == "" else gap
        out.append(gap)
        text = sql[t.start:t.end]
        is_keyword = t.type not in NAME_TYPES and t.type not in ("STRING", "NUMBER") and text.replace(" ", "").isalpha()
        if is_keyword and case != "keep":
            text = text.upper() if case == "upper" else text.lower()
        out.append(text)
        pos = t.end
    out.append(sql[pos:])
    res = "".join(out).strip()
    if collapse:
        res = _SPACES.sub(" ", res) if "'" not in res and '"' not in res else res
    if res.endswith(";"):
        res = res.rstrip(";").rstrip()
    if rng.random() < 0.1:
        res += ";"
    return res
