extern int printf(const char *, ...);

int main(void) {
  int x = 0x12345678;
  char *p = (char*) &x;
  printf("0x%x 0x%x 0x%x 0x%x\n", p[0], p[1], p[2], p[3]);
  return 0;
}
