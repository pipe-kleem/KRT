import sys
class _Any:
    def __init__(s,*a,**k): pass
    def __getattr__(s,n): return _Any()
    def __call__(s,*a,**k): return _Any()
    def __or__(s,o): return s
    def __ror__(s,o): return s
    def __mro_entries__(s,b): return (object,)
class _Mod(type(sys)):
    def __getattr__(s,n): return _Any()
sys.modules[__name__].__class__=_Mod
