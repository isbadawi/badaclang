from contextlib import contextmanager
import sys

import llvmlite.ir as llvm
from pycparser import parse_file, c_ast as C

C_TO_LLVM_TYPES = {
    'void': llvm.VoidType(),
    'char': llvm.IntType(8),
    'int': llvm.IntType(32)
}


class LlvmModuleGenerator(C.NodeVisitor):
    def __init__(self, filename):
        self.module = llvm.Module(name=filename)

        self.decl_name = None
        self.decl_type = None

        self.structs = {}
        self.llvm_types = {}
        self.constants = {}

    def llvm_type(self, node):
        if isinstance(node, C.TypeDecl):
            return self.llvm_type(node.type)
        if isinstance(node, C.FuncDecl):
            vararg = False
            return_type = self.llvm_type(node.type)
            arg_types = []
            for arg in node.args.params:
                if isinstance(arg, C.EllipsisParam):
                    vararg = True
                else:
                    arg_types.append(self.llvm_type(arg.type))
            if len(arg_types) == 1 and isinstance(arg_types[0], llvm.VoidType):
                arg_types = []
            return llvm.FunctionType(return_type, arg_types, vararg)
        if isinstance(node, C.PtrDecl):
            return self.llvm_type(node.type).as_pointer()
        if isinstance(node, C.ArrayDecl):
            if node.dim is None:
                return self.llvm_type(node.type).as_pointer()
            assert isinstance(node.dim, C.Constant)
            assert node.dim.type == 'int'
            return llvm.ArrayType(self.llvm_type(node.type), int(node.dim.value))
        if isinstance(node, C.IdentifierType):
            assert len(node.names) == 1
            name = node.names[0]
            assert name in C_TO_LLVM_TYPES
            return C_TO_LLVM_TYPES[name]
        if isinstance(node, C.Enum) or isinstance(node, C.Struct):
            return self.llvm_types[node.name]
        node.show()
        assert(0)

    def visit_Decl(self, node):
        self.decl_name = node.name
        self.decl_type = node.type
        self.generic_visit(node)

    def visit_Enum(self, node):
        self.llvm_types[node.name] = llvm.IntType(32)
        for i, pair in enumerate(node.values.enumerators):
            assert pair.value is None
            self.constants[pair.name] = llvm.Constant(llvm.IntType(32), i)

    def visit_Struct(self, node):
        element_llvm_types = [self.llvm_type(decl.type) for decl in node.decls]
        self.llvm_types[node.name] = llvm.LiteralStructType(element_llvm_types)
        self.structs[node.name] = [decl.name for decl in node.decls]

    def visit_FuncDecl(self, node):
        fn_type = self.llvm_type(self.decl_type)
        llvm.Function(self.module, fn_type, name=self.decl_name)
        self.decl_name = None
        self.decl_type = None

    def visit_FuncDef(self, node):
        generator = LlvmFunctionGenerator(self, self.module)
        generator.visit(node)


