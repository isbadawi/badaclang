// RUN: badaclang %s -o %t.ll
// RUN: clang %t.ll -o %t
// RUN: %t | grep '0x78 0x56 0x34 0x12'
extern int printf(const char *, ...);

int main(void) {
  int x = 0x12345678;
  char *p = (char*) &x;
  printf("0x%x 0x%x 0x%x 0x%x\n", p[0], p[1], p[2], p[3]);
  return 0;
}
