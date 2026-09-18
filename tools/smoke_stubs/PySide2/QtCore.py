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

class _Meta(type):
    def __getattr__(cls,n):
        v=type(n,(object,),{"__init__":lambda s,*a,**k:None}); setattr(cls,n,v); return v
class _Base(metaclass=_Meta):
    def __init__(s,*a,**k): pass
    def __getattr__(s,n): return _Any()
class _Mod(type(sys)):
    def __getattr__(s,n):
        v=type(n,(_Base,),{}); setattr(s,n,v); return v
sys.modules[__name__].__class__=_Mod