class LlvmFunctionGenerator(C.NodeVisitor):
    def __init__(self, parent, module):
        self.parent = parent
        self.module = module
        self.function = None
        self.ir = None

        self.symbol_table = {}

        self.break_targets = []

        self.next_str = 1

    def llvm_type(self, node):
        return self.parent.llvm_type(node)

    def symbol_type(self, name):
        return self.symbol_table[name][0]

    def symbol_value(self, name):
        return self.symbol_table[name][1]

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
            if node.value.startswith('0x'):
                base = 16
            elif node.value.startswith('0'):
                base = 8
            else:
                base = 10
            return llvm.Constant(llvm.IntType(32), int(node.value, base))
        node.show()
        assert False


    def addr(self, node):
        if isinstance(node, C.ID):
            return self.symbol_value(node.name)
        elif isinstance(node, C.ArrayRef):
            # TODO(isbadawi): Understand what's going on here...
            base = self.addr(node.name)
            ptr_type = base.type.pointee
            if isinstance(ptr_type, llvm.ArrayType):
                base = self.ir.bitcast(base, ptr_type.element.as_pointer())
            else:
                base = self.ir.load(base)
            return self.ir.gep(base, [self.expr(node.subscript)])
        elif isinstance(node, C.StructRef):
            assert node.type == '.'
            base = self.addr(node.name)
            type_name = self.symbol_type(node.name.name)
            struct = self.parent.structs[type_name]
            offset = struct.index(node.field.name)
            indices = [
                llvm.Constant(llvm.IntType(32), 0),
                llvm.Constant(llvm.IntType(32), offset)
            ]
            return self.ir.gep(base, indices)
        else:
            node.show()
            assert False

    def expr(self, node):
        if isinstance(node, C.Constant):
            return self.constant(node)
        if isinstance(node, C.UnaryOp):
            if node.op == '-':
                val = self.expr(node.expr)
                assert isinstance(val, llvm.Constant)
                assert isinstance(val.type, llvm.IntType)
                val.constant = val.constant * -1
                return val
            if node.op == 'p++':
                val = self.expr(node.expr)
                inc = self.ir.add(val, llvm.Constant(val.type, 1))
                self.ir.store(inc, self.addr(node.expr))
                return (val)
            elif node.op == '&':
                assert isinstance(node.expr, C.ID)
                return self.addr(node.expr)
            node.show()
            assert(False)
        if isinstance(node, C.BinaryOp):
            lhs = self.expr(node.left)
            if node.op == '&&':
                current_block = self.ir.block
                rhs_block = self.function.append_basic_block('and.rhs')
                end_block = self.function.append_basic_block('and.end')
                self.ir.cbranch(lhs, rhs_block, end_block)
                self.ir.position_at_end(rhs_block)
                rhs = self.expr(node.right)
                self.ir.branch(end_block)
                self.ir.position_at_end(end_block)
                phi = self.ir.phi(llvm.IntType(1))
                phi.add_incoming(lhs, current_block)
                phi.add_incoming(rhs, rhs_block)
                return phi

            rhs = self.expr(node.right)
            if node.op == '+':
                return self.ir.add(lhs, rhs)
            if node.op == '-':
                return self.ir.sub(lhs, rhs)
            if node.op == '*':
                return self.ir.mul(lhs, rhs)
            if node.op == '/':
                return self.ir.sdiv(lhs, rhs)
            elif node.op in ['>', '<', '==', '!=']:
                return self.ir.icmp_signed(node.op, lhs, rhs)
        if isinstance(node, C.Cast):
            to_type = self.llvm_type(node.to_type.type)
            assert(to_type.is_pointer)
            val = self.expr(node.expr)
            return self.ir.bitcast(val, to_type)
        if isinstance(node, C.ID):
            if node.name in self.parent.constants:
                return self.parent.constants[node.name]
            return self.ir.load(self.addr(node))
        if isinstance(node, (C.ArrayRef, C.StructRef)):
            return self.ir.load(self.addr(node))
        if isinstance(node, C.FuncCall):
            args = [self.expr(expr) for expr in node.args.exprs]
            target = self.module.get_global(node.name.name)
            return self.ir.call(target, args)
        node.show()
        assert(False)

    def type_name(self, decl):
        if isinstance(decl.type.type, (C.Struct, C.Enum)):
            return decl.type.type.name
        elif isinstance(decl.type.type, C.IdentifierType):
            return decl.type.type.names[0]
        return None

    def visit_FuncDef(self, node):
        self.function = llvm.Function(self.module,
                                      self.llvm_type(node.decl.type),
                                      name=node.decl.name)
        block = self.function.append_basic_block(name='entry')
        self.ir = llvm.IRBuilder()
        self.ir.position_at_end(block)
        for param, arg in zip(node.decl.type.args.params, self.function.args):
            arg.name = param.name
            local = self.ir.alloca(self.llvm_type(param.type),
                                   name='%s.addr' % param.name)
            self.symbol_table[arg.name] = (self.type_name(param), local)
            self.ir.store(arg, local)
        self.visit(node.body)

    def visit_Decl(self, node):
        local = self.ir.alloca(self.llvm_type(node.type), name=node.name)
        self.symbol_table[node.name] = (self.type_name(node), local)
        if node.init:
            self.ir.store(self.expr(node.init), local)

    def visit_If(self, node):
        then_block = self.function.append_basic_block('if.then')
        else_block = None
        if node.iffalse is not None:
            else_block = self.function.append_basic_block('if.else')
        end_block = self.function.append_basic_block('if.end')
        cond = self.expr(node.cond)
        if_false_block = else_block if else_block else end_block
        self.ir.cbranch(cond, then_block, if_false_block)
        self.ir.position_at_end(then_block)
        self.visit(node.iftrue)
        self.ir.branch(end_block)
        if else_block:
            self.ir.position_at_end(else_block)
            self.visit(node.iffalse)
            self.ir.branch(end_block)
        self.ir.position_at_end(end_block)

    def visit_While(self, node):
        cond_block = self.function.append_basic_block('while.cond')
        body_block = self.function.append_basic_block('while.body')
        end_block = self.function.append_basic_block('while.end')
        self.ir.branch(cond_block)
        self.ir.position_at_end(cond_block)
        cond = self.expr(node.cond)
        self.ir.cbranch(cond, body_block, end_block)
        self.ir.position_at_end(body_block)
        self.visit(node.stmt)
        self.ir.branch(cond_block)
        self.ir.position_at_end(end_block)

    def visit_For(self, node):
        if node.init:
            self.visit(node.init)
        cond_block = self.function.append_basic_block('for.cond')
        body_block = self.function.append_basic_block('for.body')
        inc_block = self.function.append_basic_block('for.inc')
        end_block = self.function.append_basic_block('for.end')

        self.ir.branch(cond_block)
        self.ir.position_at_end(cond_block)
        if node.cond:
            cond = self.expr(node.cond)
            self.ir.cbranch(cond, body_block, end_block)
        else:
            self.ir.branch(body_block)
        self.ir.position_at_end(body_block)
        self.visit(node.stmt)
        self.ir.branch(inc_block)
        self.ir.position_at_end(inc_block)
        if node.next:
            # TODO(isbadawi): Would be nice to be able to just "visit" here.
            self.expr(node.next)
        self.ir.branch(cond_block)
        self.ir.position_at_end(end_block)

    @contextmanager
    def break_target(self, target):
        self.break_targets.append(target)
        yield
        self.break_targets.pop()

    def visit_Break(self, node):
        self.ir.branch(self.break_targets[-1])

    def visit_Switch(self, node):
        case_blocks = []
        for i, case in enumerate(node.stmt.block_items):
            case_blocks.append(self.function.append_basic_block('switch.case%s' % i))
        end_block = self.function.append_basic_block('switch.end')
        switch = self.ir.switch(self.expr(node.cond), end_block)
        for i, case in enumerate(node.stmt.block_items):
            switch.add_case(self.expr(case.expr), case_blocks[i])
        with self.break_target(end_block):
            for i, case in enumerate(node.stmt.block_items):
                self.ir.position_at_end(case_blocks[i])
                for stmt in case.stmts:
                    self.visit(stmt)
        self.ir.position_at_end(end_block)

    def visit_Assignment(self, node):
        # TODO(isbadawi): Assigment as expression...
        assert node.op == '='
        rhs = self.expr(node.rvalue)
        lhs = self.addr(node.lvalue)
        self.ir.store(rhs, lhs)

    def visit_FuncCall(self, node):
        # TODO(ibadawi): This is duplicated in self.expr. No expr stmt?
        args = [self.expr(expr) for expr in node.args.exprs]
        target = self.module.get_global(node.name.name)
        self.ir.call(target, args)

    def visit_Return(self, node):
        self.ir.ret(self.expr(node.expr))


def main():
    filename = sys.argv[1]
    ast = parse_file(filename, use_cpp=True)
    generator = LlvmModuleGenerator(filename)
    generator.visit(ast)
    print(generator.module)

if __name__ == '__main__':
    main()
