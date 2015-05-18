from contextlib import contextmanager

import pycparser.c_ast as C
import llvmlite.ir as llvm

i8 = llvm.IntType(8)
i32 = llvm.IntType(32)

C_TO_LLVM_TYPES = {
    'void': llvm.VoidType(),
    'char': i8,
    'int': i32
}

def llvm_type(node, scope):
    if isinstance(node, C.TypeDecl):
        return llvm_type(node.type, scope)
    if isinstance(node, C.FuncDecl):
        vararg = False
        return_type = llvm_type(node.type, scope)
        arg_types = []
        for arg in node.args.params:
            if isinstance(arg, C.EllipsisParam):
                vararg = True
            else:
                arg_types.append(llvm_type(arg.type, scope))
        if len(arg_types) == 1 and isinstance(arg_types[0], llvm.VoidType):
            arg_types = []
        return llvm.FunctionType(return_type, arg_types, vararg)
    if isinstance(node, C.PtrDecl):
        return llvm_type(node.type, scope).as_pointer()
    if isinstance(node, C.ArrayDecl):
        base_type = llvm_type(node.type, scope)
        if node.dim is None:
            return base_type.as_pointer()
        assert isinstance(node.dim, C.Constant)
        assert node.dim.type == 'int'
        return llvm.ArrayType(base_type, int(node.dim.value))
    if isinstance(node, C.IdentifierType):
        assert len(node.names) == 1
        name = node.names[0]
        assert name in C_TO_LLVM_TYPES
        return C_TO_LLVM_TYPES[name]
    if isinstance(node, C.Enum):
        return i32
    if isinstance(node, C.Struct):
        struct = scope[node.name]
        element_types = [llvm_type(decl.type, scope) for decl in struct.decls]
        return llvm.LiteralStructType(element_types)
    node.show()
    assert(0)


class LlvmModuleGenerator(C.NodeVisitor):
    def __init__(self, filename, scopes):
        self.module = llvm.Module(name=filename)
        self.scopes = scopes

        self.decl_name = None
        self.decl_type = None

        self.constants = {}

    def visit_FileAST(self, node):
        self.scope = self.scopes[node]
        self.generic_visit(node)

    def visit_Decl(self, node):
        self.decl_name = node.name
        self.decl_type = node.type
        self.generic_visit(node)

    def visit_Enum(self, node):
        if node.values is None:
            return
        for i, pair in enumerate(node.values.enumerators):
            assert pair.value is None
            self.constants[pair.name] = llvm.Constant(i32, i)

    def visit_FuncDecl(self, node):
        fn_type = llvm_type(self.decl_type, self.scope)
        llvm.Function(self.module, fn_type, name=self.decl_name)
        self.decl_name = None
        self.decl_type = None

    def visit_FuncDef(self, node):
        scope = self.scopes[node]
        generator = LlvmFunctionGenerator(self.module, scope, self.constants)
        generator.visit(node)


