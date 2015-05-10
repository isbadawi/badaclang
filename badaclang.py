import sys

import llvmlite.ir as llvm
from pycparser import parse_file, c_ast as C

INT_TYPES = {
    'char': llvm.IntType(8),
    'int': llvm.IntType(32)
}

next_str = [1]
def llvm_string_literal(val, module):
    val = val.strip('"')
    # TODO(isbadawi): Other escape sequences
    val = val.replace('\\n', '\n')
    string = bytearray(val, encoding='ascii')
    string.append(0)
    type = llvm.ArrayType(llvm.IntType(8), len(string))
    var = llvm.GlobalVariable(module, type, 'str%d' % next_str[0])
    next_str[0] += 1
    var.initializer = llvm.Constant(type, string)
    var.global_constant = True
    return var.bitcast(llvm.IntType(8).as_pointer())

def llvm_type(c_type):
    if isinstance(c_type, C.TypeDecl):
        return llvm_type(c_type.type)
    if isinstance(c_type, C.FuncDecl):
        vararg = False
        return_type = llvm_type(c_type.type)
        arg_types = []
        for arg in c_type.args.params:
            if isinstance(arg, C.EllipsisParam):
                vararg = True
            else:
                arg_types.append(llvm_type(arg.type))
        return llvm.FunctionType(return_type, arg_types, vararg)
    if isinstance(c_type, C.PtrDecl):
        return llvm_type(c_type.type).as_pointer()
    if isinstance(c_type, C.ArrayDecl):
        return llvm_type(c_type.type).as_pointer()
    if isinstance(c_type, C.IdentifierType):
        assert len(c_type.names) == 1
        name = c_type.names[0]
        assert name in INT_TYPES
        return INT_TYPES[name]

def llvm_constant(c_constant, module):
    if c_constant.type == 'string':
        return llvm_string_literal(c_constant.value, module)
    elif c_constant.type == 'int':
        return llvm.Constant(llvm.IntType(32), c_constant.value)
    c_constant.show()
    assert(0)

def llvm_expr(expr, ir, module):
    if isinstance(expr, C.Constant):
        return llvm_constant(expr, module)
    if isinstance(expr, C.BinaryOp):
        lhs = llvm_expr(expr.left, ir, module)
        rhs = llvm_expr(expr.right, ir, module)
        if expr.op == '+':
            return ir.add(lhs, rhs)
    expr.show()
    assert(False)

def compile_function_body(c_body, llvm_func):
    module = llvm_func.parent
    block = llvm_func.append_basic_block(name='entry')
    ir = llvm.IRBuilder()
    ir.position_at_end(block)
    for stmt in c_body.block_items:
        if isinstance(stmt, C.FuncCall):
            args = [llvm_expr(expr, ir, module) for expr in stmt.args.exprs]
            callee = stmt.name.name
            func = module.get_global(callee)
            ir.call(func, args)
        if isinstance(stmt, C.Return):
            assert(isinstance(stmt.expr, C.Constant))
            ir.ret(llvm_constant(stmt.expr, module))

def compile(ast, filename):
    module = llvm.Module(name=filename)

    for decl in ast.ext:
        if isinstance(decl, C.Decl):
            assert 'extern' in decl.storage
            assert isinstance(decl.type, C.FuncDecl)
            llvm.Function(module, llvm_type(decl.type), name=decl.name)
        elif isinstance(decl, C.Typedef):
            assert(False)
        elif isinstance(decl, C.FuncDef):
            func = llvm.Function(module, llvm_type(decl.decl.type), name=decl.decl.name)
            for param, arg in zip(decl.decl.type.args.params, func.args):
                arg.name = param.name
            compile_function_body(decl.body, func)
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
