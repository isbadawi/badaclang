from contextlib import contextmanager

import pycparser.c_ast as C


class SymbolError(Exception):
    def __init__(self, node, msg):
        super().__init__('%s: %s' % (node.coord, msg))


class UndeclaredIdentifier(SymbolError):
    def __init__(self, node):
        super().__init__(node, "use of undeclared identifier '%s'" % node.name)


class Redefinition(SymbolError):
    def __init__(self, node):
        super().__init__(node, "redefinition of '%s'" % node.name)


class SymbolTable(object):
    def __init__(self, parent=None):
        self.symbols = {}
        self.parent = parent

    def __setitem__(self, name, node):
        if name in self.symbols:
            raise Redefinition(node)
        self.symbols[name] = node

    def __getitem__(self, name):
        if name in self.symbols:
            return self.symbols[name]
        if self.parent is not None:
            return self.parent[name]
        raise KeyError(name)

    def __contains__(self, name):
        try:
            self[name]
            return True
        except KeyError:
            return False

    def __str__(self):
        return 'SymbolTable(%s)' % str(self.__dict__)

    def __repr__(self):
        return str(self)


class SymbolTableVisitor(C.NodeVisitor):
    def __init__(self):
        self.globals = SymbolTable()
        self.scope = self.globals

    @contextmanager
    def new_scope(self):
        scope = SymbolTable(self.scope)
        self.scope = scope
        yield scope
        self.scope = scope.parent

    def visit_Decl(self, node):
        if node.name is None:
            node = node.type
            assert isinstance(node, (C.Struct, C.Enum))
            if isinstance(node, C.Enum):
                for key in node.values.enumerators:
                    self.scope[key.name] = key
        self.scope[node.name] = node

    def visit_FuncDef(self, node):
        self.visit_Decl(node.decl)
        with self.new_scope() as scope:
            for param in node.decl.type.args.params:
                self.visit(param)
            self.visit(node.body)

    def visit_StructRef(self, node):
        self.visit(node.name)

    def visit_ID(self, node):
        if node.name not in self.scope:
            raise UndeclaredIdentifier(node)

    def visit_Typedef(self, node):
        node.show()
        raise NotImplementedError('Typedef')


def table(ast):
    visitor = SymbolTableVisitor()
    visitor.visit(ast)
    return visitor.globals