class LlvmFunctionGenerator(C.NodeVisitor):
    def __init__(self, module, scope, constants):
        self.module = module
        self.function = None
        self.ir = None
        self.scope = scope
        self.constants = constants
        self.values = {}

        self.break_targets = []

        self.next_str = 1

    def llvm_type(self, node):
        return llvm_type(node, self.scope)

    def addr(self, node):
        if isinstance(node, C.ID):
            return self.values[node.name]
        elif isinstance(node, C.ArrayRef):
            # TODO(isbadawi): Understand what's going on here...
            base = self.addr(node.name)
            ptr_type = base.type.pointee
            if isinstance(ptr_type, llvm.ArrayType):
                base = self.ir.bitcast(base, ptr_type.element.as_pointer())
            else:
                base = self.ir.load(base)
            return self.ir.gep(base, [self.visit(node.subscript)])
        elif isinstance(node, C.StructRef):
            assert node.type == '.'
            decl = self.scope[node.name.name]
            struct = self.scope[decl.type.type.name]
            fields = [decl.name for decl in struct.decls]
            offset = fields.index(node.field.name)
            indices = [llvm.Constant(i32, 0), llvm.Constant(i32, offset)]
            base = self.addr(node.name)
            return self.ir.gep(base, indices)
        else:
            node.show()
            assert False

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
            self.values[arg.name] = local
            self.ir.store(arg, local)
        self.visit(node.body)
        self.function.blocks = [block for block in self.function.blocks
                                if not block.name.startswith('dead')]

    def visit_Decl(self, node):
        type = self.llvm_type(node.type)
        local = self.ir.alloca(type, name=node.name)
        self.values[node.name] = local

        if node.init is None:
            return

        if not isinstance(node.init, C.InitList):
            self.ir.store(self.visit(node.init), local)
            return

        # TODO(isbadawi): Generate memcpy/memset if possible.
        assert isinstance(type, llvm.ArrayType)
        assert len(node.init.exprs) == type.count
        for i, expr in enumerate(node.init.exprs):
            indices = [llvm.Constant(i32, 0), llvm.Constant(i32, i)]
            addr = self.ir.gep(local, indices)
            self.ir.store(self.visit(expr), addr)

    def visit_If(self, node):
        then_block = self.function.append_basic_block('if.then')
        else_block = None
        if node.iffalse is not None:
            else_block = self.function.append_basic_block('if.else')
        end_block = self.function.append_basic_block('if.end')
        cond = self.visit(node.cond)
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

    @contextmanager
    def break_target(self, target):
        self.break_targets.append(target)
        yield
        self.break_targets.pop()

    def visit_Break(self, node):
        self.ir.branch(self.break_targets[-1])
        self.ir.position_at_end(self.function.append_basic_block('dead'))

    def visit_While(self, node):
        cond_block = self.function.append_basic_block('while.cond')
        body_block = self.function.append_basic_block('while.body')
        end_block = self.function.append_basic_block('while.end')
        self.ir.branch(cond_block)
        self.ir.position_at_end(cond_block)
        cond = self.visit(node.cond)
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
            cond = self.visit(node.cond)
            self.ir.cbranch(cond, body_block, end_block)
        else:
            self.ir.branch(body_block)
        self.ir.position_at_end(body_block)
        with self.break_target(end_block):
            self.visit(node.stmt)
        self.ir.branch(inc_block)
        self.ir.position_at_end(inc_block)
        if node.next:
            self.visit(node.next)
        self.ir.branch(cond_block)
        self.ir.position_at_end(end_block)

    def visit_Switch(self, node):
        case_blocks = []
        for i, case in enumerate(node.stmt.block_items):
            block = self.function.append_basic_block('switch.case%s' % i)
            case_blocks.append(block)
        end_block = self.function.append_basic_block('switch.end')
        switch = self.ir.switch(self.visit(node.cond), end_block)
        for i, case in enumerate(node.stmt.block_items):
            switch.add_case(self.visit(case.expr), case_blocks[i])
        with self.break_target(end_block):
            for i, case in enumerate(node.stmt.block_items):
                self.ir.position_at_end(case_blocks[i])
                for stmt in case.stmts:
                    self.visit(stmt)
        self.ir.position_at_end(end_block)

    def visit_Return(self, node):
        self.ir.ret(self.visit(node.expr))
        self.ir.position_at_end(self.function.append_basic_block('dead'))

    def visit_Assignment(self, node):
        assert node.op == '='
        rhs = self.visit(node.rvalue)
        lhs = self.addr(node.lvalue)
        self.ir.store(rhs, lhs)
        return rhs

    def visit_FuncCall(self, node):
        args = [self.visit(expr) for expr in node.args.exprs]
        target = self.module.get_global(node.name.name)
        for i, (arg, param) in enumerate(zip(args, target.args)):
            if arg.type != param.type:
                # Yeah...
                assert isinstance(arg.type, llvm.ArrayType)
                assert param.type.is_pointer
                assert arg.type.element == param.type.pointee
                assert isinstance(arg, llvm.LoadInstr)
                args[i] = self.ir.bitcast(arg.operands[0], param.type)
        return self.ir.call(target, args)

    def visit_Constant(self, node):
        if node.type == 'string':
            # TODO(isbadawi): Other escape sequences
            val = node.value.strip('"').replace('\\n', '\n')
            string = bytearray(val, encoding='ascii')
            string.append(0)
            type = llvm.ArrayType(i8, len(string))
            var = llvm.GlobalVariable(self.module, type, 'str%d' % self.next_str)
            var.initializer = llvm.Constant(type, string)
            var.global_constant = True
            self.next_str += 1
            return var.bitcast(i8.as_pointer())
        elif node.type == 'int':
            if node.value.startswith('0x'):
                base = 16
            elif node.value.startswith('0'):
                base = 8
            else:
                base = 10
            return llvm.Constant(i32, int(node.value, base))
        node.show()
        assert False

    def visit_UnaryOp(self, node):
        if node.op == '-':
            val = self.visit(node.expr)
            assert isinstance(val, llvm.Constant)
            assert isinstance(val.type, llvm.IntType)
            val.constant = val.constant * -1
            return val
        if node.op in ['++', 'p++']:
            val = self.visit(node.expr)
            inc = self.ir.add(val, llvm.Constant(val.type, 1))
            self.ir.store(inc, self.addr(node.expr))
            return inc if node.op == '++' else val
        elif node.op == '&':
            assert isinstance(node.expr, C.ID)
            return self.addr(node.expr)
        node.show()
        assert(False)

    def visit_BinaryOp(self, node):
        lhs = self.visit(node.left)
        if node.op in ['&&', '||']:
            current_block = self.ir.block
            prefix = 'and' if node.op == '&&' else 'or'
            rhs_block = self.function.append_basic_block('%s.rhs' % prefix)
            end_block = self.function.append_basic_block('%s.end' % prefix)
            if node.op == '&&':
                self.ir.cbranch(lhs, rhs_block, end_block)
            else:
                self.ir.cbranch(lhs, end_block, rhs_block)
            self.ir.position_at_end(rhs_block)
            rhs = self.visit(node.right)
            self.ir.branch(end_block)
            self.ir.position_at_end(end_block)
            phi = self.ir.phi(llvm.IntType(1))
            phi.add_incoming(lhs, current_block)
            phi.add_incoming(rhs, rhs_block)
            return phi

        rhs = self.visit(node.right)
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
        node.show()
        assert(False)

    def visit_Cast(self, node):
        to_type = self.llvm_type(node.to_type.type)
        assert(to_type.is_pointer)
        val = self.visit(node.expr)
        return self.ir.bitcast(val, to_type)

    def visit_ID(self, node):
        if node.name in self.constants:
            return self.constants[node.name]
        return self.ir.load(self.addr(node))

    def visit_ArrayRef(self, node):
        return self.ir.load(self.addr(node))

    def visit_StructRef(self, node):
        return self.ir.load(self.addr(node))

def llvm_module(filename, ast, scopes):
    generator = LlvmModuleGenerator(filename, scopes)
    generator.visit(ast)
    return generator.module
