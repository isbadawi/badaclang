// RUN: badaclang %s -o %t.ll
// RUN: clang %t.ll -o %t
// RUN: %t | grep '^9$'
extern int printf(const char*, ...);

enum opcode_t {
  OPCODE_ADD,
  OPCODE_SUB,
  OPCODE_MUL,
  OPCODE_DIV
};

struct instruction_t {
  enum opcode_t opcode;
  int lhs;
  int rhs;
};

int instruction_eval(struct instruction_t inst) {
  int result = 0;
  switch (inst.opcode) {
    case OPCODE_ADD: result = inst.lhs + inst.rhs; break;
    case OPCODE_SUB: result = inst.lhs - inst.rhs; break;
    case OPCODE_MUL: result = inst.lhs * inst.rhs; break;
    case OPCODE_DIV: result = inst.lhs / inst.rhs; break;
  }
  return result;
}

int main(int argc, char *argv[]) {
  struct instruction_t inst;
  inst.opcode = OPCODE_ADD;
  inst.lhs = 4;
  inst.rhs = 5;
  int result = instruction_eval(inst);
  printf("%d\n", result);
  return 0;
}
