"""Static check: every name a function reads is its own, an enclosing one's, the module's or a builtin (python tools/names_check.py FILE).
2026-11-15: removing 猜一猜 left a `said` in _followers_react that a whole-file name check missed."""
import symtable, builtins, sys
src = open(sys.argv[1], encoding='utf-8').read()
top = symtable.symtable(src, sys.argv[1], 'exec')
mod = set(top.get_identifiers())
bad = []
def walk(t, outer):
    for c in t.get_children():
        if c.get_type() == 'function':
            own = {s.get_name() for s in c.get_symbols() if s.is_assigned() or s.is_parameter() or s.is_imported()}
            for s in c.get_symbols():
                n = s.get_name()
                if s.is_referenced() and not (n in own or n in outer or n in mod or hasattr(builtins, n) or s.is_global() and n in mod):
                    if s.is_free() and n in outer: continue
                    bad.append((c.get_name(), c.get_lineno(), n))
            walk(c, outer | own)
        else:
            walk(c, outer)
walk(top, set())
print(bad if bad else "no unknown names")
