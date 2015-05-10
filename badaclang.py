import sys

import llvmlite.ir as llvm
from pycparser import parse_file, c_ast as C

INT_TYPES = {
    'char': llvm.IntType(8),
    'int': llvm.IntType(32)
}

class LlvmFunctionGenerator(C.NodeVisitor):
    def __init__(self, module):
        self.module = module
        self.function = None
        self.block = None
        self.ir = None

        self.next_str = 1

    def type(self, node):
        if isinstance(node, C.TypeDecl):
            return self.type(node.type)
        if isinstance(node, C.FuncDecl):
            vararg = False
            return_type = self.type(node.type)
            arg_types = []
            for arg in node.args.params:
                if isinstance(arg, C.EllipsisParam):
                    vararg = True
                else:
                    arg_types.append(self.type(arg.type))
            return llvm.FunctionType(return_type, arg_types, vararg)
        if isinstance(node, C.PtrDecl):
            return self.type(node.type).as_pointer()
        if isinstance(node, C.ArrayDecl):
            return self.type(node.type).as_pointer()
        if isinstance(node, C.IdentifierType):
            assert len(node.names) == 1
            name = node.names[0]
            assert name in INT_TYPES
            return INT_TYPES[name]

    def string_literal(self, val):
        val = val.strip('"')
        # TODO(isbadawi): Other escape sequences
        val = val.replace('\\n', '\n')
        string = bytearray(val, encoding='ascii')
        string.append(0)
        type = llvm.ArrayType(llvm.IntType(8), len(string))
        var = llvm.GlobalVariable(self.module, type, 'str%d' % self.next_str)
        var.initializer = llvm.Constant(type, string)
        var.global_constant = True
        self.next_str += 1
        return var.bitcast(llvm.IntType(8).as_pointer())

    def constant(self, node):
        if node.type == 'string':
            return self.string_literal(node.value)
        elif node.type == 'int':
            return llvm.Constant(llvm.IntType(32), node.value)
        node.show()
        assert False

    def expr(self, node):
        if isinstance(node, C.Constant):
            return self.constant(node)
        if isinstance(node, C.BinaryOp):
            lhs = self.expr(node.left)
            rhs = self.expr(node.right)
            if node.op == '+':
                return self.ir.add(lhs, rhs)
        if isinstance(node, C.ID):
            print(node.name)
        node.show()
        assert(False)

    def visit_FuncDef(self, node):
        self.function = llvm.Function(self.module,
                                      self.type(node.decl.type),
                                      name=node.decl.name)
        for param, arg in zip(node.decl.type.args.params, self.function.args):
            arg.name = param.name
        self.block = self.function.append_basic_block(name='entry')
        self.ir = llvm.IRBuilder()
        self.ir.position_at_end(self.block)
        self.visit(node.body)

    def visit_FuncCall(self, node):
        args = [self.expr(expr) for expr in node.args.exprs]
        target = self.module.get_global(node.name.name)
        self.ir.call(target, args)

    def visit_Return(self, node):
        self.ir.ret(self.expr(node.expr))


def compile(ast, filename):
    module = llvm.Module(name=filename)

    for decl in ast.ext:
        if isinstance(decl, C.Decl):
            assert 'extern' in decl.storage
            assert isinstance(decl.type, C.FuncDecl)
            llvm.Function(module, LlvmFunctionGenerator(None).type(decl.type), name=decl.name)
        elif isinstance(decl, C.Typedef):
            assert(False)
        elif isinstance(decl, C.FuncDef):
            generator = LlvmFunctionGenerator(module)
            generator.visit(decl)
        else:
            assert(False)

    return module

def main():
    filename = sys.argv[1]
    ast = parse_file(sys.argv[1], use_cpp=True)
    module = compile(ast, filename)
    print(module)

if __name__ == '__main__':
    main()
